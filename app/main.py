import csv
import io
import logging
import os
import re
import secrets
from collections import Counter
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from bson import ObjectId
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pymongo.errors import DuplicateKeyError
from starlette.middleware.sessions import SessionMiddleware
from jinja2 import Environment
from fastapi.templating import Jinja2Templates

from . import db, security
from .bootstrap import bootstrap, utc_now
from .config import settings, check_config
from .security import hash_password, verify_password
from .services.inventory import (
    InventoryError, create_product, parse_object_id, product_payload,
    record_movement, update_product,
)
from .services import backups

logger = logging.getLogger("stocksafe")
BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(application: FastAPI):
    check_config()
    try:
        bootstrap()
        logger.info("StockSafe: MongoDB connected and ready.")
    except Exception as exc:
        if settings.environment == "production":
            raise
        logger.warning("StockSafe starts without a configured database: %s", exc)
    yield


app = FastAPI(title="StockSafe", description="NoSQL inventory and backup demonstration", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret or "development-only-insecure-session-secret",
    session_cookie="stocksafe_session",
    max_age=60 * 60 * 8,
    same_site="lax",
    https_only=settings.environment == "production",
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def pen(cents):
    return "S/ {:,.2f}".format((int(cents or 0)) / 100)


def date_text(value):
    if not value:
        return "--"
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    return str(value)


templates.env.filters["pen"] = pen
templates.env.filters["fecha"] = date_text


def view(request, template_name, user=None, status_code=200, **extra):
    context = {
        "request": request, "user": user, "csrf": security.session_token(request),
        "flash": request.session.pop("flash", None),
        "active": request.url.path.split("/")[1] or "dashboard", "year": date.today().year,
        **extra,
    }
    return templates.TemplateResponse(request=request, name=template_name,
                                      context=context, status_code=status_code)


def go(location, request=None, message=None, kind="success"):
    if request is not None and message:
        security.set_flash(request, message, kind)
    return RedirectResponse(location, status_code=303)


def authenticated(request):
    user = security.current_user(request)
    return user


def denied():
    return RedirectResponse("/login", status_code=303)


def ensure_admin(user):
    security.require_admin(user)


@app.post("/internal/backup/export", include_in_schema=False)
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


@app.get("/health")
def health():
    try:
        db.get_client().admin.command("ping")
        return {"status": "ok", "app": "StockSafe", "database": "connected"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "disconnected"})


@app.get("/", include_in_schema=False)
def home(request: Request):
    return go("/dashboard" if authenticated(request) else "/login")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if authenticated(request):
        return go("/dashboard")
    return view(request, "login.html")


@app.post("/login", response_class=HTMLResponse)
def login_action(request: Request, email: str = Form(...), password: str = Form(...), csrf_token: str = Form(...)):
    security.require_csrf(request, csrf_token)
    email = email.strip().lower()
    try:
        user = db.get_db().users.find_one({"email": email, "active": True})
    except Exception:
        return view(request, "login.html", status_code=503,
                    error="No se pudo conectar a MongoDB. Revisa MONGODB_URI y el acceso de red.")
    if not user or not verify_password(user["password_hash"], password):
        return view(request, "login.html", status_code=401, error="Correo o contrasena incorrectos.")
    request.session.clear()
    request.session["uid"] = str(user["_id"])
    request.session["csrf"] = secrets.token_urlsafe(32)
    return go("/dashboard", request, "Bienvenido a StockSafe.")


@app.post("/logout")
def logout(request: Request, csrf_token: str = Form(...)):
    security.require_csrf(request, csrf_token)
    request.session.clear()
    return go("/login")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    user = authenticated(request)
    if not user:
        return denied()
    database = db.get_db()
    products = list(database.products.find({"active": True}).limit(10000))
    total = len(products)
    low = sum(1 for p in products if p["stock"] <= p.get("min_stock", 0))
    inventory_value = sum(p["stock"] * p["price_cents"] for p in products)
    units = sum(p["stock"] for p in products)
    movements = list(database.movements.find().sort("created_at", -1).limit(7))
    recent = list(database.movements.find({"created_at": {"$gte": utc_now() - timedelta(days=7)}}).limit(3000))
    daily = Counter((m["created_at"].date().isoformat(), m.get("type")) for m in recent)
    labels = [(date.today() - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    category_counts = Counter(p["category"] for p in products)
    return view(request, "dashboard.html", user=user, total=total, low=low, units=units,
                inventory_value=inventory_value, movements=movements,
                days=[date.fromisoformat(d).strftime("%d/%m") for d in labels],
                entries=[daily[(d, "entrada")] for d in labels],
                exits=[daily[(d, "salida")] for d in labels],
                categories=category_counts.most_common(5),
                low_products=sorted([p for p in products if p["stock"] <= p.get("min_stock", 0)],
                                    key=lambda p: p["stock"])[:5])


@app.get("/productos", response_class=HTMLResponse)
def product_list(request: Request, q: str = "", estado: str = "activos"):
    user = authenticated(request)
    if not user:
        return denied()
    query = {}
    if estado == "activos":
        query["active"] = True
    elif estado == "inactivos":
        query["active"] = False
    if q.strip():
        escaped = re.escape(q.strip()[:60])
        query["$or"] = [{"name": {"$regex": escaped, "$options": "i"}},
                        {"sku": {"$regex": escaped, "$options": "i"}},
                        {"category": {"$regex": escaped, "$options": "i"}}]
    products = list(db.get_db().products.find(query).sort("name", 1).limit(300))
    return view(request, "products.html", user=user, products=products, q=q,
                estado=estado, count=db.get_db().products.count_documents(query))


@app.get("/productos/nuevo", response_class=HTMLResponse)
def new_product(request: Request):
    user = authenticated(request)
    if not user:
        return denied()
    return view(request, "product_form.html", user=user, product=None,
                initial_stock=0, mode="create")


@app.post("/productos/nuevo")
def create_product_post(
    request: Request, name: str = Form(...), sku: str = Form(...), category: str = Form(...),
    price: str = Form(...), min_stock: str = Form(...), initial_stock: str = Form("0"),
    description: str = Form(""), image_url: str = Form(""), csrf_token: str = Form(...),
):
    security.require_csrf(request, csrf_token)
    user = authenticated(request)
    if not user:
        return denied()
    try:
        payload = product_payload(name, sku, category, price, min_stock, description, image_url)
        create_product(db.get_db(), payload, initial_stock)
        return go("/productos", request, "Producto registrado correctamente.")
    except InventoryError as exc:
        item = dict(name=name, sku=sku, category=category, price_text=price,
                    min_stock=min_stock, description=description, image_url=image_url)
        return view(request, "product_form.html", user=user, product=item,
                    initial_stock=initial_stock, mode="create", error=str(exc), status_code=422)


@app.get("/productos/{product_id}/editar", response_class=HTMLResponse)
def edit_product(request: Request, product_id: str):
    user = authenticated(request)
    if not user:
        return denied()
    try:
        product = db.get_db().products.find_one({"_id": parse_object_id(product_id)})
    except InventoryError:
        raise HTTPException(404, "Producto invalido.")
    if not product:
        raise HTTPException(404, "Producto no encontrado.")
    product["price_text"] = str(Decimal(product["price_cents"]) / 100)
    return view(request, "product_form.html", user=user, product=product, mode="edit")


@app.post("/productos/{product_id}/editar")
def edit_product_post(
    request: Request, product_id: str, name: str = Form(...), sku: str = Form(...),
    category: str = Form(...), price: str = Form(...), min_stock: str = Form(...),
    description: str = Form(""), image_url: str = Form(""), csrf_token: str = Form(...),
):
    security.require_csrf(request, csrf_token)
    user = authenticated(request)
    if not user:
        return denied()
    try:
        payload = product_payload(name, sku, category, price, min_stock, description, image_url)
        update_product(db.get_db(), product_id, payload)
        return go("/productos", request, "Producto actualizado correctamente.")
    except InventoryError as exc:
        item = dict(_id=product_id, name=name, sku=sku, category=category,
                    price_text=price, min_stock=min_stock, description=description,
                    image_url=image_url)
        return view(request, "product_form.html", user=user, product=item,
                    mode="edit", error=str(exc), status_code=422)


@app.post("/productos/{product_id}/estado")
def toggle_product(request: Request, product_id: str, csrf_token: str = Form(...)):
    security.require_csrf(request, csrf_token)
    user = authenticated(request)
    if not user:
        return denied()
    ensure_admin(user)
    oid = parse_object_id(product_id)
    product = db.get_db().products.find_one({"_id": oid})
    if not product:
        raise HTTPException(404, "No existe el producto.")
    db.get_db().products.update_one({"_id": oid}, {"$set": {
        "active": not product.get("active", True), "updated_at": utc_now()}})
    return go("/productos?estado=todos", request, "Estado del producto actualizado.")


@app.get("/movimientos", response_class=HTMLResponse)
def movement_list(request: Request):
    user = authenticated(request)
    if not user:
        return denied()
    database = db.get_db()
    movements = list(database.movements.find().sort("created_at", -1).limit(250))
    products = list(database.products.find({"active": True}).sort("name", 1).limit(500))
    return view(request, "movements.html", user=user, movements=movements, products=products)


@app.post("/movimientos/nuevo")
def movement_post(request: Request, product_id: str = Form(...), kind: str = Form(...),
                  quantity: str = Form(...), notes: str = Form(""), csrf_token: str = Form(...)):
    security.require_csrf(request, csrf_token)
    user = authenticated(request)
    if not user:
        return denied()
    try:
        record_movement(db.get_db(), product_id, kind, quantity, notes, user)
        return go("/movimientos", request, "Movimiento registrado y stock actualizado.")
    except InventoryError as exc:
        return go("/movimientos", request, str(exc), "error")


@app.get("/respaldos", response_class=HTMLResponse)
def backup_page(request: Request):
    user = authenticated(request)
    if not user:
        return denied()
    ensure_admin(user)
    backups_list = backups.list_vault_backups(db.get_vault())
    return view(request, "backups.html", user=user, backup_items=backups_list,
                backups_enabled=len(settings.backup_passphrase) >= 24
                and not settings.backup_passphrase.startswith("CHANGE_THIS"))


@app.post("/respaldos/crear")
def create_backup_post(request: Request, csrf_token: str = Form(...)):
    security.require_csrf(request, csrf_token)
    user = authenticated(request)
    if not user:
        return denied()
    ensure_admin(user)
    try:
        _, stats = backups.create_vault_backup(db.get_db(), db.get_vault())
        return go("/respaldos", request, f"Respaldo cifrado creado: {stats['total']} documentos.")
    except backups.BackupError as exc:
        return go("/respaldos", request, str(exc), "error")


@app.get("/respaldos/{backup_id}/descargar")
def download_backup(request: Request, backup_id: str):
    user = authenticated(request)
    if not user:
        return denied()
    ensure_admin(user)
    try:
        stored = backups.get_backup(db.get_vault(), backup_id)
        data, name = stored.read(), stored.filename
    except backups.BackupError as exc:
        raise HTTPException(404, str(exc))
    return Response(content=data, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{name}"',
                             "Cache-Control": "no-store"})


@app.post("/respaldos/{backup_id}/restaurar")
def restore_backup_post(request: Request, backup_id: str,
                        confirmacion: str = Form(...), csrf_token: str = Form(...)):
    security.require_csrf(request, csrf_token)
    user = authenticated(request)
    if not user:
        return denied()
    ensure_admin(user)
    if confirmacion != "RESTAURAR":
        return go("/respaldos", request, "Debes escribir RESTAURAR exactamente.", "error")
    try:
        result = backups.restore_backup(db.get_db(), db.get_vault(), backup_id)
        return go("/respaldos", request,
                  f"Restauracion completada: {result['products']} productos y {result['movements']} movimientos.")
    except backups.BackupError as exc:
        return go("/respaldos", request, str(exc), "error")


@app.post("/respaldos/importar")
async def import_backup_post(request: Request, file: UploadFile = File(...),
                             csrf_token: str = Form(...)):
    security.require_csrf(request, csrf_token)
    user = authenticated(request)
    if not user:
        return denied()
    ensure_admin(user)
    if not (file.filename or "").lower().endswith(".ssb"):
        return go("/respaldos", request, "Selecciona un archivo .ssb valido.", "error")
    data = await file.read(backups.MAX_ENCRYPTED_BYTES + 1)
    if len(data) > backups.MAX_ENCRYPTED_BYTES:
        return go("/respaldos", request, "El archivo es demasiado grande.", "error")
    try:
        backups.import_vault_backup(db.get_vault(), data)
        return go("/respaldos", request, "Archivo validado, descifrado e importado correctamente.")
    except backups.BackupError as exc:
        return go("/respaldos", request, str(exc), "error")
    finally:
        await file.close()


@app.get("/usuarios", response_class=HTMLResponse)
def users_page(request: Request):
    user = authenticated(request)
    if not user:
        return denied()
    ensure_admin(user)
    users = list(db.get_db().users.find().sort("created_at", -1).limit(150))
    return view(request, "users.html", user=user, team=users)


@app.post("/usuarios/nuevo")
def create_user_post(request: Request, name: str = Form(...), email: str = Form(...),
                     password: str = Form(...), role: str = Form(...), csrf_token: str = Form(...)):
    security.require_csrf(request, csrf_token)
    user = authenticated(request)
    if not user:
        return denied()
    ensure_admin(user)
    name, email = name.strip(), email.strip().lower()
    if len(name) < 2 or len(name) > 80 or "@" not in email or len(email) > 150:
        return go("/usuarios", request, "Nombre o correo no validos.", "error")
    if len(password) < 12 or len(password) > 128:
        return go("/usuarios", request, "La contrasena debe tener 12 a 128 caracteres.", "error")
    if role not in ("admin", "operador"):
        return go("/usuarios", request, "Rol invalido.", "error")
    try:
        db.get_db().users.insert_one({"name": name, "email": email,
                                      "password_hash": hash_password(password),
                                      "role": role, "active": True, "created_at": utc_now()})
    except DuplicateKeyError:
        return go("/usuarios", request, "Ese correo ya fue registrado.", "error")
    return go("/usuarios", request, "Usuario creado correctamente.")


@app.post("/usuarios/{user_id}/estado")
def toggle_user(request: Request, user_id: str, csrf_token: str = Form(...)):
    security.require_csrf(request, csrf_token)
    user = authenticated(request)
    if not user:
        return denied()
    ensure_admin(user)
    oid = parse_object_id(user_id)
    if oid == user["_id"]:
        return go("/usuarios", request, "No puedes desactivar tu propia cuenta.", "error")
    target = db.get_db().users.find_one({"_id": oid})
    if not target:
        raise HTTPException(404, "Usuario no encontrado.")
    db.get_db().users.update_one({"_id": oid}, {"$set": {"active": not target["active"]}})
    return go("/usuarios", request, "Estado de usuario actualizado.")


def safe_csv(value):
    text = str(value or "")
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


@app.get("/exportar/productos.csv")
def export_products(request: Request):
    if not authenticated(request):
        return denied()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["SKU", "Producto", "Categoria", "Precio PEN", "Stock", "Stock minimo", "Activo"])
    for p in db.get_db().products.find().sort("name", 1).limit(10000):
        writer.writerow([safe_csv(p.get("sku")), safe_csv(p.get("name")),
                         safe_csv(p.get("category")), "{:.2f}".format(p.get("price_cents", 0) / 100),
                         p.get("stock", 0), p.get("min_stock", 0), "Si" if p.get("active") else "No"])
    return Response(content="\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="stocksafe_productos.csv"'})


@app.get("/api/v1/productos")
def api_products(request: Request):
    if not authenticated(request):
        raise HTTPException(status_code=401, detail="Requiere iniciar sesion.")
    products = list(db.get_db().products.find({"active": True}).sort("name", 1).limit(250))
    return {"count": len(products), "items": [
        {"id": str(p["_id"]), "sku": p["sku"], "nombre": p["name"],
         "categoria": p["category"], "precio": p["price_cents"] / 100,
         "stock": p["stock"], "stock_minimo": p["min_stock"]} for p in products]}
