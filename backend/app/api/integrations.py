from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth
from app.core.db import get_db
from app.integrations import providers, service
from app.integrations.providers import IntegrationError
from typing import Literal

router = APIRouter(prefix="/integrations", tags=["integrations"])


class EmailIn(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    security: Literal["starttls", "ssl", "none"] = "starttls"
    username: str = Field(default="", max_length=320)
    password: str = Field(default="", max_length=500)  # blank keeps the stored one
    from_email: EmailStr
    from_name: str = Field(default="", max_length=100)


class SlackIn(BaseModel):
    webhook_url: str = Field(default="", max_length=500)  # blank keeps the stored one


def _admin(auth: AuthContext) -> None:
    if auth.user.role not in ("owner", "admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owners and admins can change integrations")


def _check_webhook(url: str) -> None:
    u = urlparse(url)
    if u.scheme != "https" or u.hostname != "hooks.slack.com" or not u.path.startswith("/services/"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Use a Slack incoming webhook URL (https://hooks.slack.com/services/...)")


@router.get("")
def list_integrations(auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    out = {}
    for kind in ("email", "slack"):
        row = service.get_row(db, auth.org_id, kind)
        out[kind] = service.public_view(row) if row else None
    return out


@router.put("/email")
def save_email(body: EmailIn, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    _admin(auth)
    try:
        providers.check_public_host(body.host.strip())
    except IntegrationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    row = service.save_config(db, auth.org_id, "email", {**body.model_dump(), "host": body.host.strip(), "from_email": str(body.from_email)})
    db.commit()
    return service.public_view(row)


@router.put("/slack")
def save_slack(body: SlackIn, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    _admin(auth)
    if body.webhook_url:
        _check_webhook(body.webhook_url)
    elif service.get_row(db, auth.org_id, "slack") is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Webhook URL is required")
    row = service.save_config(db, auth.org_id, "slack", {"webhook_url": body.webhook_url})
    db.commit()
    return service.public_view(row)


@router.post("/{kind}/test")
def test_integration(kind: Literal["email", "slack"], auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    """Email: sends a test message to the signed-in user. Slack: posts a test line."""
    _admin(auth)
    row = service.get_row(db, auth.org_id, kind)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{kind} is not set up yet")
    cfg = service.get_config(db, auth.org_id, kind) or {}
    error = None
    try:
        if kind == "email":
            providers.send_email(cfg, auth.user.email, "BizOS test email", "Your email integration works. Agents can now send emails after a human approves them.")
        else:
            providers.post_slack(cfg["webhook_url"], f"BizOS test message from {auth.org.name}")
    except IntegrationError as e:
        error = str(e)
    except ValueError as e:  # undecryptable secret
        error = str(e)
    service.mark_tested(row, error)
    db.commit()
    if error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, error)
    return {"ok": True}


@router.delete("/{kind}", status_code=status.HTTP_204_NO_CONTENT)
def remove_integration(kind: Literal["email", "slack"], auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    _admin(auth)
    row = service.get_row(db, auth.org_id, kind)
    if row:
        db.delete(row)
        db.commit()
