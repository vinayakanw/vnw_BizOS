import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet() -> Fernet:
    seed = (settings.secrets_key or settings.jwt_secret).encode()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"bizos-secrets:" + seed).digest()))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        raise ValueError("Stored credential cannot be decrypted (was SECRETS_KEY or JWT_SECRET changed?)")
