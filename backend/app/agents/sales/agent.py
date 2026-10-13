"""Sales agent pipeline: analyze -> retrieve -> reply -> score -> persist, with a full step trace.

The model reasons (analysis + reply). Retrieval, scoring, escalation and persistence are plain code,
so the agent can only do what is explicitly written here.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.common import business_context
from app.agents.sales import prompts
from app.agents.sales.retrieval import find_products, search_knowledge
from app.agents.sales.schemas import Analysis, ProposedAction, Reply
from app.agents.sales.scoring import STAGE_RANK, ScoreInput, recommend_next_action, score_lead
from app.llm.base import LLMError
from app.llm.factory import get_llm
from app.llm.structured import generate_structured
from app.models import AgentRun, BusinessProfile, Conversation, Lead, Message, Organization
from app.tools import run_tool
from app.workflows.engine import fire

log = logging.getLogger("bizos.sales")

SALES_CATEGORIES = {"product_inquiry", "pricing", "purchase_intent"}
HISTORY_TURNS = 10


class ConversationNotFound(Exception):
    pass


@dataclass
class Trace:
    steps: list[dict] = field(default_factory=list)

    def add(self, step: str, detail: str = "") -> None:
        self.steps.append({"t": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "step": step, "detail": detail})


@dataclass
class ChatResult:
    conversation_id: str
    reply: str
    escalated: bool
    escalation_reason: str | None
    lead: Lead | None
    run_id: str
    steps: list[dict]
    products: list[dict]
    actions: list[dict] = field(default_factory=list)


def _pick(new, old):
    return new if new not in (None, "") else old


_business_context = business_context


def _merge_lead(db: Session, org_id: str, conv: Conversation, a: Analysis, products_ok: bool, customer_name: str | None) -> Lead:
    lead = db.get(Lead, conv.lead_id) if conv.lead_id else None
    if lead is not None and lead.org_id != org_id:  # defensive: never touch another tenant's lead
        lead = None
    if lead is None:
        lead = Lead(org_id=org_id, conversation_id=conv.id)
        db.add(lead)

    lead.name = _pick(a.customer_name or customer_name, lead.name)
    lead.company = _pick(a.company, lead.company)
    lead.email = _pick(a.email or conv.customer_email, lead.email)
    lead.phone = _pick(a.phone or conv.customer_phone, lead.phone)
    lead.requirement = _pick(a.requirement_summary, lead.requirement)
    lead.use_case = _pick(a.use_case, lead.use_case)
    lead.timeline = _pick(a.timeline, lead.timeline)
    lead.quantity = _pick(a.quantity, lead.quantity)
    lead.budget_per_unit = _pick(a.budget_per_unit, lead.budget_per_unit)
    lead.currency = (_pick(a.currency, lead.currency) or "INR").upper()[:3]
    if STAGE_RANK[a.purchase_stage] >= STAGE_RANK.get(lead.purchase_stage or "browsing", 0):
        lead.purchase_stage = a.purchase_stage
    lead.product_match = bool(lead.product_match) or products_ok
    return lead


def run_sales_agent(
    db: Session, org: Organization, conversation_id: str | None, message: str, customer_name: str | None = None,
    channel: str = "dashboard",
) -> ChatResult:
    started = time.monotonic()
    trace = Trace()

    # --- conversation + customer message (saved first so nothing is lost if the model fails) ---
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

    run = AgentRun(org_id=org.id, agent="sales", conversation_id=conv.id, status="running")
    db.add(run)
    trace.add("Received customer message", message[:200])
    db.commit()

    def fail(err: Exception) -> None:
        trace.add("Failed", str(err)[:300])
        run.status = "failed"
        run.error = str(err)[:500]
        run.steps = list(trace.steps)
        run.duration_ms = int((time.monotonic() - started) * 1000)
        db.commit()

    try:
        llm = get_llm()

        # --- 1. understand ---
        analysis = generate_structured(llm, prompts.ANALYZE_SYSTEM, prompts.analyze_prompt(history, message), Analysis)
        trace.add(
            "Analyzed message",
            f"category={analysis.category}, stage={analysis.purchase_stage}, qty={analysis.quantity}, "
            f"budget={analysis.budget_per_unit} {analysis.currency or ''}".strip(),
        )

        # --- 2. retrieve (this org only) ---
        existing = db.get(Lead, conv.lead_id) if conv.lead_id else None
        prev_status = existing.status if existing else None  # before this message changes it
        prev_escalated = conv.escalated
        budget = analysis.budget_per_unit or (float(existing.budget_per_unit) if existing and existing.budget_per_unit else None)
        products = find_products(db, org.id, analysis.product_search_terms, budget)
        trace.add("Searched products", f"{len(products)} candidate(s): " + ", ".join(p["name"] for p in products[:4]) if products else "no products found")

        try:
            query = " ".join([message, *analysis.product_search_terms])
            knowledge = search_knowledge(db, org.id, query)
            trace.add("Searched knowledge", f"{len(knowledge)} relevant passage(s)")
        except Exception:
            log.exception("Knowledge search failed")
            knowledge = []
            trace.add("Searched knowledge", "unavailable, continued without it")

        # --- 3. reply, grounded on retrieved data only ---
        known = {
            k: v
            for k, v in {
                "name": analysis.customer_name or customer_name or (existing.name if existing else None),
                "company": analysis.company or (existing.company if existing else None),
                "quantity": analysis.quantity or (existing.quantity if existing else None),
                "budget_per_unit": budget,
                "email_or_phone_shared": bool(analysis.email or analysis.phone or conv.customer_email or conv.customer_phone or (existing and (existing.email or existing.phone))),
            }.items()
            if v not in (None, False)
        }
        reply = generate_structured(
            llm,
            prompts.REPLY_SYSTEM,
            prompts.reply_prompt(_business_context(db, org), history, known, products, knowledge, message),
            Reply,
        )
        trace.add("Drafted reply", f"{len(reply.reply)} characters")

        # --- 4. escalation rules (code, not model opinion) ---
        reasons = []
        if analysis.wants_human:
            reasons.append("Customer asked for a human")
        if analysis.requests_discount:
            reasons.append("Discount requested, needs approval")
        if analysis.sensitive_request:
            reasons.append("Sensitive request (refund, contract or payment)")
        if reply.needs_human:
            reasons.append(reply.escalation_reason or "Agent could not answer from available data")
        escalation_reason = "; ".join(dict.fromkeys(reasons)) or None
        if escalation_reason:
            trace.add("Escalated to human", escalation_reason)
            conv.escalated = True
            conv.escalation_reason = escalation_reason

        # --- 5. lead capture + scoring ---
        lead: Lead | None = existing
        if analysis.category in SALES_CATEGORIES or analysis.quantity or analysis.budget_per_unit:
            in_budget = any(p.get("within_budget") for p in products) if budget else bool(products)
            lead = _merge_lead(db, org.id, conv, analysis, in_budget, customer_name or conv.customer_name)
            result = score_lead(
                ScoreInput(
                    quantity=lead.quantity,
                    budget_per_unit=float(lead.budget_per_unit) if lead.budget_per_unit else None,
                    requirement=lead.requirement,
                    use_case=lead.use_case,
                    timeline=lead.timeline,
                    email=lead.email,
                    phone=lead.phone,
                    company=lead.company,
                    purchase_stage=lead.purchase_stage,
                    product_match=lead.product_match,
                )
            )
            lead.score = result.score
            lead.intent = result.intent
            if lead.status not in ("CONVERTED", "LOST"):
                lead.status = result.status
            lead.score_reasons = result.reasons
            conv_escalation = conv.escalation_reason if conv.escalated else None
            lead.next_action = recommend_next_action(result, conv_escalation)

            unit_price = float(lead.budget_per_unit) if lead.budget_per_unit else (products[0]["price"] if products else None)
            lead.potential_value = round(unit_price * lead.quantity, 2) if (unit_price and lead.quantity) else lead.potential_value
            lead.last_interaction_at = datetime.now(timezone.utc)
            db.flush()
            conv.lead_id = lead.id
            trace.add("Scored lead", f"{lead.score}/100 ({lead.status}, intent {lead.intent}). {lead.next_action}")
        else:
            trace.add("Lead capture skipped", f"category '{analysis.category}' is not a sales inquiry")

        # --- 5b. proposed actions: the model proposes, the tool layer validates, applies policy and logs ---
        action_rows: list[dict] = []
        proposed = list(reply.actions)
        # A discounted quote is built by code from what the customer actually asked for, so the approval
        # gate never depends on the reply model choosing the right tool.
        if (
            lead is not None
            and analysis.requests_discount
            and analysis.requested_discount_pct
            and analysis.chosen_product_name
            and lead.quantity
        ):
            proposed = [a for a in proposed if a.tool != "create_quote"]
            proposed.insert(
                0,
                ProposedAction(
                    tool="create_quote",
                    product_name=analysis.chosen_product_name,
                    quantity=lead.quantity,
                    discount_pct=analysis.requested_discount_pct,
                ),
            )
        for act in proposed[:3]:
            if lead is None:
                trace.add("Skipped action", f"{act.tool}: no lead yet")
                continue
            call = run_tool(
                db, org_id=org.id, lead=lead, tool=act.tool, raw_args=act.args(), run_id=run.id, conversation_id=conv.id
            )
            note = call.summary if call.status != "failed" else f"{call.summary}: {call.error}"
            trace.add({"executed": "Ran action", "pending_approval": "Action needs approval", "failed": "Action failed"}[call.status], note)
            if call.status == "pending_approval" and not conv.escalated:
                conv.escalated = True
                conv.escalation_reason = call.approval_reason
                escalation_reason = call.approval_reason
            action_rows.append({"id": call.id, "tool": call.tool, "status": call.status, "summary": call.summary, "error": call.error})

        # --- 5c. workflows: events from this message trigger the org's enabled workflows ---
        if lead is not None:
            events = []
            if existing is None:
                events.append("lead.created")
            if lead.status == "HOT" and prev_status != "HOT":
                events.append("lead.hot")
            if escalation_reason and not prev_escalated:
                events.append("conversation.escalated")
            for event in events:
                for wf, wrun in fire(db, org_id=org.id, lead=lead, trigger=event):
                    ran = [s for s in wrun.steps if s["status"] != "skipped"]
                    trace.add(f"Workflow '{wf.name}'", f"{wrun.status}, {len(ran)} step(s) ({event})" + (f": {wrun.error}" if wrun.error else ""))

        # --- 6. save reply + finish run ---
        db.add(Message(org_id=org.id, conversation_id=conv.id, seq=next_seq + 1, role="agent", content=reply.reply))
        trace.add("Completed")
        run.status = "escalated" if escalation_reason else "completed"
        run.summary = (
            f"{analysis.category}; "
            + (f"lead {lead.score}/100 {lead.status}" if lead else "no lead")
            + (f"; escalated: {escalation_reason}" if escalation_reason else "")
        )
        run.steps = list(trace.steps)
        run.duration_ms = int((time.monotonic() - started) * 1000)
        db.commit()
        return ChatResult(
            conversation_id=conv.id,
            reply=reply.reply,
            escalated=bool(escalation_reason),
            escalation_reason=escalation_reason,
            lead=lead,
            run_id=run.id,
            steps=trace.steps,
            products=products,
            actions=action_rows,
        )
    except LLMError as e:
        db.rollback()
        run = db.get(AgentRun, run.id)
        fail(e)
        raise
    except Exception as e:
        log.exception("Sales agent crashed")
        db.rollback()
        run = db.get(AgentRun, run.id)
        fail(e)
        raise
