from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.agents.sales.agent import ConversationNotFound
from app.agents.support.agent import run_support_agent
from app.core import ratelimit
from app.api.deps import AuthContext, get_auth
from app.core.db import get_db
from app.llm.base import LLMError, LLMUnavailable
from app.models import Conversation, Message, Ticket
from app.schemas_agent import ConversationOut, MessageOut, StepOut

router = APIRouter(tags=["support agent"])


class SupportChatIn(BaseModel):
    conversation_id: str | None = None
    message: str = Field(min_length=1, max_length=2000)
    customer_name: str | None = Field(default=None, max_length=200)


class TicketOut(BaseModel):
    id: str
    conversation_id: str
    number: str
    subject: str
    category: str
    priority: str
    status: str
    customer_name: str | None
    email: str | None
    phone: str | None
    order_reference: str | None
    escalation_reason: str | None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class SupportChatOut(BaseModel):
    conversation_id: str
    reply: str
    escalated: bool
    escalation_reason: str | None
    ticket: TicketOut | None
    run_id: str
    steps: list[StepOut]
    sources: list[str]


class TicketPatch(BaseModel):
    status: str | None = Field(default=None, pattern="^(open|in_progress|resolved)$")
    priority: str | None = Field(default=None, pattern="^(low|normal|high)$")


class TicketDetail(BaseModel):
    ticket: TicketOut
    conversation: ConversationOut | None


@router.post("/agents/support/chat", response_model=SupportChatOut, dependencies=[Depends(ratelimit.by_org("llm", 30, 60))])
def support_chat(body: SupportChatIn, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    try:
        r = run_support_agent(db, auth.org, body.conversation_id, body.message.strip(), body.customer_name)
    except ConversationNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    except LLMUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    except LLMError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The AI model returned an unusable answer. Please try again.")
    return SupportChatOut(
        conversation_id=r.conversation_id, reply=r.reply, escalated=r.escalated, escalation_reason=r.escalation_reason,
        ticket=TicketOut.model_validate(r.ticket) if r.ticket else None, run_id=r.run_id, steps=r.steps, sources=r.sources,
    )


def _get(db: Session, auth: AuthContext, ticket_id: str) -> Ticket:
    t = db.scalar(select(Ticket).where(Ticket.id == ticket_id, Ticket.org_id == auth.org_id))
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    return t


@router.get("/tickets", response_model=list[TicketOut])
def list_tickets(
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=100),
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    stmt = select(Ticket).where(Ticket.org_id == auth.org_id)
    if status_filter:
        if status_filter not in ("open", "in_progress", "resolved"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown status")
        stmt = stmt.where(Ticket.status == status_filter)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Ticket.subject.ilike(like), Ticket.customer_name.ilike(like), Ticket.email.ilike(like), Ticket.order_reference.ilike(like), Ticket.number.ilike(like)))
    tickets = db.scalars(stmt).all()
    rank = {"high": 0, "normal": 1, "low": 2}
    done = {"resolved": 1}
    return sorted(tickets, key=lambda t: (done.get(t.status, 0), rank.get(t.priority, 1), -t.created_at.timestamp()))


@router.get("/tickets/count")
def ticket_count(auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    n = db.scalar(select(func.count()).select_from(Ticket).where(Ticket.org_id == auth.org_id, Ticket.status != "resolved"))
    return {"open": n or 0}


@router.get("/tickets/{ticket_id}", response_model=TicketDetail)
def ticket_detail(ticket_id: str, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    t = _get(db, auth, ticket_id)
    c = db.scalar(select(Conversation).where(Conversation.id == t.conversation_id, Conversation.org_id == auth.org_id))
    conv = None
    if c:
        msgs = db.scalars(select(Message).where(Message.conversation_id == c.id, Message.org_id == auth.org_id).order_by(Message.seq)).all()
        conv = ConversationOut(
            id=c.id, escalated=c.escalated, escalation_reason=c.escalation_reason, created_at=c.created_at,
            messages=[MessageOut.model_validate(m) for m in msgs],
        )
    return TicketDetail(ticket=TicketOut.model_validate(t), conversation=conv)


@router.patch("/tickets/{ticket_id}", response_model=TicketOut)
def update_ticket(ticket_id: str, body: TicketPatch, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    t = _get(db, auth, ticket_id)
    if body.status:
        t.status = body.status
    if body.priority:
        t.priority = body.priority
    db.commit()
    db.refresh(t)
    return t
