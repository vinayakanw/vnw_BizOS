"""Everything that reaches a customer outside the live chat: reply emails, transcripts, quote delivery.

All functions return a short status string or dict and never raise, so a mail outage cannot break a chat or an approval.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_visitor_token
from app.integrations import providers
from app.integrations import service as integrations
from app.models import ChatSettings, Conversation, Lead, Message, Organization, Quote

log = logging.getLogger("bizos.comms")

ONLINE_SECONDS = 20  # a page polls every 4s; this long without a poll means the customer left
SEEN_WRITE_EVERY = 5  # do not write presence on every single poll
NOTIFY_COOLDOWN = timedelta(minutes=5)
QUOTE_VALID_DAYS = 14


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def now() -> datetime:
    return datetime.now(timezone.utc)


def touch(db: Session, conv: Conversation) -> None:
    """Record that the customer's page is open right now."""
    seen = _aware(conv.customer_last_seen_at)
    if seen is None or (now() - seen).total_seconds() >= SEEN_WRITE_EVERY:
        conv.customer_last_seen_at = now()
        db.commit()


def is_online(conv: Conversation) -> bool:
    seen = _aware(conv.customer_last_seen_at)
    return seen is not None and (now() - seen).total_seconds() < ONLINE_SECONDS


def email_enabled(db: Session, org_id: str) -> bool:
    return integrations.get_config(db, org_id, "email") is not None


def chat_link(db: Session, org_id: str, conv: Conversation) -> str | None:
    cs = db.scalar(select(ChatSettings).where(ChatSettings.org_id == org_id))
    if cs is None or not cs.enabled:
        return None
    return f"{settings.public_app_url.rstrip('/')}/chat/{cs.slug}?t={create_visitor_token(conv.id, org_id)}"


def quote_link(quote: Quote) -> str:
    return f"{settings.public_app_url.rstrip('/')}/quote/{quote.public_token}"


def send_to_customer(db: Session, org_id: str, to: str | None, subject: str, body: str) -> str:
    """sent | no_email_setup | no_customer_email | failed"""
    if not to:
        return "no_customer_email"
    cfg = integrations.get_config(db, org_id, "email")
    if cfg is None:
        return "no_email_setup"
    try:
        providers.send_email(cfg, to, subject, body)
        return "sent"
    except Exception as e:  # noqa: BLE001
        log.warning("Customer email failed: %s", e)
        return "failed"


def notify_staff_reply(db: Session, org: Organization, conv: Conversation, text: str) -> str:
    """Email the customer a staff reply if they have left the page. Status: sent | skipped_online | skipped_recent | no_email_setup | no_customer_email | failed"""
    if is_online(conv):
        return "skipped_online"
    last = _aware(conv.customer_notified_at)
    if last is not None and now() - last < NOTIFY_COOLDOWN:
        return "skipped_recent"
    link = chat_link(db, org.id, conv)
    body = (
        f"Hi {conv.customer_name or 'there'},\n\n{org.name} replied to your chat:\n\n\"{text}\"\n\n"
        + (f"Continue the conversation here:\n{link}\n\n" if link else "")
        + f"You are getting this email because you started a chat with {org.name}."
    )
    st = send_to_customer(db, org.id, conv.customer_email, f"{org.name} replied to your message", body)
    if st == "sent":
        conv.customer_notified_at = now()
        db.commit()
    return st


def send_transcript(db: Session, org: Organization, conv: Conversation) -> str:
    rows = db.scalars(select(Message).where(Message.conversation_id == conv.id, Message.org_id == org.id).order_by(Message.seq)).all()
    who = {"customer": "You", "agent": f"{org.name} assistant", "human": f"{org.name} team"}
    lines = [f"{who.get(m.role, m.role)}: {m.content}" for m in rows]
    body = f"Hi {conv.customer_name or 'there'},\n\nHere is a copy of your chat with {org.name}.\n\n" + "\n\n".join(lines)
    return send_to_customer(db, org.id, conv.customer_email, f"Your chat with {org.name}", body)


def deliver_quote(db: Session, org: Organization, quote: Quote) -> dict:
    """Make a quote reach the customer: a message in their chat, plus an email if they have left the page.

    Returns {"url", "chat": bool, "email": status}. Safe to call again to resend.
    """
    lead = db.scalar(select(Lead).where(Lead.id == quote.lead_id, Lead.org_id == org.id))
    conv = None
    if lead is not None:
        conv = db.scalar(
            select(Conversation)
            .where(Conversation.org_id == org.id, Conversation.lead_id == lead.id, Conversation.channel == "web-sales")
            .order_by(Conversation.created_at.desc())
        )
    url = quote_link(quote)
    if quote.expires_at is None:
        quote.expires_at = now() + timedelta(days=QUOTE_VALID_DAYS)
    if quote.status == "draft":
        quote.status = "sent"
    result = {"url": url, "chat": False, "email": "no_customer_email"}
    text = f"Your quote {quote.number} is ready. You can review it and accept, decline or ask for changes here:\n{url}"
    if conv is not None:
        seq = (db.scalar(select(func.max(Message.seq)).where(Message.conversation_id == conv.id)) or 0) + 1
        db.add(Message(org_id=org.id, conversation_id=conv.id, seq=seq, role="agent", content=text))
        result["chat"] = True
    db.commit()
    to = (conv.customer_email if conv is not None else None) or (lead.email if lead is not None else None)
    if conv is not None and is_online(conv):
        result["email"] = "skipped_online"
    else:
        body = (
            f"Hi {(conv.customer_name if conv else None) or (lead.name if lead else None) or 'there'},\n\n"
            f"{org.name} prepared a quote for you ({quote.number}).\n\nReview it, and accept, decline or ask for changes:\n{url}\n\n"
            f"The link is valid for {QUOTE_VALID_DAYS} days."
        )
        result["email"] = send_to_customer(db, org.id, to, f"Your quote {quote.number} from {org.name}", body)
    return result
