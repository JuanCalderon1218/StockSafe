from datetime import datetime, timezone
from .config import settings
from .db import initialize_database
from .security import hash_password


def utc_now():
    return datetime.now(timezone.utc)


def bootstrap():
    db = initialize_database()
    email = settings.admin_email.strip().lower()
    if not db.users.find_one({"email": email}):
        if not settings.admin_password or settings.admin_password.startswith("CHANGE_THIS"):
            raise RuntimeError("Set ADMIN_PASSWORD to create the initial administrator.")
        db.users.insert_one({
            "name": "Administrador StockSafe", "email": email,
            "password_hash": hash_password(settings.admin_password),
            "role": "admin", "active": True, "created_at": utc_now(),
        })
    if settings.seed_demo_data and db.products.count_documents({}) == 0:
        sample = [
            ("Laptop Lenovo IdeaPad", "TEC-001", "Tecnologia", 2699, 16, 5),
            ("Monitor Samsung 24", "TEC-002", "Tecnologia", 749, 9, 4),
            ("Mouse inalambrico", "TEC-003", "Accesorios", 59.9, 40, 10),
            ("Teclado mecanico", "TEC-004", "Accesorios", 179, 24, 8),
            ("Audifonos Bluetooth", "TEC-005", "Audio", 149, 7, 6),
            ("Disco SSD 1 TB", "TEC-006", "Almacenamiento", 289, 14, 6),
            ("Memoria USB 64 GB", "TEC-007", "Almacenamiento", 38, 55, 12),
            ("Camara web Full HD", "TEC-008", "Accesorios", 129, 11, 4),
            ("Impresora multifuncion", "TEC-009", "Oficina", 849, 4, 4),
            ("Silla ergonomica", "TEC-010", "Oficina", 539, 8, 3),
            ("Router WiFi 6", "TEC-011", "Redes", 325, 6, 4),
            ("Cable HDMI 2m", "TEC-012", "Accesorios", 24.5, 60, 15),
        ]
        db.products.insert_many([
            {"name": name, "sku": sku, "category": category,
             "price_cents": round(price * 100), "stock": stock,
             "min_stock": min_stock, "description": "Producto de demostracion",
             "image_url": "", "active": True, "created_at": utc_now(), "updated_at": utc_now()}
            for name, sku, category, price, stock, min_stock in sample
        ])
    return db
