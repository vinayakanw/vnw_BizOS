"""Support agent: analyze -> retrieve knowledge -> reply (grounded) -> escalation rules -> ticket -> trace.

It can read an order only when the customer gives an order number that matches the email on the chat. It has no access
to payments or addresses. Everything else is policy from the knowledge base, or a hand-off to a human through a ticket.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations import service as integrations
from app.agents.common import business_context
from app.agents.sales.agent import ConversationNotFound
from app.agents.sales.retrieval import search_knowledge
from app.agents.support import prompts
from app.agents.support.schemas import SupportAnalysis, SupportReply
from app.agents.support.tickets import next_ticket_number
from app.orders_lookup import find_order, order_facts
from app.llm.base import LLMError
from app.llm.factory import get_llm
from app.llm.structured import generate_structured
from app.models import AgentRun, Conversation, Message, Organization, Ticket

log = logging.getLogger("bizos.support")

HISTORY_TURNS = 10
CHANNEL = "support"
TICKET_CATEGORIES = {"order_status", "delivery", "return_refund", "warranty", "complaint", "technical"}
NO_KNOWLEDGE_OK = {"greeting", "other"}
PRIORITY_RANK = {"low": 0, "normal": 1, "high": 2}
MAX_LOOKUP_FAILURES = 5  # wrong order numbers per conversation before lookups stop


@dataclass
class SupportResult:
    conversation_id: str
    reply: str
    escalated: bool
    escalation_reason: str | None
    ticket: Ticket | None
    run_id: str
    steps: list[dict]
    sources: list[str] = field(default_factory=list)


def _pick(new, old):
    return new if new not in (None, "") else old


def _priority(a: SupportAnalysis, escalated: bool) -> str:
    if a.sentiment == "angry" or a.urgency == "high" or a.sensitive_request:
        return "high"
    if a.category in ("greeting", "faq") and not escalated:
        return "low"
    return "normal"


def run_support_agent(
    db: Session, org: Organization, conversation_id: str | None, message: str, customer_name: str | None = None, channel: str = CHANNEL
) -> SupportResult:
    started = time.monotonic()
    steps: list[dict] = []

    def add(step: str, detail: str = "") -> None:
        steps.append({"t": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "step": step, "detail": detail})

    if conversation_id:
        conv = db.scalar(select(Conversation).where(Conversation.id == conversation_id, Conversation.org_id == org.id))
        if conv is None or conv.channel != channel:
            raise ConversationNotFound()
    else:
        conv = Conversation(org_id=org.id, channel=channel, customer_name=customer_name)
        db.add(conv)
        db.flush()

    prior = db.scalars(
        select(Message).where(Message.conversation_id == conv.id, Message.org_id == org.id).order_by(Message.seq.desc()).limit(HISTORY_TURNS)
    ).all()
    history = [("team" if m.role == "human" else m.role, m.content) for m in reversed(prior)]
    next_seq = (db.scalar(select(func.max(Message.seq)).where(Message.conversation_id == conv.id)) or 0) + 1
    db.add(Message(org_id=org.id, conversation_id=conv.id, seq=next_seq, role="customer", content=message))

    run = AgentRun(org_id=org.id, agent="support", conversation_id=conv.id, status="running")
    db.add(run)
    add("Received customer message", message[:200])
    db.commit()

    def fail(err: Exception) -> None:
        add("Failed", str(err)[:300])
        run.status, run.error = "failed", str(err)[:500]
        run.steps = list(steps)
        run.duration_ms = int((time.monotonic() - started) * 1000)
        db.commit()

    try:
        llm = get_llm()
        a = generate_structured(llm, prompts.ANALYZE_SYSTEM, prompts.analyze_prompt(history, message), SupportAnalysis)
        add("Analyzed message", f"category={a.category}, urgency={a.urgency}, sentiment={a.sentiment}")

        query = " ".join([message, *a.search_terms])
        try:
            knowledge = search_knowledge(db, org.id, query)
        except Exception:
            log.exception("Knowledge search failed")
            knowledge = []
        add("Searched knowledge", f"{len(knowledge)} relevant passage(s)" + (": " + ", ".join(dict.fromkeys(k["title"] for k in knowledge)) if knowledge else ""))

        ticket = db.scalar(select(Ticket).where(Ticket.conversation_id == conv.id, Ticket.org_id == org.id))
        known = {
            k: v
            for k, v in {
                "name": a.customer_name or customer_name or conv.customer_name or (ticket.customer_name if ticket else None),
                "email": a.email or conv.customer_email or (ticket.email if ticket else None),
                "order_reference": a.order_reference or (ticket.order_reference if ticket else None),
            }.items()
            if v
        }

        # --- order lookup: code finds the order, the model only phrases what code gives it ---
        order_block, order_answered, order_missed = None, False, False
        if a.category == "order_status":
            ref = known.get("order_reference")
            email = conv.customer_email or a.email
            if not ref:
                order_block = "no_reference"
            elif conv.lookup_failures >= MAX_LOOKUP_FAILURES:
                order_block, order_missed = "not_found", True
                add("Order lookup skipped", "too many failed lookups in this conversation")
            else:
                order = find_order(db, org.id, ref, email)
                if order is not None:
                    order_block, order_answered = order_facts(order), True
                    add("Looked up order", f"{order.order_ref}: {order.status}")
                else:
                    conv.lookup_failures += 1
                    order_block, order_missed = "not_found", True
                    add("Looked up order", "no order matches that number and email")
        reply = generate_structured(
            llm, prompts.REPLY_SYSTEM, prompts.reply_prompt(business_context(db, org), history, known, knowledge, message, order_block), SupportReply
        )
        add("Drafted reply", f"{len(reply.reply)} characters")

        # --- escalation rules (code, not model opinion) ---
        reasons = []
        if a.wants_human:
            reasons.append("Customer asked for a human")
        if a.sentiment == "angry":
            reasons.append("Customer is upset")
        if a.sensitive_request:
            reasons.append("Sensitive request (refund demand, payment, legal or safety)")
        if order_missed:
            reasons.append("Order not found for the number and email given, needs a person to check")
        if a.category == "return_refund" and not knowledge:
            reasons.append("Return or refund question with no policy in the knowledge base")
        if not knowledge and a.category not in NO_KNOWLEDGE_OK and a.category != "order_status":
            reasons.append("Nothing in the knowledge base covers this")
        if reply.needs_human:
            reasons.append(reply.escalation_reason or "Agent could not resolve this from available information")
        escalation_reason = "; ".join(dict.fromkeys(reasons)) or None
        if escalation_reason:
            add("Escalated to human", escalation_reason)
            conv.escalated, conv.escalation_reason = True, escalation_reason

        # --- ticket: created for real problems and every escalation, updated on later messages ---
        if escalation_reason or (a.category in TICKET_CATEGORIES and not order_answered) or ticket is not None:
            if ticket is None:
                ticket = Ticket(
                    org_id=org.id, conversation_id=conv.id, number=next_ticket_number(db, org.id),
                    subject=(a.issue_summary or message)[:200], category=a.category,
                    priority=_priority(a, bool(escalation_reason)),
                )
                db.add(ticket)
                add("Created ticket", f"{ticket.number}: {ticket.subject}")
                integrations.notify_slack(db, org.id, f"New support ticket {ticket.number} ({ticket.priority}): {ticket.subject}")
            else:
                if a.issue_summary and ticket.category in ("greeting", "faq", "other"):
                    ticket.subject, ticket.category = a.issue_summary[:200], a.category
                new_p = _priority(a, bool(escalation_reason))
                if PRIORITY_RANK[new_p] > PRIORITY_RANK[ticket.priority]:
                    ticket.priority = new_p
                if ticket.status == "resolved":
                    ticket.status = "open"
                    add("Reopened ticket", ticket.number)
                else:
                    add("Updated ticket", ticket.number)
            ticket.customer_name = _pick(a.customer_name or customer_name or conv.customer_name, ticket.customer_name)
            ticket.email = _pick(a.email or conv.customer_email, ticket.email)
            ticket.phone = _pick(a.phone or conv.customer_phone, ticket.phone)
            ticket.order_reference = _pick(a.order_reference, ticket.order_reference)
            if escalation_reason:
                ticket.escalation_reason = escalation_reason
            db.flush()

        db.add(Message(org_id=org.id, conversation_id=conv.id, seq=next_seq + 1, role="agent", content=reply.reply))
        add("Completed")
        run.status = "escalated" if escalation_reason else "completed"
        run.summary = f"{a.category}" + (f"; ticket {ticket.number}" if ticket else "") + (f"; escalated: {escalation_reason}" if escalation_reason else "")
        run.steps = list(steps)
        run.duration_ms = int((time.monotonic() - started) * 1000)
        db.commit()
        return SupportResult(
            conversation_id=conv.id, reply=reply.reply, escalated=bool(escalation_reason), escalation_reason=escalation_reason,
            ticket=ticket, run_id=run.id, steps=steps, sources=list(dict.fromkeys(k["title"] for k in knowledge)),
        )
    except LLMError as e:
        db.rollback()
        run = db.get(AgentRun, run.id)
        fail(e)
        raise
    except Exception as e:
        log.exception("Support agent crashed")
        db.rollback()
        run = db.get(AgentRun, run.id)
        fail(e)
        raise
