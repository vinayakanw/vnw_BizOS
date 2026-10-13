from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.sessions import ACCESS_COOKIE
from app.core.security import decode_access_token
from app.models import Organization, User

bearer = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    """Resolved identity for a request. org_id comes from the DB row, never from client input."""

    user: User
    org: Organization

    @property
    def org_id(self) -> str:
        return self.org.id


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _csrf_check(request: Request) -> None:
    """Cookie auth is sent automatically by browsers, so state-changing requests must come from our own frontend.
    SameSite already blocks most cross-site posts. This adds an Origin check on top."""
    if request.method in SAFE_METHODS:
        return
    origin = request.headers.get("origin")
    if origin is None or origin.rstrip("/") not in settings.cors_origin_list:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Request origin not allowed")


def get_auth(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> AuthContext:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing token")
    if creds is not None:
        token = creds.credentials  # explicit header (API clients, tests): not forgeable cross-site
    else:
        token = request.cookies.get(ACCESS_COOKIE)
        if not token:
            raise unauthorized
        _csrf_check(request)
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise unauthorized

    row = db.execute(
        select(User, Organization).join(Organization, Organization.id == User.org_id).where(User.id == payload.get("sub"))
    ).first()  # one round trip: the database may be far away
    if row is None or row[0].org_id != payload.get("org"):
        raise unauthorized
    return AuthContext(user=row[0], org=row[1])
