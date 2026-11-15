"""Encrypted, application-level backups of products and movements.

This snapshot format preserves MongoDB-specific BSON types using Extended JSON.
It is not a mongodump of the entire Atlas cluster. Vault copies within the
same cluster are operational restores; GitHub artifacts/downloaded backups
provide separate storage for disaster recovery.
"""
import gzip
import io
import os
import secrets
from datetime import datetime, timezone
from bson import ObjectId, json_util
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from gridfs import GridFS
from .inventory import InventoryError, parse_object_id
from ..config import settings

MAGIC = b"SSB1"
AAD = b"StockSafe-Snapshot-v1"
COLLECTIONS = ("products", "movements")
MAX_DOCUMENTS_PER_COLLECTION = 10000
MAX_PLAINTEXT_BYTES = 40 * 1024 * 1024
MAX_ENCRYPTED_BYTES = 25 * 1024 * 1024


class BackupError(ValueError):
    pass


def passphrase():
    text = settings.backup_passphrase
    if len(text) < 24 or text.startswith("CHANGE_THIS"):
        raise BackupError("Configura BACKUP_PASSPHRASE (24 caracteres o mas).")
    return text


def _derive_key(password: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2**14, r=8, p=1).derive(password.encode("utf-8"))


def seal(content: bytes, password: str) -> bytes:
    if len(content) > MAX_PLAINTEXT_BYTES:
        raise BackupError("El respaldo supera el tamano permitido.")
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    encrypted = AESGCM(_derive_key(password, salt)).encrypt(nonce, gzip.compress(content), AAD)
    result = MAGIC + salt + nonce + encrypted
    if len(result) > MAX_ENCRYPTED_BYTES:
        raise BackupError("El respaldo cifrado supera el limite de 25 MB.")
    return result


def unseal(data: bytes, password: str) -> bytes:
    if len(data) < 48 or len(data) > MAX_ENCRYPTED_BYTES or not data.startswith(MAGIC):
        raise BackupError("Formato o tamano de respaldo invalido.")
    salt, nonce, encrypted = data[4:20], data[20:32], data[32:]
    try:
        compressed = AESGCM(_derive_key(password, salt)).decrypt(nonce, encrypted, AAD)
        with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as f:
            plaintext = f.read(MAX_PLAINTEXT_BYTES + 1)
        if len(plaintext) > MAX_PLAINTEXT_BYTES:
            raise BackupError("El archivo descomprimido es demasiado grande.")
        return plaintext
    except BackupError:
        raise
    except Exception as exc:
        raise BackupError("Clave incorrecta o archivo cifrado alterado.") from exc


def serialize_snapshot(database) -> tuple[bytes, dict]:
    collections = {}
    total = 0
    for name in COLLECTIONS:
        docs = list(database[name].find({}).limit(MAX_DOCUMENTS_PER_COLLECTION + 1))
        if len(docs) > MAX_DOCUMENTS_PER_COLLECTION:
            raise BackupError("Demasiados documentos para esta edicion academica (maximo 10000 por coleccion).")
        collections[name] = docs
        total += len(docs)
    payload = {"format": "stocksafe-snapshot-v1", "created_at": datetime.now(timezone.utc),
               "collections": collections}
    plain = json_util.dumps(payload).encode("utf-8")
    if len(plain) > MAX_PLAINTEXT_BYTES:
        raise BackupError("Los datos exceden el tamano maximo de respaldo.")
    return plain, {"products": len(collections["products"]),
                   "movements": len(collections["movements"]), "total": total}


def validate_snapshot(plaintext: bytes) -> dict:
    try:
        payload = json_util.loads(plaintext.decode("utf-8"))
    except Exception as exc:
        raise BackupError("El contenido del respaldo no se puede leer.") from exc
    if not isinstance(payload, dict) or payload.get("format") != "stocksafe-snapshot-v1":
        raise BackupError("Version de respaldo incompatible.")
    collections = payload.get("collections")
    if not isinstance(collections, dict) or set(collections) != set(COLLECTIONS):
        raise BackupError("El respaldo no contiene las dos colecciones esperadas.")
    for name in COLLECTIONS:
        docs = collections[name]
        if not isinstance(docs, list) or len(docs) > MAX_DOCUMENTS_PER_COLLECTION:
            raise BackupError(f"Cantidad invalida de documentos en {name}.")
        ids = set()
        for doc in docs:
            if not isinstance(doc, dict) or not isinstance(doc.get("_id"), ObjectId):
                raise BackupError("Documento sin ObjectId valido.")
            if doc["_id"] in ids:
                raise BackupError("El respaldo contiene identificadores duplicados.")
            ids.add(doc["_id"])
    return collections


def make_encrypted_snapshot(database):
    content, stats = serialize_snapshot(database)
    return seal(content, passphrase()), stats


def _bucket(vault_database):
    return GridFS(vault_database, collection="backup_files")


def create_vault_backup(database, vault_database, origin="manual"):
    encrypted, stats = make_encrypted_snapshot(database)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"stocksafe_{origin}_{timestamp}_{secrets.token_hex(3)}.ssb"
    file_id = _bucket(vault_database).put(
        encrypted, filename=filename, content_type="application/octet-stream",
        origin=origin, product_count=stats["products"], movement_count=stats["movements"],
        created_at=datetime.now(timezone.utc),
    )
    return file_id, stats


def import_vault_backup(vault_database, encrypted: bytes):
    collections = validate_snapshot(unseal(encrypted, passphrase()))
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    file_id = _bucket(vault_database).put(
        encrypted, filename=f"stocksafe_importado_{timestamp}_{secrets.token_hex(3)}.ssb",
        content_type="application/octet-stream", origin="importado",
        product_count=len(collections["products"]),
        movement_count=len(collections["movements"]), created_at=datetime.now(timezone.utc),
    )
    return file_id


def list_vault_backups(vault_database, limit=40):
    return list(_bucket(vault_database).find({}).sort("uploadDate", -1).limit(limit))


def get_backup(vault_database, backup_id: str):
    try:
        return _bucket(vault_database).get(parse_object_id(backup_id))
    except Exception as exc:
        raise BackupError("No se encontro el archivo de respaldo.") from exc


def restore_backup(database, vault_database, backup_id: str):
    encrypted_file = get_backup(vault_database, backup_id)
    collections = validate_snapshot(unseal(encrypted_file.read(), passphrase()))
    # Always preserve the current state before modifying either collection.
    pre_id, _ = create_vault_backup(database, vault_database, origin="antes_restaurar")
    original = {name: list(database[name].find({})) for name in COLLECTIONS}
    try:
        for name in COLLECTIONS:
            database[name].delete_many({})
            if collections[name]:
                database[name].insert_many(collections[name], ordered=True)
        for name in COLLECTIONS:
            if database[name].count_documents({}) != len(collections[name]):
                raise BackupError("Fallo la comprobacion del numero de documentos.")
    except Exception as exc:
        # Compensating rollback. This is NOT a multi-document ACID transaction.
        try:
            for name in COLLECTIONS:
                database[name].delete_many({})
                if original[name]:
                    database[name].insert_many(original[name], ordered=True)
        except Exception as rollback_exc:
            raise BackupError(
                f"La restauracion fallo y la recuperacion automatica tambien. "
                f"Recupera manualmente el respaldo previo {pre_id}."
            ) from rollback_exc
        raise BackupError("La restauracion fallo. El estado anterior fue recuperado.") from exc
    return {"products": len(collections["products"]),
            "movements": len(collections["movements"]), "pre_restore_id": str(pre_id)}
