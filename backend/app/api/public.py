"""Public customer chat. No login. A visitor token (signed, one conversation, 7 days) is the only credential.

Everything returned here is customer-safe: reply text, a hand-off flag and a ticket reference. Never lead scores,
agent steps, sources, internal notes or other customers' data.
"""

import logging

import jwt
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.sales.agent import ConversationNotFound, run_sales_agent
from app import customer_comms as comms
from app.agents.support.agent import run_support_agent
from app.agents.support.tickets import ensure_ticket
from app.core import ratelimit
from app.core.config import settings
from app.core.db import get_db
from app.core.security import create_visitor_token, decode_visitor_token
from app.integrations import service as integrations
from app.llm.base import LLMError, LLMUnavailable
from app.models import ChatAttachment, ChatSettings, Conversation, Message, Organization, Quote, Ticket, ToolCall

log = logging.getLogger("bizos.public")
router = APIRouter(prefix="/public/chat", tags=["public chat"])

MAX_CUSTOMER_MESSAGES = 60  # per conversation, cost and abuse cap
MAX_PHOTO_BYTES = 4 * 1024 * 1024
MAX_PHOTOS = 10  # per conversation
PHOTO_ACK = {
    "en": ("Sent a photo", "Thanks, we received your photo. A team member will take a look and reply here."),
    "hi": ("फोटो भेजी", "धन्यवाद, हमें आपकी फोटो मिल गई है। हमारी टीम देखकर यहीं जवाब देगी।"),
}
BUSY = "We're having trouble right now. Please try again in a moment."


class StartIn(BaseModel):
    mode: str = Field(pattern="^(sales|support)$")
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=30)


class MessageIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class PublicMessage(BaseModel):
    seq: int
    role: str  # customer | agent | human
    content: str
    attachment_id: str | None = None


class Info(BaseModel):
    name: str
    welcome_message: str
    sales_enabled: bool
    support_enabled: bool
    email_enabled: bool  # the business can email transcripts and replies


class Session_(BaseModel):
    token: str
    messages: list[PublicMessage]


class ProductCard(BaseModel):
    name: str
    price: float
    currency: str
    blurb: str = ""
    in_stock: bool | None = None


class Reply(BaseModel):
    products: list[ProductCard] = []  # products the AI just talked about, shown as cards
    messages: list[PublicMessage]  # new agent or team messages after the customer's own
    last_seq: int
    handoff: bool  # a person will follow up
    human_active: bool
    ticket: str | None = None


def _settings(db: Session, slug: str) -> tuple[ChatSettings, Organization]:
    row = db.execute(
        select(ChatSettings, Organization).join(Organization, Organization.id == ChatSettings.org_id).where(ChatSettings.slug == slug.lower())
    ).first()  # one round trip
    if row is None or not row[0].enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This chat is not available")
    return row[0], row[1]


def _visitor(db: Session, org: Organization, token: str | None) -> Conversation:
    bad = HTTPException(status.HTTP_401_UNAUTHORIZED, "Your chat session expired. Please start a new chat.")
    if not token:
        raise bad
    try:
        payload = decode_visitor_token(token)
    except jwt.PyJWTError:
        raise bad
    if payload.get("org") != org.id:
        raise bad
    conv = db.scalar(select(Conversation).where(Conversation.id == payload.get("cid"), Conversation.org_id == org.id))
    if conv is None or conv.channel not in ("web-sales", "web-support"):
        raise bad
    return conv


def _visible(db: Session, conv: Conversation, after: int = 0, roles: tuple[str, ...] = ("customer", "agent", "human")) -> list[PublicMessage]:
    rows = db.scalars(
        select(Message).where(Message.conversation_id == conv.id, Message.org_id == conv.org_id, Message.seq > after, Message.role.in_(roles)).order_by(Message.seq)
    ).all()
    atts = {}
    if rows:
        for a in db.execute(select(ChatAttachment.message_id, ChatAttachment.id).where(ChatAttachment.message_id.in_([m.id for m in rows]))).all():
            atts[a[0]] = a[1]
    return [PublicMessage(seq=m.seq, role=m.role, content=m.content, attachment_id=atts.get(m.id)) for m in rows]


def _last_seq(db: Session, conv: Conversation) -> int:
    return db.scalar(select(func.max(Message.seq)).where(Message.conversation_id == conv.id)) or 0


@router.get("/{slug}", response_model=Info, dependencies=[Depends(ratelimit.by_ip("pub_info", 120, 60))])
def info(slug: str, db: Session = Depends(get_db)):
    cs, org = _settings(db, slug)
    return Info(
        name=org.name, welcome_message=cs.welcome_message, sales_enabled=cs.sales_enabled, support_enabled=cs.support_enabled,
        email_enabled=comms.email_enabled(db, org.id),
    )


class Me(BaseModel):
    mode: str
    name: str | None


@router.get("/{slug}/me", response_model=Me, dependencies=[Depends(ratelimit.by_ip("pub_me", 120, 60))])
def me(slug: str, x_visitor_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    """Which kind of chat this token belongs to. Used when a customer comes back through an email link."""
    _, org = _settings(db, slug)
    conv = _visitor(db, org, x_visitor_token)
    return Me(mode="sales" if conv.channel == "web-sales" else "support", name=conv.customer_name)


@router.post("/{slug}/start", response_model=Session_, dependencies=[Depends(ratelimit.by_ip("pub_start", 20, 3600))])
def start(slug: str, body: StartIn, db: Session = Depends(get_db)):
    cs, org = _settings(db, slug)
    if (body.mode == "sales" and not cs.sales_enabled) or (body.mode == "support" and not cs.support_enabled):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This chat is not available")
    if settings.rate_limit_enabled and (wait := ratelimit.hit(f"pub_start:org:{org.id}", 300, 86400)):
        raise ratelimit._deny(wait)
    conv = Conversation(
        org_id=org.id, channel=f"web-{body.mode}", customer_name=body.name.strip(), customer_email=str(body.email).lower(),
        customer_phone=(body.phone or "").strip() or None,
    )
    db.add(conv)
    db.flush()
    db.add(Message(org_id=org.id, conversation_id=conv.id, seq=1, role="agent", content=cs.welcome_message))
    db.commit()
    return Session_(token=create_visitor_token(conv.id, org.id), messages=_visible(db, conv))


@router.get("/{slug}/messages", response_model=list[PublicMessage], dependencies=[Depends(ratelimit.by_ip("pub_poll", 120, 60))])
def messages(slug: str, after: int = 0, x_visitor_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    """Polling: new team and agent messages. With after=0 returns the whole chat (to restore it after a page reload)."""
    _, org = _settings(db, slug)
    conv = _visitor(db, org, x_visitor_token)
    comms.touch(db, conv)
    return _visible(db, conv, after, ("customer", "agent", "human") if after == 0 else ("agent", "human"))


@router.post("/{slug}/message", response_model=Reply, dependencies=[Depends(ratelimit.by_ip("pub_msg", 20, 60))])
def send(slug: str, body: MessageIn, x_visitor_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    cs, org = _settings(db, slug)
    conv = _visitor(db, org, x_visitor_token)
    comms.touch(db, conv)
    if settings.rate_limit_enabled:
        wait = ratelimit.hit(f"pub_msg:conv:{conv.id}", 10, 60) or ratelimit.hit(f"pub_msg:org:{org.id}", 400, 3600)
        if wait:
            raise ratelimit._deny(wait)
    sent = db.scalar(select(func.count()).select_from(Message).where(Message.conversation_id == conv.id, Message.role == "customer")) or 0
    if sent >= MAX_CUSTOMER_MESSAGES:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "This conversation is full. Please start a new chat or contact us directly.")

    text = body.message.strip()
    before = _last_seq(db, conv)
    was_escalated = conv.escalated
    mode = "sales" if conv.channel == "web-sales" else "support"

    if conv.human_active:  # a person is handling it: store the message, the AI stays quiet
        db.add(Message(org_id=org.id, conversation_id=conv.id, seq=before + 1, role="customer", content=text))
        db.commit()
        integrations.notify_slack(db, org.id, f"Customer replied in chat ({conv.customer_name or 'customer'}): {text[:150]}")
        ticket = db.scalar(select(Ticket).where(Ticket.conversation_id == conv.id, Ticket.org_id == org.id))
        return Reply(messages=[], last_seq=before + 1, handoff=True, human_active=True, ticket=ticket.number if ticket else None)

    cards: list[ProductCard] = []
    try:
        if mode == "sales":
            result = run_sales_agent(db, org, conv.id, text, conv.customer_name, channel="web-sales")
            _deliver_new_quotes(db, org, result.actions)
            said = " ".join(m.content for m in _visible(db, conv, before, ("agent",))).lower()
            cards = [
                ProductCard(name=p["name"], price=p["price"], currency=p["currency"], blurb=(p.get("description") or "")[:110], in_stock=(p["stock"] > 0) if isinstance(p.get("stock"), int) else None)
                for p in result.products
                if p["name"].lower() in said
            ][:3]
        else:
            run_support_agent(db, org, conv.id, text, conv.customer_name, channel="web-support")
    except ConversationNotFound:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your chat session expired. Please start a new chat.")
    except (LLMUnavailable, LLMError):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, BUSY)
    except Exception:
        log.exception("Public chat failed")
        db.rollback()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, BUSY)

    db.refresh(conv)
    if conv.escalated and not was_escalated:
        integrations.notify_slack(db, org.id, f"Customer chat needs a person ({mode}, {conv.customer_name or 'customer'}): {(conv.escalation_reason or '')[:200]}")
    new = [m for m in _visible(db, conv, before, ("agent", "human"))]
    ticket = db.scalar(select(Ticket).where(Ticket.conversation_id == conv.id, Ticket.org_id == org.id))
    return Reply(
        products=cards, messages=new, last_seq=_last_seq(db, conv), handoff=conv.escalated, human_active=conv.human_active, ticket=ticket.number if ticket else None
    )


def _deliver_new_quotes(db: Session, org: Organization, actions: list[dict]) -> None:
    """A quote the agent just created (no approval needed) goes to the customer as a link in the chat."""
    for act in actions:
        if act.get("tool") != "create_quote" or act.get("status") != "executed":
            continue
        call = db.scalar(select(ToolCall).where(ToolCall.id == act["id"], ToolCall.org_id == org.id))
        quote_id = (call.result or {}).get("quote_id") if call else None
        quote = db.scalar(select(Quote).where(Quote.id == quote_id, Quote.org_id == org.id)) if quote_id else None
        if quote is not None:
            comms.deliver_quote(db, org, quote)


# ---------------------------------------------------------------- transcript

@router.post("/{slug}/transcript", dependencies=[Depends(ratelimit.by_ip("pub_transcript", 10, 3600))])
def transcript(slug: str, x_visitor_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    """Email the customer a copy of this chat. Goes only to the email they gave when they started."""
    _, org = _settings(db, slug)
    conv = _visitor(db, org, x_visitor_token)
    if not comms.email_enabled(db, org.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "This business cannot send email right now.")
    if settings.rate_limit_enabled and (wait := ratelimit.hit(f"pub_transcript:conv:{conv.id}", 3, 3600)):
        raise ratelimit._deny(wait)
    st = comms.send_transcript(db, org, conv)
    if st != "sent":
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "We could not send the email. Please try again later.")
    return {"sent": True, "to": _mask(conv.customer_email)}


def _mask(email: str | None) -> str:
    if not email or "@" not in email:
        return ""
    name, domain = email.split("@", 1)
    return f"{name[:1]}***@{domain}"


# ---------------------------------------------------------------- photos

def _sniff_image(data: bytes) -> str | None:
    """The type comes from the bytes, never from the file name or the browser's claim."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@router.post("/{slug}/photo", response_model=Reply, dependencies=[Depends(ratelimit.by_ip("pub_photo", 10, 60))])
def photo(
    slug: str,
    file: UploadFile = File(...),
    caption: str = Form(default="", max_length=500),
    lang: str = Form(default="en", max_length=5),
    x_visitor_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """The customer sends a photo (damaged item, wrong product). The AI does not look at it: a person does."""
    cs, org = _settings(db, slug)
    conv = _visitor(db, org, x_visitor_token)
    if settings.rate_limit_enabled and (wait := ratelimit.hit(f"pub_photo:conv:{conv.id}", 5, 600)):
        raise ratelimit._deny(wait)
    data = file.file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "That photo is too large. The limit is 4 MB.")
    ctype = _sniff_image(data)
    if ctype is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Please send a JPG, PNG or WebP photo.")
    have = db.scalar(select(func.count()).select_from(ChatAttachment).where(ChatAttachment.conversation_id == conv.id)) or 0
    if have >= MAX_PHOTOS:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "You have sent the maximum number of photos for this chat.")

    default_text, ack = PHOTO_ACK.get(lang if lang in PHOTO_ACK else "en")
    seq = _last_seq(db, conv) + 1
    before = seq - 1
    msg = Message(org_id=org.id, conversation_id=conv.id, seq=seq, role="customer", content=caption.strip() or default_text)
    db.add(msg)
    db.flush()
    db.add(ChatAttachment(org_id=org.id, conversation_id=conv.id, message_id=msg.id, content_type=ctype, size=len(data), data=data))

    was_escalated = conv.escalated
    ticket = None
    if not conv.human_active:
        db.add(Message(org_id=org.id, conversation_id=conv.id, seq=seq + 1, role="agent", content=ack))
    if not was_escalated:
        conv.escalated = True
        conv.escalation_reason = "Customer sent a photo, needs a person to review it"
    if conv.channel == "web-support":
        ticket = ensure_ticket(db, org.id, conv, "Customer sent a photo", "other", conv.escalation_reason or "Customer sent a photo")
    db.commit()
    if not was_escalated:
        integrations.notify_slack(db, org.id, f"Customer sent a photo ({conv.customer_name or 'customer'}). Open the Inbox to review it.")
    elif conv.human_active:
        integrations.notify_slack(db, org.id, f"Customer sent a photo in an active chat ({conv.customer_name or 'customer'}).")
    new = _visible(db, conv, before, ("customer", "agent", "human"))
    return Reply(messages=new, last_seq=_last_seq(db, conv), handoff=True, human_active=conv.human_active, ticket=ticket.number if ticket else None)


@router.get("/{slug}/photo/{attachment_id}", dependencies=[Depends(ratelimit.by_ip("pub_photo_get", 240, 60))])
def get_photo(slug: str, attachment_id: str, x_visitor_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    """The customer's own photos only (the token pins the conversation)."""
    _, org = _settings(db, slug)
    conv = _visitor(db, org, x_visitor_token)
    a = db.scalar(select(ChatAttachment).where(ChatAttachment.id == attachment_id, ChatAttachment.conversation_id == conv.id, ChatAttachment.org_id == org.id))
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return Response(content=a.data, media_type=a.content_type, headers={"Cache-Control": "private, max-age=3600"})
