from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_access_token(user_id: str, org_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "org": org_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


VISITOR_AUDIENCE = "bizos-visitor"
VISITOR_DAYS = 30  # long enough for "continue your chat" links in emails


def create_visitor_token(conversation_id: str, org_id: str) -> str:
    """Lets an anonymous customer continue exactly one conversation. Not accepted as a staff token (different audience)."""
    now = datetime.now(timezone.utc)
    payload = {"cid": conversation_id, "org": org_id, "aud": VISITOR_AUDIENCE, "iat": now, "exp": now + timedelta(days=VISITOR_DAYS)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_visitor_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm], audience=VISITOR_AUDIENCE)
