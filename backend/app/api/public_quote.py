"""Public quote page. The unguessable token in the link is the only credential and opens exactly one quote."""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import customer_comms as comms
from app.core import ratelimit
from app.core.config import settings
from app.core.db import get_db
from app.integrations import service as integrations
from app.models import Lead, LeadNote, LeadTask, Organization, Quote

log = logging.getLogger("bizos.quote")
router = APIRouter(prefix="/public/quote", tags=["public quote"])

LABEL = {"accept": "accepted", "decline": "declined", "changes": "changes_requested"}
NOTE_TITLE = {
    "accepted": "accepted",
    "declined": "declined",
    "changes_requested": "asked for changes to",
}


class QuoteView(BaseModel):
    business: str
    customer_name: str | None
    number: str
    items: list[dict]
    currency: str
    subtotal: float
    discount_pct: float
    total: float
    status: str  # sent | accepted | declined | changes_requested | expired
    customer_response: str | None
    customer_note: str | None
    expires_at: datetime | None


class RespondIn(BaseModel):
    action: str = Field(pattern="^(accept|decline|changes)$")
    note: str = Field(default="", max_length=1000)


def _load(db: Session, token: str) -> tuple[Quote, Organization, Lead | None]:
    q = db.scalar(select(Quote).where(Quote.public_token == token)) if token and len(token) <= 64 else None
    org = db.get(Organization, q.org_id) if q else None
    if q is None or org is None or q.status == "draft":  # a draft was never sent to anyone
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This quote link is not valid")
    lead = db.scalar(select(Lead).where(Lead.id == q.lead_id, Lead.org_id == org.id))
    return q, org, lead


def _expired(q: Quote) -> bool:
    exp = comms._aware(q.expires_at)
    return q.customer_response is None and exp is not None and comms.now() > exp


def _view(q: Quote, org: Organization, lead: Lead | None) -> QuoteView:
    return QuoteView(
        business=org.name, customer_name=lead.name if lead else None, number=q.number, items=q.items, currency=q.currency,
        subtotal=float(q.subtotal), discount_pct=float(q.discount_pct), total=float(q.total),
        status="expired" if _expired(q) else q.status, customer_response=q.customer_response, customer_note=q.customer_note,
        expires_at=q.expires_at,
    )


@router.get("/{token}", response_model=QuoteView, dependencies=[Depends(ratelimit.by_ip("pub_quote", 60, 60))])
def view(token: str, db: Session = Depends(get_db)):
    q, org, lead = _load(db, token)
    return _view(q, org, lead)


@router.post("/{token}/respond", response_model=QuoteView, dependencies=[Depends(ratelimit.by_ip("pub_quote_respond", 10, 60))])
def respond(token: str, body: RespondIn, db: Session = Depends(get_db)):
    q, org, lead = _load(db, token)
    if q.customer_response is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "You have already responded to this quote. The team will be in touch.")
    if _expired(q):
        raise HTTPException(status.HTTP_410_GONE, "This quote has expired. Please contact us for a new one.")
    note = body.note.strip()
    if body.action == "changes" and not note:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Please tell us what you would like changed.")

    outcome = LABEL[body.action]
    who = (lead.name if lead and lead.name else None) or "The customer"
    q.customer_response, q.customer_note, q.responded_at, q.status = outcome, note or None, comms.now(), outcome
    if lead is not None:
        text = f"{who} {NOTE_TITLE[outcome]} quote {q.number} from the quote page."
        db.add(LeadNote(org_id=org.id, lead_id=lead.id, author_name="Customer", body=text + (f"\n\nTheir note: {note}" if note else "")))
        todo = {
            "accepted": f"Quote {q.number} accepted by {who}: confirm the order and payment",
            "declined": f"Quote {q.number} declined by {who}: find out why, maybe follow up",
            "changes_requested": f"Quote {q.number}: {who} wants changes, send a revised quote",
        }[outcome]
        db.add(LeadTask(org_id=org.id, lead_id=lead.id, title=todo[:200], due_at=comms.now() + timedelta(days=0 if outcome != "declined" else 2), created_by="Quote page"))
    db.commit()
    integrations.notify_slack(db, org.id, f"Quote {q.number} {NOTE_TITLE[outcome]} by {who}" + (f": {note[:150]}" if note else ""))
    return _view(q, org, lead)
