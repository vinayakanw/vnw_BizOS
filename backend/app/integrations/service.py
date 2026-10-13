import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import secrets
from app.integrations import providers
from app.integrations.providers import IntegrationError
from app.models import Integration

log = logging.getLogger("bizos.integrations")
SECRET_FIELDS = {"email": ("password",), "slack": ("webhook_url",)}


def get_row(db: Session, org_id: str, kind: str) -> Integration | None:
    return db.scalar(select(Integration).where(Integration.org_id == org_id, Integration.kind == kind))


def get_config(db: Session, org_id: str, kind: str) -> dict | None:
    """Decrypted config for server-side use only. Never return this from an API."""
    row = get_row(db, org_id, kind)
    if row is None:
        return None
    cfg = dict(row.config)
    for f in SECRET_FIELDS[kind]:
        if cfg.get(f):
            cfg[f] = secrets.decrypt(cfg[f])
    return cfg


def save_config(db: Session, org_id: str, kind: str, values: dict) -> Integration:
    row = get_row(db, org_id, kind)
    old = row.config if row else {}
    cfg = dict(values)
    for f in SECRET_FIELDS[kind]:
        if cfg.get(f):
            cfg[f] = secrets.encrypt(cfg[f])
        elif old.get(f):
            cfg[f] = old[f]  # blank means keep the stored secret
    if row is None:
        row = Integration(org_id=org_id, kind=kind, config=cfg)
        db.add(row)
    else:
        row.config, row.last_error, row.last_tested_at = cfg, None, None
    db.flush()
    return row


def public_view(row: Integration) -> dict:
    cfg = {k: v for k, v in row.config.items() if k not in ("password", "webhook_url")}
    cfg["has_password"] = bool(row.config.get("password"))
    if row.kind == "slack":
        cfg["webhook_set"] = bool(row.config.get("webhook_url"))
    return {"kind": row.kind, "config": cfg, "last_tested_at": row.last_tested_at, "last_error": row.last_error}


def mark_tested(row: Integration, error: str | None) -> None:
    row.last_tested_at, row.last_error = datetime.now(timezone.utc), error


def notify_slack(db: Session, org_id: str, text: str) -> None:
    """Internal team notification. Never raises: a Slack outage must not break an agent."""
    try:
        cfg = get_config(db, org_id, "slack")
        if cfg and cfg.get("webhook_url"):
            providers.post_slack(cfg["webhook_url"], text)
    except Exception as e:  # noqa: BLE001
        log.warning("Slack notification failed: %s", e)


__all__ = ["IntegrationError", "get_config", "get_row", "mark_tested", "notify_slack", "public_view", "save_config"]
