import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("STOCKSAFE_ENV", "development")
    mongodb_uri: str = os.getenv("MONGODB_URI", "")
    mongodb_db: str = os.getenv("MONGODB_DB", "stocksafe_db")
    vault_db: str = os.getenv("MONGODB_VAULT_DB", "stocksafe_vault")
    session_secret: str = os.getenv("SESSION_SECRET", "")
    backup_passphrase: str = os.getenv("BACKUP_PASSPHRASE", "")
    admin_email: str = os.getenv("ADMIN_EMAIL", "admin@stocksafe.local")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "")
    seed_demo_data: bool = os.getenv("SEED_DEMO_DATA", "false").lower() == "true"


settings = Settings()


def check_config():
    if settings.mongodb_db == settings.vault_db:
        raise RuntimeError("MONGODB_DB and MONGODB_VAULT_DB must be different databases.")
    if settings.environment == "production":
        if len(settings.session_secret) < 32:
            raise RuntimeError("SESSION_SECRET must have at least 32 characters.")
        if not settings.mongodb_uri:
            raise RuntimeError("MONGODB_URI is required in production.")
        if len(settings.backup_passphrase) < 24:
            raise RuntimeError("BACKUP_PASSPHRASE must have at least 24 characters.")
        if len(settings.admin_password) < 12:
            raise RuntimeError("ADMIN_PASSWORD must have at least 12 characters.")
