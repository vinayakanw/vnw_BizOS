from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations import service as integrations
from app.models import Conversation, Ticket


def next_ticket_number(db: Session, org_id: str) -> str:
    count = db.scalar(select(func.count()).select_from(Ticket).where(Ticket.org_id == org_id)) or 0
    return f"T-{count + 1:04d}"


def ensure_ticket(db: Session, org_id: str, conv: Conversation, subject: str, category: str, reason: str) -> Ticket:
    """The ticket for a support conversation, created if it does not exist yet (used when no agent run created one)."""
    ticket = db.scalar(select(Ticket).where(Ticket.conversation_id == conv.id, Ticket.org_id == org_id))
    if ticket is None:
        ticket = Ticket(
            org_id=org_id, conversation_id=conv.id, number=next_ticket_number(db, org_id), subject=subject[:200], category=category,
            priority="normal", customer_name=conv.customer_name, email=conv.customer_email, phone=conv.customer_phone,
            escalation_reason=reason,
        )
        db.add(ticket)
        db.flush()
        integrations.notify_slack(db, org_id, f"New support ticket {ticket.number} (normal): {ticket.subject}")
    return ticket
