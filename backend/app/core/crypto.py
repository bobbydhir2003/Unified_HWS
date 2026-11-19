"""Authenticated encryption for stored secrets (e.g. AI provider API keys), using Fernet (AES-128-CBC + HMAC-SHA256).

Key: CREDENTIALS_ENCRYPTION_KEY (a Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`).
Development fallback derives a key from SECRET_KEY via HKDF; production refuses to start without a dedicated key.
Ciphertext is never returned by any API; only a masked hint (last 4 characters) is shown.
"""

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings


def _fernet() -> Fernet:
    if settings.credentials_encryption_key:
        return Fernet(settings.credentials_encryption_key.encode())
    derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"undeclared-credentials-v1", info=b"credential-encryption").derive(
        settings.secret_key.encode())
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise ValueError("Stored credential can't be decrypted (encryption key changed?) — re-enter it in AI Settings") from e


def mask(secret: str) -> str:
    return f"…{secret[-4:]}" if len(secret) >= 8 else "…"
