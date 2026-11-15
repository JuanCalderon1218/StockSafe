from functools import lru_cache
from pymongo import MongoClient, ASCENDING, DESCENDING
from .config import settings


@lru_cache(maxsize=1)
def get_client():
    if not settings.mongodb_uri or "YOUR-CLUSTER" in settings.mongodb_uri:
        raise RuntimeError("Configure a valid MONGODB_URI in the .env file.")
    return MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=7000, connectTimeoutMS=7000)


def get_db():
    return get_client()[settings.mongodb_db]


def get_vault():
    return get_client()[settings.vault_db]


def initialize_database():
    client = get_client()
    client.admin.command("ping")
    db = get_db()
    db.users.create_index([("email", ASCENDING)], unique=True)
    db.products.create_index([("sku", ASCENDING)], unique=True)
    db.products.create_index([("active", ASCENDING), ("name", ASCENDING)])
    db.movements.create_index([("created_at", DESCENDING)])
    return db
