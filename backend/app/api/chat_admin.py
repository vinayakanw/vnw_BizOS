"""Staff side of customer chat: settings for the public chat page, and the inbox where humans take over."""

import re
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth
from app import customer_comms as comms
from app.core.db import get_db
from app.models import ChatAttachment, ChatSettings, Conversation, Lead, Message, Ticket
from app.schemas_agent import MessageOut

router = APIRouter(tags=["customer chat"])

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")
WEB_CHANNELS = ("web-sales", "web-support")


# ---------------------------------------------------------------- settings

class ChatSettingsOut(BaseModel):
    slug: str
    enabled: bool
    welcome_message: str
    sales_enabled: bool
    support_enabled: bool

    model_config = {"from_attributes": True}


class ChatSettingsIn(BaseModel):
    slug: str = Field(min_length=3, max_length=40)
    enabled: bool
    welcome_message: str = Field(min_length=1, max_length=500)
    sales_enabled: bool = True
    support_enabled: bool = True


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30].strip("-")
    return s if len(s) >= 3 else "shop"


def get_or_create_settings(db: Session, org_id: str, org_name: str) -> ChatSettings:
    row = db.scalar(select(ChatSettings).where(ChatSettings.org_id == org_id))
    if row is None:
        slug = _slugify(org_name)
        while db.scalar(select(ChatSettings).where(ChatSettings.slug == slug)):
            slug = f"{_slugify(org_name)[:30]}-{secrets.token_hex(2)}"
        row = ChatSettings(org_id=org_id, slug=slug)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.get("/chat/settings", response_model=ChatSettingsOut)
def get_settings(auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    return get_or_create_settings(db, auth.org_id, auth.org.name)


@router.put("/chat/settings", response_model=ChatSettingsOut)
def put_settings(body: ChatSettingsIn, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    if auth.user.role not in ("owner", "admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owners and admins can change chat settings")
    slug = body.slug.strip().lower()
    if not SLUG_RE.match(slug):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Link name: 3 to 40 letters, numbers or dashes, not starting or ending with a dash")
    row = get_or_create_settings(db, auth.org_id, auth.org.name)
    taken = db.scalar(select(ChatSettings).where(ChatSettings.slug == slug, ChatSettings.org_id != auth.org_id))
    if taken:
        raise HTTPException(status.HTTP_409_CONFLICT, "That link name is already taken")
    if body.enabled and not (body.sales_enabled or body.support_enabled):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Turn on at least one of sales or support")
    row.slug, row.enabled, row.welcome_message = slug, body.enabled, body.welcome_message.strip()
    row.sales_enabled, row.support_enabled = body.sales_enabled, body.support_enabled
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------- inbox

class InboxItem(BaseModel):
    id: str
    mode: str  # sales | support | test
    customer_name: str | None
    customer_email: str | None
    state: str  # ai | needs_human | human
    waiting: bool  # a customer is waiting for a person
    last_message: str
    last_message_role: str
    last_message_at: datetime
    message_count: int
    ticket_number: str | None = None
    lead_id: str | None = None


class InboxMessage(MessageOut):
    attachment_id: str | None = None


class InboxDetail(BaseModel):
    item: InboxItem
    channel: str
    escalation_reason: str | None
    can_reply: bool
    ticket_id: str | None
    messages: list[InboxMessage]
    # Only set on a reply: did the customer also get an email? sent | skipped_online | skipped_recent | no_email_setup | no_customer_email | failed
    email_status: str | None = None


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


def _mode(channel: str) -> str:
    return {"web-sales": "sales", "web-support": "support"}.get(channel, "test")


def _state(c: Conversation) -> str:
    return "human" if c.human_active else ("needs_human" if c.escalated else "ai")


def _items(db: Session, org_id: str, convs: list[Conversation]) -> list[InboxItem]:
    if not convs:
        return []
    ids = [c.id for c in convs]
    stats = (
        select(Message.conversation_id.label("cid"), func.max(Message.seq).label("ms"), func.count().label("n"))
        .where(Message.org_id == org_id, Message.conversation_id.in_(ids))
        .group_by(Message.conversation_id)
        .subquery()
    )
    rows = db.execute(
        select(Message, stats.c.n).join(stats, and_(Message.conversation_id == stats.c.cid, Message.seq == stats.c.ms)).where(Message.org_id == org_id)
    ).all()
    last = {m.conversation_id: (m, n) for m, n in rows}
    tickets = {t.conversation_id: t.number for t in db.scalars(select(Ticket).where(Ticket.org_id == org_id, Ticket.conversation_id.in_(ids))).all()}
    out = []
    for c in convs:
        if c.id not in last:
            continue
        m, n = last[c.id]
        state = _state(c)
        out.append(InboxItem(
            id=c.id, mode=_mode(c.channel), customer_name=c.customer_name, customer_email=c.customer_email, state=state,
            waiting=(state == "needs_human") or (state == "human" and m.role == "customer"),
            last_message=m.content[:140], last_message_role=m.role, last_message_at=m.created_at, message_count=n,
            ticket_number=tickets.get(c.id), lead_id=c.lead_id,
        ))
    return out


@router.get("/inbox", response_model=list[InboxItem])
def inbox(
    show: str = Query(default="all", pattern="^(all|waiting|sales|support)$"),
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    convs = db.scalars(
        select(Conversation).where(Conversation.org_id == auth.org_id, Conversation.channel.in_(WEB_CHANNELS)).order_by(Conversation.created_at.desc()).limit(200)
    ).all()
    items = _items(db, auth.org_id, list(convs))
    if show == "waiting":
        items = [i for i in items if i.waiting]
    elif show in ("sales", "support"):
        items = [i for i in items if i.mode == show]
    items.sort(key=lambda i: (not i.waiting, -i.last_message_at.timestamp()))
    return items


@router.get("/inbox/count")
def inbox_count(auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    convs = db.scalars(select(Conversation).where(Conversation.org_id == auth.org_id, Conversation.channel.in_(WEB_CHANNELS))).all()
    return {"waiting": sum(1 for i in _items(db, auth.org_id, list(convs)) if i.waiting)}


def _conv(db: Session, auth: AuthContext, conv_id: str) -> Conversation:
    c = db.scalar(select(Conversation).where(Conversation.id == conv_id, Conversation.org_id == auth.org_id))
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return c


def _detail(db: Session, auth: AuthContext, c: Conversation) -> InboxDetail:
    msgs = db.scalars(select(Message).where(Message.conversation_id == c.id, Message.org_id == auth.org_id).order_by(Message.seq)).all()
    ticket = db.scalar(select(Ticket).where(Ticket.conversation_id == c.id, Ticket.org_id == auth.org_id))
    items = _items(db, auth.org_id, [c])
    item = items[0] if items else InboxItem(
        id=c.id, mode=_mode(c.channel), customer_name=c.customer_name, customer_email=c.customer_email, state=_state(c), waiting=False,
        last_message="", last_message_role="agent", last_message_at=c.created_at, message_count=0,
    )
    atts = {}
    if msgs:
        for mid, aid in db.execute(select(ChatAttachment.message_id, ChatAttachment.id).where(ChatAttachment.org_id == auth.org_id, ChatAttachment.conversation_id == c.id)).all():
            atts[mid] = aid
    out = []
    for m in msgs:
        o = InboxMessage.model_validate(m)
        o.attachment_id = atts.get(m.id)
        out.append(o)
    return InboxDetail(
        item=item, channel=c.channel, escalation_reason=c.escalation_reason, can_reply=c.channel in WEB_CHANNELS,
        ticket_id=ticket.id if ticket else None, messages=out,
    )


@router.get("/inbox/{conv_id}", response_model=InboxDetail)
def inbox_detail(conv_id: str, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    return _detail(db, auth, _conv(db, auth, conv_id))


@router.post("/inbox/{conv_id}/reply", response_model=InboxDetail)
def reply(conv_id: str, body: ReplyIn, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    c = _conv(db, auth, conv_id)
    if c.channel not in WEB_CHANNELS:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only real customer chats can be replied to")
    seq = (db.scalar(select(func.max(Message.seq)).where(Message.conversation_id == c.id)) or 0) + 1
    text = body.body.strip()
    db.add(Message(org_id=auth.org_id, conversation_id=c.id, seq=seq, role="human", content=text))
    c.human_active = True
    ticket = db.scalar(select(Ticket).where(Ticket.conversation_id == c.id, Ticket.org_id == auth.org_id))
    if ticket is not None and ticket.status == "open":
        ticket.status = "in_progress"
    db.commit()
    email_status = comms.notify_staff_reply(db, auth.org, c, text)  # emails the customer only if they left the page
    detail = _detail(db, auth, c)
    detail.email_status = email_status
    return detail


@router.post("/inbox/{conv_id}/handback", response_model=InboxDetail)
def handback(conv_id: str, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    """Give the chat back to the AI. Also clears the escalation flag so it stops showing as needing a human."""
    c = _conv(db, auth, conv_id)
    c.human_active = False
    c.escalated = False
    db.commit()
    return _detail(db, auth, c)


@router.get("/inbox/attachments/{attachment_id}")
def attachment(attachment_id: str, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    a = db.scalar(select(ChatAttachment).where(ChatAttachment.id == attachment_id, ChatAttachment.org_id == auth.org_id))
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")
    return Response(content=a.data, media_type=a.content_type, headers={"Cache-Control": "private, max-age=3600", "Content-Disposition": "inline"})
