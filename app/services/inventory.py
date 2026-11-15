from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pymongo.errors import DuplicateKeyError
from bson import ObjectId


class InventoryError(ValueError):
    pass


def parse_object_id(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise InventoryError("Identificador invalido.")
    return ObjectId(value)


def parse_price(value: str) -> int:
    try:
        parsed = Decimal(str(value).strip().replace(",", "."))
        if not parsed.is_finite() or parsed < 0 or parsed > Decimal("99999999"):
            raise ValueError()
        return int((parsed * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (ValueError, InvalidOperation, TypeError):
        raise InventoryError("Ingresa un precio valido mayor o igual a cero.")


def product_payload(name, sku, category, price, min_stock, description, image_url):
    name, sku, category = str(name).strip(), str(sku).strip().upper(), str(category).strip()
    description, image_url = str(description).strip(), str(image_url).strip()
    if not (2 <= len(name) <= 100):
        raise InventoryError("El nombre debe tener entre 2 y 100 caracteres.")
    if not (2 <= len(sku) <= 32) or not all(c.isalnum() or c in "-_" for c in sku):
        raise InventoryError("El SKU debe tener 2-32 caracteres (letras, numeros, guion).")
    if not (2 <= len(category) <= 50):
        raise InventoryError("La categoria debe tener entre 2 y 50 caracteres.")
    if len(description) > 500:
        raise InventoryError("La descripcion debe tener como maximo 500 caracteres.")
    if image_url and not (image_url.startswith("https://") or image_url.startswith("http://")):
        raise InventoryError("La imagen debe tener una URL http o https.")
    if len(image_url) > 500:
        raise InventoryError("La URL de imagen es demasiado larga.")
    try:
        min_stock = int(min_stock)
        if min_stock < 0 or min_stock > 1_000_000:
            raise ValueError()
    except (ValueError, TypeError):
        raise InventoryError("El stock minimo debe ser de 0 a 1000000.")
    return {"name": name, "sku": sku, "category": category,
            "price_cents": parse_price(price), "min_stock": min_stock,
            "description": description, "image_url": image_url}


def create_product(database, payload, initial_stock=0):
    try:
        initial_stock = int(initial_stock)
        if initial_stock < 0 or initial_stock > 1_000_000:
            raise ValueError()
    except (TypeError, ValueError):
        raise InventoryError("El stock inicial debe estar entre 0 y 1000000.")
    now = datetime.now(timezone.utc)
    data = {**payload, "stock": initial_stock, "active": True,
            "created_at": now, "updated_at": now}
    try:
        return database.products.insert_one(data).inserted_id
    except DuplicateKeyError:
        raise InventoryError("Ya existe un producto con ese codigo SKU.")


def update_product(database, object_id, payload):
    try:
        changed = database.products.update_one({"_id": parse_object_id(object_id)},
                                               {"$set": {**payload, "updated_at": datetime.now(timezone.utc)}})
    except DuplicateKeyError:
        raise InventoryError("El SKU ya esta registrado en otro producto.")
    if changed.matched_count == 0:
        raise InventoryError("No se encontro el producto.")


def record_movement(database, product_id, kind, quantity, notes, user):
    if kind not in ("entrada", "salida"):
        raise InventoryError("Selecciona un tipo de movimiento valido.")
    try:
        quantity = int(quantity)
        if not 1 <= quantity <= 1_000_000:
            raise ValueError()
    except (TypeError, ValueError):
        raise InventoryError("La cantidad debe estar entre 1 y 1000000.")
    if len(notes or "") > 250:
        raise InventoryError("La observacion no puede superar los 250 caracteres.")
    oid = parse_object_id(product_id)
    old = database.products.find_one({"_id": oid, "active": True})
    if old is None:
        raise InventoryError("El producto no existe o esta inactivo.")
    if kind == "salida":
        # The condition prevents simultaneous sales from creating negative stock.
        result = database.products.find_one_and_update(
            {"_id": oid, "active": True, "stock": {"$gte": quantity}},
            {"$inc": {"stock": -quantity}, "$set": {"updated_at": datetime.now(timezone.utc)}},
            return_document=True,
        )
        if result is None:
            raise InventoryError("Stock insuficiente para registrar la salida.")
        delta = -quantity
    else:
        result = database.products.find_one_and_update(
            {"_id": oid, "active": True, "stock": {"$lte": 1_000_000 - quantity}},
            {"$inc": {"stock": quantity}, "$set": {"updated_at": datetime.now(timezone.utc)}},
            return_document=True,
        )
        if result is None:
            raise InventoryError("La entrada supera el limite de stock permitido.")
        delta = quantity
    # Record the ledger entry. Retry/compensate if logging fails (best effort).
    try:
        database.movements.insert_one({
            "product_id": oid, "product_name": result["name"], "sku": result["sku"],
            "type": kind, "quantity": quantity, "stock_after": result["stock"],
            "notes": (notes or "").strip(), "user_id": str(user["_id"]),
            "user_name": user["name"], "created_at": datetime.now(timezone.utc),
        })
    except Exception:
        database.products.update_one({"_id": oid}, {"$inc": {"stock": -delta}})
        raise InventoryError("No se pudo registrar el movimiento. Se intento revertir el stock.")
    return result["stock"]
