from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.founder.agent import make_briefing
from app.agents.founder.snapshot import build_snapshot
from app.core import ratelimit
from app.api.deps import AuthContext, get_auth
from app.core.db import get_db
from app.integrations import service as integrations
from app.models import Briefing

router = APIRouter(prefix="/agents/founder", tags=["founder agent"])


class BriefingIn(BaseModel):
    days: int = Field(default=7, ge=1, le=30)


class BriefingOut(BaseModel):
    id: str
    period_days: int
    headline: str
    summary: str
    ai_written: bool
    facts: dict
    priorities: list[dict]
    created_at: datetime

    model_config = {"from_attributes": True}


@router.post("/briefing", response_model=BriefingOut, dependencies=[Depends(ratelimit.by_org("llm", 30, 60))])
def create_briefing(body: BriefingIn, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    return make_briefing(db, auth.org, body.days)


@router.get("/briefings", response_model=list[BriefingOut])
def list_briefings(auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    return db.scalars(select(Briefing).where(Briefing.org_id == auth.org_id).order_by(Briefing.created_at.desc()).limit(20)).all()


@router.get("/briefings/{briefing_id}", response_model=BriefingOut)
def get_briefing(briefing_id: str, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    b = db.scalar(select(Briefing).where(Briefing.id == briefing_id, Briefing.org_id == auth.org_id))
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Briefing not found")
    return b


@router.get("/attention")
def attention(auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    """Live attention items with no AI, so the page is useful even before a briefing is generated."""
    s = build_snapshot(db, auth.org_id, 7)
    return {"facts": s["facts"], "items": s["items"]}


@router.post("/briefings/{briefing_id}/share")
def share_to_slack(briefing_id: str, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    b = db.scalar(select(Briefing).where(Briefing.id == briefing_id, Briefing.org_id == auth.org_id))
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Briefing not found")
    cfg = integrations.get_config(db, auth.org_id, "slack")
    if not cfg:
        raise HTTPException(status.HTTP_409_CONFLICT, "Slack is not connected. Set it up under Integrations")
    lines = [f"*{b.headline}*", b.summary] + [f"- {p['item']['title']}: {p['why']}" for p in b.priorities]
    try:
        integrations.providers.post_slack(cfg["webhook_url"], "\n".join(lines))
    except integrations.IntegrationError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    return {"ok": True}
