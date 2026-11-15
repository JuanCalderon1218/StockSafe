import pytest
from bson import ObjectId
from app.services.inventory import (
    InventoryError, parse_price, product_payload, create_product, record_movement,
)
from .conftest import csrf_for, login


def payload(sku="TEC-100"):
    return product_payload("Mouse ergonomico", sku, "Accesorios", "98.50", 3, "Buen producto", "")


def test_money_and_input_validation():
    assert parse_price("54.90") == 5490
    assert parse_price("54,90") == 5490
    with pytest.raises(InventoryError):
        parse_price("-2")
    with pytest.raises(InventoryError):
        product_payload("X", "@@", "A", "2", 0, "", "")


def test_movement_prevents_negative_stock(state):
    web, database, _ = state
    product_id = create_product(database, payload(), 4)
    user = database.users.find_one()
    assert record_movement(database, str(product_id), "salida", 3, "Venta", user) == 1
    assert record_movement(database, str(product_id), "entrada", 2, "Compra", user) == 3
    with pytest.raises(InventoryError, match="Stock insuficiente"):
        record_movement(database, str(product_id), "salida", 4, "Venta", user)
    assert database.products.find_one({"_id": product_id})["stock"] == 3
    assert database.movements.count_documents({}) == 2


def test_product_crud_and_api_requires_login(state):
    web, database, _ = state
    assert web.get("/api/v1/productos").status_code == 401
    token = login(web)
    result = web.post("/productos/nuevo", data={
        "csrf_token": token, "name": "Monitor IPS", "sku": "TEC-010",
        "category": "Tecnologia", "price": "729.90", "min_stock": "5",
        "initial_stock": "12", "description": "Pantalla para oficina", "image_url": "",
    }, follow_redirects=False)
    assert result.status_code == 303
    product = database.products.find_one({"sku": "TEC-010"})
    assert product["stock"] == 12
    assert product["price_cents"] == 72990
    assert web.get("/api/v1/productos").json()["count"] == 1
    assert web.get("/dashboard").status_code == 200
    assert web.get("/exportar/productos.csv").status_code == 200
    token = csrf_for(web, "/productos")
    edited = web.post(f"/productos/{product['_id']}/editar", data={
        "csrf_token": token, "name": "Monitor IPS editado", "sku": "TEC-010",
        "category": "Tecnologia", "price": "699.00", "min_stock": "6",
        "description": "Modelo actualizado", "image_url": "",
    }, follow_redirects=False)
    assert edited.status_code == 303
    assert database.products.find_one({"sku": "TEC-010"})["price_cents"] == 69900


def test_csrf_is_enforced(state):
    web, _, _ = state
    login(web)
    result = web.post("/productos/nuevo", data={
        "csrf_token": "fake", "name": "Teclado nuevo", "sku": "TEST-101",
        "category": "Accesorios", "price": "30", "min_stock": "1",
        "initial_stock": "1",
    })
    assert result.status_code == 403
