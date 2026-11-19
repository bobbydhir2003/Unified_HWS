import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings

_hasher = PasswordHasher()
ALGO = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def validate_password_strength(password: str) -> str | None:
    """Return an error message, or None when the password is acceptable."""
    if len(password) < 10:
        return "Password must be at least 10 characters."
    classes = sum(
        [
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        ]
    )
    if classes < 3:
        return "Use at least three of: lowercase, uppercase, digits, symbols."
    return None


def now() -> datetime:
    return datetime.now(UTC)


def create_token(subject: str, kind: str, minutes: int, extra: dict[str, Any] | None = None) -> str:
    payload = {"sub": subject, "typ": kind, "iat": now(), "exp": now() + timedelta(minutes=minutes)}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=ALGO)


def decode_token(token: str, kind: str) -> dict[str, Any] | None:
    try:
        data = jwt.decode(token, settings.secret_key, algorithms=[ALGO])
    except jwt.PyJWTError:
        return None
    if data.get("typ") != kind:
        return None
    return data


def new_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
