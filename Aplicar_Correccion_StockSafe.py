from pathlib import Path
import sys

root = Path(__file__).resolve().parent
if not (root / 'app' / 'main.py').is_file():
    print('ERROR: Guarda este archivo dentro de la carpeta StockSafe, junto a render.yaml.')
    sys.exit(1)

main_path = root / 'app' / 'main.py'
main = main_path.read_text(encoding='utf-8')
marker = '@app.get("/health")'
if '/internal/backup/export' not in main:
    if marker not in main or 'import logging\n' not in main:
        raise SystemExit('La estructura de app/main.py es distinta; no se hicieron cambios.')
    new_endpoint = '''@app.post("/internal/backup/export", include_in_schema=False)
def backup_export_for_actions(request: Request):
    """Generate an encrypted snapshot only for the dedicated backup automation."""
    token = os.getenv("STOCKSAFE_BACKUP_TOKEN", "")
    authorization = request.headers.get("authorization", "")
    if len(token) < 32 or not secrets.compare_digest(authorization, "Bearer " + token):
        raise HTTPException(status_code=403, detail="Acceso denegado.")
    encrypted, _ = backups.make_encrypted_snapshot(db.get_db())
    filename = "stocksafe_auto_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + ".ssb"
    return Response(
        content=encrypted,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


'''
    main = main.replace('import logging\n', 'import logging\nimport os\n', 1)
    main = main.replace(marker, new_endpoint + marker, 1)
    main_path.write_text(main, encoding='utf-8')

workflow_path = root / '.github' / 'workflows' / 'backup.yml'
if not workflow_path.is_file():
    raise SystemExit('No se encontro .github/workflows/backup.yml')
workflow = '''name: Respaldo NoSQL cifrado (fuera de MongoDB)

on:
  schedule:
    - cron: '17 12 * * *' # 07:17 en Peru (UTC-5)
  workflow_dispatch:

permissions:
  contents: read

jobs:
  backup:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - name: Descargar copia cifrada desde StockSafe en Render
        env:
          STOCKSAFE_BACKUP_TOKEN: ${{ secrets.STOCKSAFE_BACKUP_TOKEN }}
        run: |
          set -euo pipefail
          if [ -z "$STOCKSAFE_BACKUP_TOKEN" ]; then
            echo "::error::Configura STOCKSAFE_BACKUP_TOKEN en GitHub Actions y Render."
            exit 1
          fi
          mkdir -p backups
          FILE="backups/stocksafe_auto_$(date -u +%Y%m%d_%H%M%S).ssb"
          curl --fail --silent --show-error --location --retry 3 --retry-delay 15 \\
            --connect-timeout 30 --max-time 240 \\
            -X POST \\
            -H "Authorization: Bearer $STOCKSAFE_BACKUP_TOKEN" \\
            -H "Accept: application/octet-stream" \\
            --output "$FILE" \\
            "https://stocksafe-inventario.onrender.com/internal/backup/export"
          python -c "from pathlib import Path; p=next(Path('backups').glob('*.ssb')); d=p.read_bytes(); assert len(d)>48 and d[:4]==b'SSB1', 'Respaldo invalido'; print('Respaldo cifrado verificado:', len(d), 'bytes')"
      - name: Conservar copia externa
        uses: actions/upload-artifact@v4
        with:
          name: stocksafe-nosql-${{ github.run_id }}
          path: backups/*.ssb
          if-no-files-found: error
          retention-days: 30
'''
workflow_path.write_text(workflow, encoding='utf-8')

render_path = root / 'render.yaml'
render = render_path.read_text(encoding='utf-8')
if 'STOCKSAFE_BACKUP_TOKEN' not in render:
    needle = '      - key: BACKUP_PASSPHRASE\n        sync: false'
    if needle not in render:
        raise SystemExit('No encuentro el bloque de variables en render.yaml')
    render = render.replace(needle, needle + '\n      - key: STOCKSAFE_BACKUP_TOKEN\n        sync: false')
    render_path.write_text(render, encoding='utf-8')

tests_path = root / 'tests' / 'test_backups.py'
tests = tests_path.read_text(encoding='utf-8')
if 'test_automation_backup_requires_token' not in tests:
    tests += '''\n\ndef test_automation_backup_requires_token(state, monkeypatch):
    web, database, _ = state
    monkeypatch.delenv("STOCKSAFE_BACKUP_TOKEN", raising=False)
    assert web.post("/internal/backup/export").status_code == 403
    token = "test-only-bearer-token-with-at-least-32-chars"
    monkeypatch.setenv("STOCKSAFE_BACKUP_TOKEN", token)
    assert web.post("/internal/backup/export").status_code == 403
    response = web.post("/internal/backup/export", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 200
    assert response.content.startswith(b"SSB1")
    assert response.headers["content-type"] == "application/octet-stream"
'''
    tests_path.write_text(tests, encoding='utf-8')

readme_path = root / 'README.md'
readme = readme_path.read_text(encoding='utf-8')
if '## Backup programado desde GitHub Actions (sin abrir Atlas a todas las IP)' not in readme:
    readme += '''\n\n## Backup programado desde GitHub Actions (sin abrir Atlas a todas las IP)

El workflow de backup solicita a StockSafe en Render una copia cifrada de los
productos y movimientos y la guarda fuera del cluster durante 30 dias en
GitHub Actions Artifacts. Render se conecta a Atlas; los runners de GitHub
no necesitan acceso de red directo a MongoDB.

1. Genera un secreto de 32 o mas caracteres en PowerShell:
   `python -c "import secrets; print(secrets.token_urlsafe(48))"`
2. Copia ese valor PRIVADO a Render > stocksafe-inventario > Environment,
   variable `STOCKSAFE_BACKUP_TOKEN`, y guarda con despliegue.
3. Copia el MISMO valor a GitHub > Settings > Secrets and variables > Actions,
   secreto `STOCKSAFE_BACKUP_TOKEN`.
4. En GitHub > Actions > Respaldo NoSQL cifrado > Run workflow ejecuta la prueba.
5. Comprueba que el job termine verde y descarga el `.ssb` en Artifacts.

No compartas la clave o los archivos de respaldo. Conserva en privado
`BACKUP_PASSPHRASE` para poder restaurar los respaldos cifrados.
'''
    readme_path.write_text(readme, encoding='utf-8')

print('CORRECCION APLICADA: endpoint protegido, workflow, Render, prueba y README.')
print('Siguiente: git add . && git commit -m "Corregir backup automatizado" && git push')
