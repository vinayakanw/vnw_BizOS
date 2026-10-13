from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth
from app.core import ratelimit, sessions
from app.core.db import get_db
from app.core.security import hash_password, verify_password
from app.models import Organization, User
from app.schemas import LoginRequest, OrgOut, RegisterRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(ratelimit.by_ip("register", 10, 3600))],
)
def register(body: RegisterRequest, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    org = Organization(name=body.org_name.strip())
    db.add(org)
    db.flush()
    user = User(
        org_id=org.id,
        email=email,
        full_name=body.full_name.strip(),
        password_hash=hash_password(body.password),
        role="owner",
    )
    db.add(user)
    db.flush()
    token = sessions.start_session(db, response, user)
    db.commit()
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    # Two buckets: many tries from one address, and many tries against one account from anywhere.
    if ratelimit.settings.rate_limit_enabled:
        wait = ratelimit.hit(f"login:ip:{ratelimit.client_ip(request)}", 20, 60) or ratelimit.hit(f"login:acct:{body.email.lower()}", 8, 300)
        if wait:
            raise ratelimit._deny(wait)
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    token = sessions.start_session(db, response, user)
    db.commit()
    return TokenResponse(access_token=token)


@router.post("/refresh", dependencies=[Depends(ratelimit.by_ip("refresh", 60, 60))])
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    user = sessions.rotate(db, response, request.cookies.get(sessions.REFRESH_COOKIE))
    if user is None:
        sessions.clear_cookies(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired. Please sign in again.")
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    sessions.end_session(db, response, request.cookies.get(sessions.REFRESH_COOKIE))
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(auth: AuthContext = Depends(get_auth)) -> UserOut:
    return UserOut(
        id=auth.user.id,
        email=auth.user.email,
        full_name=auth.user.full_name,
        role=auth.user.role,
        org=OrgOut.model_validate(auth.org),
    )
