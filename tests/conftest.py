import re
import pytest
import mongomock
import mongomock.gridfs
from fastapi.testclient import TestClient
from app import db
from app import main as main_module
from app.config import settings
from app.security import hash_password

mongomock.gridfs.enable_gridfs_integration()


@pytest.fixture
def state(monkeypatch):
    client = mongomock.MongoClient()
    database = client["stocksafe_db"]
    vault = client["stocksafe_vault"]
    database.products.create_index("sku", unique=True)
    database.users.create_index("email", unique=True)
    database.users.insert_one({
        "name": "Administrador Demo", "email": "admin@test.local",
        "password_hash": hash_password("AdminPassword123!"),
        "role": "admin", "active": True,
    })
    monkeypatch.setattr(db, "get_db", lambda: database)
    monkeypatch.setattr(db, "get_vault", lambda: vault)
    monkeypatch.setattr(main_module, "bootstrap", lambda: database)
    monkeypatch.setattr(settings, "backup_passphrase", "test-secret-backup-passphrase-123456")
    with TestClient(main_module.app) as web:
        yield web, database, vault


def csrf_for(web, path):
    page = web.get(path)
    assert page.status_code == 200, page.text[:1000]
    match = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert match
    return match.group(1)


def login(web, email="admin@test.local", password="AdminPassword123!"):
    token = csrf_for(web, "/login")
    result = web.post("/login", data={"email": email, "password": password, "csrf_token": token},
                      follow_redirects=False)
    assert result.status_code == 303, result.text[:1000]
    return csrf_for(web, "/productos")
