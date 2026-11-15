from bson import ObjectId
import pytest
from app.services import backups
from app.services.inventory import create_product, product_payload
from .conftest import login, csrf_for


def test_encrypted_snapshot_and_detect_tampering(state):
    _, database, _ = state
    create_product(database, product_payload("Router AX", "NET-100", "Redes", "250", 2, "", ""), 10)
    encrypted, stats = backups.make_encrypted_snapshot(database)
    assert encrypted.startswith(b"SSB1")
    assert b"Router AX" not in encrypted
    assert stats["products"] == 1
    restored = backups.validate_snapshot(backups.unseal(encrypted, backups.passphrase()))
    assert restored["products"][0]["name"] == "Router AX"
    tampered = bytearray(encrypted)
    tampered[-2] ^= 2
    with pytest.raises(backups.BackupError):
        backups.unseal(bytes(tampered), backups.passphrase())


def test_restoration_from_encrypted_vault(state):
    web, database, vault = state
    login(web)
    create_product(database, product_payload("SSD", "ALM-200", "Tecnologia", "230", 3, "", ""), 5)
    token = csrf_for(web, "/respaldos")
    result = web.post("/respaldos/crear", data={"csrf_token": token}, follow_redirects=False)
    assert result.status_code == 303
    files = backups.list_vault_backups(vault)
    assert len(files) == 1
    backup_id = str(files[0]._id)
    file_response = web.get(f"/respaldos/{backup_id}/descargar")
    assert file_response.status_code == 200
    assert file_response.content.startswith(b"SSB1")
    database.products.delete_many({})
    result = web.post(f"/respaldos/{backup_id}/restaurar", data={
        "csrf_token": token, "confirmacion": "RESTAURAR",
    }, follow_redirects=False)
    assert result.status_code == 303
    assert database.products.count_documents({}) == 1
    assert len(backups.list_vault_backups(vault)) == 2


def test_non_admin_cannot_restore(state):
    web, database, _ = state
    login(web)
    database.users.insert_one({"name": "Operador", "email": "op@test.local",
                               "password_hash": database.users.find_one()["password_hash"],
                               "role": "operador", "active": True})
    csrf = csrf_for(web, "/productos")
    web.post("/logout", data={"csrf_token": csrf})
    login(web, "op@test.local")
    assert web.get("/respaldos").status_code == 403
    assert web.get("/usuarios").status_code == 403


def test_automation_backup_requires_token(state, monkeypatch):
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
