"""Cookie sessions: a short-lived access JWT and a rotating refresh token, both in httpOnly cookies."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.models import RefreshToken, User

ACCESS_COOKIE = "bizos_access"
REFRESH_COOKIE = "bizos_refresh"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _set_cookie(resp: Response, name: str, value: str, max_age: int, path: str) -> None:
    resp.set_cookie(
        name, value, max_age=max_age, path=path, httponly=True,
        secure=settings.cookie_secure, samesite=settings.cookie_samesite.lower(),  # type: ignore[arg-type]
    )


def clear_cookies(resp: Response) -> None:
    for name, path in ((ACCESS_COOKIE, "/"), (REFRESH_COOKIE, "/auth")):
        resp.delete_cookie(name, path=path, secure=settings.cookie_secure, samesite=settings.cookie_samesite.lower(), httponly=True)  # type: ignore[arg-type]


def _issue_refresh(db: Session, user: User, family_id: str) -> str:
    raw = secrets.token_urlsafe(48)
    db.add(RefreshToken(
        user_id=user.id, family_id=family_id, token_hash=_hash(raw),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_expire_days),
    ))
    return raw


def start_session(db: Session, resp: Response, user: User, family_id: str | None = None) -> str:
    """Create cookies for a user. Returns the access token (also sent in the body for non-browser clients)."""
    refresh = _issue_refresh(db, user, family_id or secrets.token_hex(16))
    access = create_access_token(user.id, user.org_id)
    _set_cookie(resp, ACCESS_COOKIE, access, settings.jwt_expire_minutes * 60, "/")
    _set_cookie(resp, REFRESH_COOKIE, refresh, settings.refresh_expire_days * 86400, "/auth")
    return access


def rotate(db: Session, resp: Response, raw: str | None) -> User | None:
    """Swap a refresh token for a new pair. A token that was already used revokes its whole family (theft signal)."""
    if not raw:
        return None
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == _hash(raw)))
    if row is None:
        return None
    now = datetime.now(timezone.utc)
    if row.revoked_at is not None:
        revoke_family(db, row.family_id)
        db.commit()
        return None
    if _utc(row.expires_at) < now:
        return None
    user = db.get(User, row.user_id)
    if user is None:
        return None
    row.revoked_at = now
    start_session(db, resp, user, family_id=row.family_id)
    db.commit()
    return user


def revoke_family(db: Session, family_id: str) -> None:
    db.execute(update(RefreshToken).where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None)).values(revoked_at=datetime.now(timezone.utc)))


def end_session(db: Session, resp: Response, raw: str | None) -> None:
    if raw:
        row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == _hash(raw)))
        if row:
            revoke_family(db, row.family_id)
            db.commit()
    clear_cookies(resp)
