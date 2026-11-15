# StockSafe - Inicio rapido para la entrega

## En el PC (Windows)

1. Extraer el ZIP y abrir la carpeta StockSafe en Visual Studio Code.
2. Abrir PowerShell en esa carpeta y ejecutar:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

3. Crear un cluster MongoDB Atlas y copiar su URL en `MONGODB_URI` del `.env`.
4. Completar `ADMIN_PASSWORD`, `SESSION_SECRET` y `BACKUP_PASSPHRASE`.
5. Configurar `SEED_DEMO_DATA=true` para mostrar 12 productos de ejemplo.
6. Ejecutar `uvicorn app.main:app --reload`.
7. Entrar a `http://127.0.0.1:8000` e iniciar sesion con el admin del `.env`.

## GitHub (repositorio nuevo)

1. Crear repositorio publico **StockSafe** en github.com/JuanCalderon1218.
2. Ejecutar en el directorio de proyecto:

```powershell
git init
git branch -M main
git add .
git commit -m "StockSafe NoSQL Backup Strategy"
git remote add origin https://github.com/JuanCalderon1218/StockSafe.git
git push -u origin main
```

## Render y GitHub Actions

1. Render: New > Blueprint > elegir el repositorio; usa `render.yaml`.
2. Render: configurar `MONGODB_URI`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` y `BACKUP_PASSPHRASE`.
3. Render: Settings > Deploy Hook > copiar la URL privada.
4. GitHub: Settings > Secrets and variables > Actions; crear:
   - `RENDER_DEPLOY_HOOK_URL`: hook de Render.
   - `MONGODB_URI`: cadena de conexion de Atlas.
   - `BACKUP_PASSPHRASE`: EXACTAMENTE la clave usada en Render.
5. GitHub > Actions > Pruebas y despliegue > comprobar la ejecucion.
6. GitHub > Actions > Respaldo NoSQL cifrado > Run workflow.
7. En la web, ir a Respaldos > Crear > Descargar > Restaurar.

## Importante

- El archivo `.env` nunca debe subirse ni enviarse al docente.
- No publiques contrasenas, hooks, archivos de respaldo descifrados ni URI con credenciales.
- Se requiere una cuenta Atlas real para ejecutar en local y Render.
- El flujo de GitHub genera copias fuera del cluster durante 30 dias.
- Las evidencias, dos articulos y video se preparan despues de verificar el sistema.
- Lee `README.md` para detalles, limitaciones y solucion de errores.
