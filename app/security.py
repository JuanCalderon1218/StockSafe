import secrets
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from bson import ObjectId
from fastapi import HTTPException, Request
from . import db

_hasher = PasswordHasher(time_cost=2, memory_cost=32768, parallelism=2)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(hash_value: str, password: str) -> bool:
    try:
        return bool(_hasher.verify(hash_value, password))
    except (VerifyMismatchError, VerificationError, InvalidHashError, ValueError):
        return False


def session_token(request: Request) -> str:
    if "csrf" not in request.session:
        request.session["csrf"] = secrets.token_urlsafe(32)
    return request.session["csrf"]


def require_csrf(request: Request, csrf_token: str):
    existing = request.session.get("csrf")
    if not existing or not secrets.compare_digest(existing, csrf_token or ""):
        raise HTTPException(status_code=403, detail="Token de seguridad invalido. Recarga la pagina.")


def current_user(request: Request):
    uid = request.session.get("uid")
    if not uid or not ObjectId.is_valid(uid):
        return None
    user = db.get_db().users.find_one({"_id": ObjectId(uid), "active": True})
    if user is None:
        request.session.clear()
    return user


def is_admin(user) -> bool:
    return bool(user and user.get("role") == "admin")


def require_admin(user):
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Acceso exclusivo del administrador.")


def set_flash(request: Request, message: str, kind: str = "success"):
    request.session["flash"] = {"message": message, "kind": kind}
