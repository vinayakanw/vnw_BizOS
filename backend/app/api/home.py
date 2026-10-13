"""The owner's home screen: what needs a person today, how setup is going, and the sidebar counters in one request."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.chat_admin import WEB_CHANNELS, _items
from app.api.deps import AuthContext, get_auth
from app.core.db import get_db
from app.models import (
    BusinessProfile, ChatSettings, Conversation, Document, Faq, Integration, Lead, LeadTask, Order, Product, Quote, Ticket, ToolCall,
)

router = APIRouter(prefix="/home", tags=["home"])


class Counts(BaseModel):
    inbox: int
    tickets: int
    approvals: int


class QueueItem(BaseModel):
    kind: str  # chat | approval | quote | ticket | lead
    urgency: str  # high | medium | normal
    title: str
    detail: str
    to: str
    action: str
    at: datetime | None = None


class Step(BaseModel):
    key: str
    title: str
    hint: str
    to: str
    done: bool
    optional: bool = False


class Stats(BaseModel):
    chats: int
    leads: int
    quotes_sent: int
    tickets_resolved: int


class Today(BaseModel):
    first_name: str
    business: str
    counts: Counts
    queue: list[QueueItem]
    stats: Stats
    steps: list[Step]
    chat_path: str | None  # /chat/<slug> once chat is on


def _waiting_chats(db: Session, org_id: str):
    """Only chats that are escalated or taken over can be waiting, so only those are loaded."""
    convs = db.scalars(
        select(Conversation).where(
            Conversation.org_id == org_id, Conversation.channel.in_(WEB_CHANNELS), (Conversation.escalated.is_(True)) | (Conversation.human_active.is_(True))
        )
    ).all()
    return [i for i in _items(db, org_id, list(convs)) if i.waiting]


def _count(db: Session, stmt) -> int:
    return db.scalar(stmt) or 0


@router.get("/counts", response_model=Counts)
def counts(auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    org = auth.org_id
    return Counts(
        inbox=len(_waiting_chats(db, org)),
        tickets=_count(db, select(func.count()).select_from(Ticket).where(Ticket.org_id == org, Ticket.status == "open")),
        approvals=_count(db, select(func.count()).select_from(ToolCall).where(ToolCall.org_id == org, ToolCall.status == "pending_approval")),
    )


def _aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


@router.get("/today", response_model=Today)
def today(auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    org = auth.org_id
    queue: list[QueueItem] = []

    waiting = _waiting_chats(db, org)
    for w in waiting:
        queue.append(QueueItem(
            kind="chat", urgency="high", title=f"{w.customer_name or w.customer_email or 'A customer'} is waiting for a reply",
            detail=w.last_message, to=f"/inbox/{w.id}", action="Reply", at=w.last_message_at,
        ))

    approvals = db.scalars(select(ToolCall).where(ToolCall.org_id == org, ToolCall.status == "pending_approval").order_by(ToolCall.created_at).limit(5)).all()
    for a in approvals:
        queue.append(QueueItem(kind="approval", urgency="high", title="The AI needs your OK", detail=a.approval_reason or a.summary, to="/approvals", action="Review", at=a.created_at))

    # Customer answers to quotes that nobody has followed up on yet.
    tasks = db.scalars(
        select(LeadTask).where(LeadTask.org_id == org, LeadTask.created_by == "Quote page", LeadTask.status == "open").order_by(LeadTask.created_at.desc()).limit(5)
    ).all()
    for t in tasks:
        queue.append(QueueItem(kind="quote", urgency="medium", title=t.title, detail="Reply from the customer's quote page", to=f"/leads/{t.lead_id}", action="Open lead", at=t.created_at))

    tickets = db.scalars(
        select(Ticket).where(Ticket.org_id == org, Ticket.status == "open", Ticket.priority == "high").order_by(Ticket.created_at.desc()).limit(5)
    ).all()
    for t in tickets:
        queue.append(QueueItem(kind="ticket", urgency="medium", title=f"Urgent ticket {t.number}", detail=t.subject, to=f"/tickets/{t.id}", action="Open", at=t.created_at))

    hot = db.scalars(select(Lead).where(Lead.org_id == org, Lead.status == "HOT").order_by(Lead.score.desc()).limit(3)).all()
    for l in hot:
        who = l.name or l.email or l.phone or (f"{l.company}" if l.company else None)
        title = f"Hot lead: {who}" if who else "Hot lead from chat"
        detail = " · ".join(x for x in [l.requirement, l.next_action] if x)[:140]
        queue.append(QueueItem(kind="lead", urgency="normal", title=title, detail=detail, to=f"/leads/{l.id}", action="Open lead", at=l.last_interaction_at))

    rank = {"high": 0, "medium": 1, "normal": 2}
    queue.sort(key=lambda q: (rank[q.urgency], -(_aware(q.at).timestamp() if q.at else 0)))

    week = datetime.now(timezone.utc) - timedelta(days=7)
    stats = Stats(
        chats=_count(db, select(func.count()).select_from(Conversation).where(Conversation.org_id == org, Conversation.channel.in_(WEB_CHANNELS), Conversation.created_at >= week)),
        leads=_count(db, select(func.count()).select_from(Lead).where(Lead.org_id == org, Lead.created_at >= week)),
        quotes_sent=_count(db, select(func.count()).select_from(Quote).where(Quote.org_id == org, Quote.expires_at.is_not(None), Quote.created_at >= week)),
        tickets_resolved=_count(db, select(func.count()).select_from(Ticket).where(Ticket.org_id == org, Ticket.status == "resolved", Ticket.updated_at >= week)),
    )

    prof = db.get(BusinessProfile, org)
    cs = db.scalar(select(ChatSettings).where(ChatSettings.org_id == org))
    has_email = db.scalar(select(Integration.id).where(Integration.org_id == org, Integration.kind == "email")) is not None
    has_web_chat = db.scalar(select(Conversation.id).where(Conversation.org_id == org, Conversation.channel.in_(WEB_CHANNELS)).limit(1)) is not None
    steps = [
        Step(key="profile", title="Tell the AI about your business", hint="A short description and how you like to talk to customers.", to="/profile", done=bool(prof and (prof.description or "").strip())),
        Step(key="products", title="Add what you sell", hint="Products with prices. The AI only quotes what is listed here.", to="/products", done=_count(db, select(func.count()).select_from(Product).where(Product.org_id == org)) > 0),
        Step(key="faqs", title="Add answers to common questions", hint="Returns, delivery, warranty. Questions and answers, or upload a document.",
             to="/faqs", done=_count(db, select(func.count()).select_from(Faq).where(Faq.org_id == org)) + _count(db, select(func.count()).select_from(Document).where(Document.org_id == org)) > 0),
        Step(key="chat", title="Turn on your customer chat", hint="This gives you the link customers use to talk to you.", to="/customer-chat", done=bool(cs and cs.enabled)),
        Step(key="try", title="Send yourself a test message", hint="Open your chat link and write like a customer would.", to=f"/chat/{cs.slug}" if cs and cs.enabled else "/customer-chat", done=has_web_chat),
        Step(key="email", title="Connect your email", hint="So customers who leave still get your reply and their quotes.", to="/integrations", done=has_email),
        Step(key="orders", title="Add your orders", hint="So customers can check where their order is without calling you.", to="/orders", done=_count(db, select(func.count()).select_from(Order).where(Order.org_id == org)) > 0, optional=True),
    ]

    return Today(
        first_name=((auth.user.full_name or "").split(" ")[0] or "there").capitalize(), business=auth.org.name,
        counts=Counts(
            inbox=len(waiting),
            tickets=_count(db, select(func.count()).select_from(Ticket).where(Ticket.org_id == org, Ticket.status == "open")),
            approvals=_count(db, select(func.count()).select_from(ToolCall).where(ToolCall.org_id == org, ToolCall.status == "pending_approval")),
        ),
        queue=queue[:12], stats=stats, steps=steps, chat_path=f"/chat/{cs.slug}" if cs and cs.enabled else None,
    )
