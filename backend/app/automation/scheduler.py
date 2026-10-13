"""Background checks. Runs inside the API process on a timer (Phase 14 moves this to a real worker).

Safe to run twice: workflows run at most once per lead, so overlapping ticks cannot double-create work.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.models import Lead, Workflow
from app.workflows.engine import fire

log = logging.getLogger("bizos.scheduler")

CLOSED = ("CONVERTED", "LOST")
state: dict = {"last_tick_at": None, "last_runs": 0}


def check_inactive(db: Session, org_id: str) -> int:
    """Fire `lead.inactive` workflows for this org's open leads. Returns how many workflow runs happened."""
    has_any = db.scalar(
        select(Workflow.id).where(Workflow.org_id == org_id, Workflow.enabled.is_(True), Workflow.trigger == "lead.inactive").limit(1)
    )
    if not has_any:
        return 0
    leads = db.scalars(select(Lead).where(Lead.org_id == org_id, Lead.status.notin_(CLOSED))).all()
    runs = 0
    for lead in leads:
        runs += len(fire(db, org_id=org_id, lead=lead, trigger="lead.inactive"))
    db.commit()
    return runs


def tick() -> int:
    total = 0
    with SessionLocal() as db:
        org_ids = db.scalars(select(Workflow.org_id).where(Workflow.enabled.is_(True), Workflow.trigger == "lead.inactive").distinct()).all()
        for org_id in org_ids:
            try:
                total += check_inactive(db, org_id)
            except Exception:
                db.rollback()
                log.exception("Inactive check failed for org %s", org_id)
    state["last_tick_at"] = datetime.now(timezone.utc)
    state["last_runs"] = total
    return total


async def loop() -> None:
    interval = settings.scheduler_interval_seconds
    log.info("Scheduler started, every %ss", interval)
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(tick)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Scheduler tick failed")
