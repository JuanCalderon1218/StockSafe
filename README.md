# StockSafe | Sistema de inventario y respaldos NoSQL

Proyecto academico independiente para **NoSQL Backup Strategy**.

StockSafe es un sistema web de inventario con panel de control, productos,
movimientos de stock, usuarios y roles, copias cifradas de MongoDB y
restauracion de informacion. Usa **FastAPI + MongoDB Atlas + Jinja2**.

## Que incluye

- Dashboard con indicadores de stock, valor, alertas y graficos.
- CRUD de productos; desactivacion logica en lugar de eliminacion fisica.
- Entradas y salidas con validacion de stock no negativo e historial.
- Administradores y operadores, contrasenas Argon2 y CSRF en formularios.
- Exportacion de productos a CSV y API de consulta protegida.
- Respaldos NoSQL cifrados con AES-256-GCM, con fecha y conteos.
- Descarga, importacion y restauracion de archivos `.ssb`.
- Copia preventiva automatica antes de restaurar (rollback compensatorio).
- Automatizacion CI/CD con GitHub Actions y deploy hook de Render.
- Backups cifrados diarios en artifacts de GitHub (30 dias de retencion).
- Pruebas automatizadas con pytest y MongoDB simulado (mongomock).

## 1. Requisitos

- Python 3.12, Windows/Linux/macOS.
- Cuenta de MongoDB Atlas con un cluster y un usuario de base de datos.
- Conexion a internet para el cluster y las librerias de interfaz.

## 2. Preparar MongoDB Atlas

1. En https://cloud.mongodb.com crea un proyecto y un cluster.
2. En **Database Access**, crea un usuario con permisos de lectura/escritura
   en `stocksafe_db` y `stocksafe_vault`. No uses una cuenta administrativa global.
3. En **Network Access** agrega las IPs de acceso necesarias. Para pruebas
   academicas, una apertura temporal de red puede ser necesaria si Render y
   GitHub Actions usan IPs de salida variables. Evita exposicion indefinida.
4. En **Connect > Drivers > Python**, copia el string de conexion de MongoDB.
5. Si el usuario o la contrasena tienen caracteres especiales, aplica URL encoding.

## 3. Ejecutar en Windows (PowerShell)

Desde la carpeta StockSafe:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Si PowerShell bloquea el entorno virtual, ejecuta
`Set-ExecutionPolicy -Scope Process Bypass` en esa terminal y vuelve a activarlo.

Edita `.env` y cambia **sin excepcion**:

- `MONGODB_URI`: string del cluster Atlas.
- `SESSION_SECRET`: una cadena aleatoria de 32 o mas caracteres.
- `BACKUP_PASSPHRASE`: clave de cifrado privada de 24 o mas caracteres.
- `ADMIN_EMAIL`: correo de administrador inicial.
- `ADMIN_PASSWORD`: contrasena de 12 o mas caracteres, sin prefijo `CHANGE_THIS`.
- `SEED_DEMO_DATA=true`: opcional; crea 12 productos en una base vacia.

Para crear secretos seguros desde Python:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Usa resultados distintos para SESSION_SECRET y BACKUP_PASSPHRASE.
No compartas las claves ni las subas al repositorio. El `.gitignore` excluye `.env`.

Inicia la aplicacion:

```powershell
uvicorn app.main:app --reload
```

Abre http://127.0.0.1:8000 e inicia sesion con ADMIN_EMAIL y ADMIN_PASSWORD.
El administrador se crea la primera vez y NO se reescribe al reiniciar.

## 4. Pruebas y demostracion de recuperacion

1. Inicia sesion como administrador.
2. Crea un producto o activa SEED_DEMO_DATA para tener productos de muestra.
3. En **Respaldos NoSQL**, pulsa **Crear respaldo ahora**.
4. Descarga el archivo `.ssb` para conservar una copia externa.
5. Ve a Productos y cambia o registra datos de prueba.
6. Ve a Respaldos > Restaurar la copia anterior. Escribe `RESTAURAR`.
7. Comprueba que productos y movimientos regresaron a la instantanea.

**Importante:** la restauracion reemplaza las dos colecciones operativas.
Haz la demostracion solo en un entorno de laboratorio sin usuarios activos.
Esta edicion utiliza rollback compensatorio, no una transaccion ACID del
cluster. El respaldo previo se conserva. No incluye cuentas de usuario.

## 5. Subir a GitHub

Crea un repositorio PUBLICO NUEVO llamado `StockSafe` y en esta carpeta:

```powershell
git init
git branch -M main
git add .
git commit -m "StockSafe inventario y backup NoSQL"
git remote add origin https://github.com/JuanCalderon1218/StockSafe.git
git push -u origin main
```

No subas `.env` ni archivos `.ssb` a Git. Github Actions y la web reciben
los secretos mediante variables de entorno.

## 6. Despliegue publico en Render

1. En https://dashboard.render.com crea un **Blueprint** con el repositorio,
   usando el archivo `render.yaml` ya incluido. Tambien puedes crear un Web
   Service Python manualmente.
2. Completa las variables solicitadas en Render:
   `MONGODB_URI`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` y `BACKUP_PASSPHRASE`.
   `SESSION_SECRET` se genera automaticamente con render.yaml.
3. Las restantes variables quedan definidas en `render.yaml`.
4. El servicio utiliza `pip install -r requirements.txt` y el comando:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

5. Espera a que `/health` responda `{"status":"ok",...}`.
6. Abre tu URL publica `https://<nombre-servicio>.onrender.com`.

No inventes la URL: Render muestra la definitiva en el panel del servicio.

## 7. Despliegue automatizado despues de pruebas

El archivo `.github/workflows/ci-deploy.yml`:

- Ejecuta pytest en cada `push` o Pull Request a `main`.
- Si las pruebas pasan y el evento fue un push a main, llama al Deploy Hook de Render.
- Si falta el secreto, el trabajo de deploy FALLA claramente, en vez de fingir exito.

En Render entra al servicio > **Settings > Deploy Hook** y copia la URL.
En GitHub > **Settings > Secrets and variables > Actions**, crea el secreto:

`RENDER_DEPLOY_HOOK_URL` = URL privada del Deploy Hook.

El `render.yaml` tiene `autoDeployTrigger: off` para evitar dos despliegues
por cada push. El primer despliegue del Blueprint es manual/creacion.

## 8. Respaldos diarios fuera de MongoDB

El archivo `.github/workflows/backup.yml` ejecuta el respaldo todos los dias
**12:17 UTC (07:17 hora de Peru)** y permite tambien **Run workflow** manual.
El job genera un archivo cifrado `.ssb` con productos y movimientos, que se
conserva como artifact de GitHub Actions durante **30 dias**.

Configura estos secretos de GitHub Actions:

- `MONGODB_URI`: cadena de conexion de Atlas.
- `BACKUP_PASSPHRASE`: EXACTAMENTE la misma clave que en Render.

Para probarlo: GitHub > Actions > Respaldo NoSQL cifrado > Run workflow.
Descarga el artifact, descomprime el ZIP para obtener el `.ssb`, y usa el
formulario **Importar respaldo externo** en StockSafe. Luego restaura.

**No pierdas BACKUP_PASSPHRASE**: sin ella no se pueden descifrar copias antiguas.
Los artifacts de GitHub pueden estar disponibles para colaboradores autorizados:
se guardan cifrados y deben gestionarse con permisos adecuados.

## 9. Estrategia de backup / limitaciones

- **Formato**: snapshot de documentos de `products` y `movements` codificados
  como MongoDB Extended JSON (conserva ObjectId/fechas), comprimidos GZIP y
  cifrados mediante AES-256-GCM con clave derivada por Scrypt y sal aleatoria.
- **No es `mongodump`** ni un respaldo completo del cluster o de todas las
  colecciones. Es un backup LOGICO a nivel de aplicacion de las dos colecciones.
- **Operativo**: copias en `stocksafe_vault` con GridFS dentro del mismo cluster;
  protegen ante borrado/error de la aplicacion, pero NO ante perdida del cluster.
- **Externo**: workflow de GitHub Actions con artifact `.ssb` fuera de Atlas.
- **Alcance**: maximo 10000 documentos por coleccion; archivo cifrado <=25 MB.
- **Restauracion**: reemplaza las colecciones sin permitir nuevas operaciones
  concurrentes durante el proceso de demostracion. El respaldo previo queda guardado.
- **Almacenamiento**: backups de la interfaz consumen espacio del cluster.
- **Seguridad**: documentos de usuarios y hash de contrasenas no se exportan.
- **Produccion real**: requeriria almacenamiento externo de larga retencion,
  politicas de retencion/monitoreo, restauracion transaccional y pruebas de DR.

## 10. Ejecutar pruebas automatizadas

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Usan `mongomock` y no requieren credenciales reales de Atlas.

## 11. Evidencias para la entrega del laboratorio

- Dashboard con datos registrados.
- Productos y movimientos con cambio de stock.
- Consola de MongoDB Atlas con colecciones `products` y `movements`.
- Vista de backups antes y despues de restaurar.
- Descarga del archivo `.ssb` y restauracion de un producto eliminado.
- Github Actions con tests (check verde) y deploy desde el hook.
- Github Actions con backup programado/exitoso y artifact cifrado.
- URL publica en Render, repositorio y articulo individual por integrante.
- Video publico de hasta 5 minutos (agregar al terminar).

## Rutas

- `/login`: autenticacion.
- `/dashboard`: resumen.
- `/productos`: gestion de productos.
- `/movimientos`: registro de entradas y salidas.
- `/respaldos`: backups y restauracion solo para administradores.
- `/usuarios`: administracion de usuarios.
- `/api/v1/productos`: API JSON autenticada de productos activos.
- `/health`: conexion al cluster.

## Equipo

Juan Carlos Calderon Rodriguez y Franco Mango Puma.
Los articulos y el video se agregaran al completar la publicacion.
