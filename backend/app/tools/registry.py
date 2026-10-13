"""Tool layer. The model can only *propose* a tool call; this module decides what happens.

For every proposal:
  1. arguments are validated against a strict schema (bad args are logged as failed, never run)
  2. a policy check decides: run now, or park it as pending_approval for a human
  3. handlers only touch rows of the lead's own org, and take prices and stock from the database
  4. the outcome is written to tool_calls, which is both the audit log and the approval queue

Nothing here sends email or talks to the outside world. Emails are drafts only.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations import providers, service as integrations
from app.models import ApprovalRules, Lead, LeadTask, Product, Quote, ToolCall

log = logging.getLogger("bizos.tools")


class ToolError(Exception):
    """A handler refused to act (unknown product, not enough stock...). Shown to the human, not a crash."""


@dataclass
class Ctx:
    db: Session
    org_id: str
    lead: Lead


# ---- argument schemas -------------------------------------------------------------------

class QuoteArgs(BaseModel):
    product_name: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1, le=100000)
    discount_pct: float = Field(default=0, ge=0, le=100)


class TaskArgs(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_in_days: int = Field(default=1, ge=0, le=60)


class EmailArgs(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)


# ---- handlers: return (summary, result) -------------------------------------------------

def _money(n: Decimal | float, cur: str) -> str:
    return f"{cur} {float(n):,.2f}"


def _find_product(db: Session, org_id: str, name: str) -> Product:
    base = select(Product).where(Product.org_id == org_id, Product.is_active.is_(True))
    exact = db.scalars(base.where(func.lower(Product.name) == name.strip().lower())).all()
    if len(exact) == 1:
        return exact[0]
    loose = db.scalars(base.where(Product.name.ilike(f"%{name.strip()}%"))).all()
    if len(loose) == 1:
        return loose[0]
    if not loose:
        raise ToolError(f"No active product named '{name}'")
    raise ToolError(f"'{name}' matches several products: " + ", ".join(p.name for p in loose[:4]))


def _create_quote(ctx: Ctx, a: QuoteArgs) -> tuple[str, dict]:
    p = _find_product(ctx.db, ctx.org_id, a.product_name)
    if p.stock is not None and a.quantity > p.stock:
        raise ToolError(f"Only {p.stock} of {p.name} in stock, requested {a.quantity}")
    unit = Decimal(p.price)
    subtotal = (unit * a.quantity).quantize(Decimal("0.01"), ROUND_HALF_UP)
    disc = Decimal(str(a.discount_pct))
    total = (subtotal * (Decimal(100) - disc) / Decimal(100)).quantize(Decimal("0.01"), ROUND_HALF_UP)
    count = ctx.db.scalar(select(func.count()).select_from(Quote).where(Quote.org_id == ctx.org_id)) or 0
    q = Quote(
        org_id=ctx.org_id,
        lead_id=ctx.lead.id,
        number=f"Q-{count + 1:04d}",
        items=[{"product": p.name, "unit_price": float(unit), "quantity": a.quantity, "line_total": float(subtotal)}],
        currency=p.currency,
        subtotal=subtotal,
        discount_pct=disc,
        total=total,
    )
    ctx.db.add(q)
    ctx.db.flush()
    d = f" with {a.discount_pct:g}% discount" if disc else ""
    return (
        f"{q.number}: {a.quantity} x {p.name}{d}, total {_money(total, p.currency)}",
        {"quote_id": q.id, "number": q.number, "total": float(total), "currency": p.currency},
    )


def _create_task(ctx: Ctx, a: TaskArgs) -> tuple[str, dict]:
    due = datetime.now(timezone.utc) + timedelta(days=a.due_in_days)
    t = LeadTask(org_id=ctx.org_id, lead_id=ctx.lead.id, title=a.title.strip(), due_at=due)
    ctx.db.add(t)
    ctx.db.flush()
    return f"{t.title} (due in {a.due_in_days} day(s))", {"task_id": t.id}


def _draft_email(ctx: Ctx, a: EmailArgs) -> tuple[str, dict]:
    to = ctx.lead.email
    note = "" if to else " (no email on the lead yet)"
    return (
        f"'{a.subject}'{note}. Draft only, not sent.",
        {"to": to, "subject": a.subject, "body": a.body, "sent": False},
    )


def _send_email(ctx: Ctx, a: EmailArgs) -> tuple[str, dict]:
    to = ctx.lead.email
    if not to:
        raise ToolError("The lead has no email address")
    cfg = integrations.get_config(ctx.db, ctx.org_id, "email")
    if not cfg:
        raise ToolError("Email is not connected. Set it up under Integrations")
    try:
        message_id = providers.send_email(cfg, to, a.subject, a.body)
    except providers.IntegrationError as e:
        raise ToolError(str(e))
    return f"Email '{a.subject}' sent to {to}", {"to": to, "subject": a.subject, "body": a.body, "sent": True, "message_id": message_id}


# ---- policy: return a reason when a human must approve first ----------------------------

@dataclass
class Rules:
    auto_discount_max_pct: float
    auto_discount_min_qty: int
    quote_approval_above: float | None
    always_approve_tools: list[str]


def load_rules(db: Session, org_id: str) -> Rules:
    row = db.scalar(select(ApprovalRules).where(ApprovalRules.org_id == org_id))
    if row is None:
        return Rules(settings.auto_discount_max_pct, settings.auto_discount_min_qty, None, [])
    return Rules(
        float(row.auto_discount_max_pct),
        row.auto_discount_min_qty,
        float(row.quote_approval_above) if row.quote_approval_above is not None else None,
        list(row.always_approve_tools or []),
    )


def _quote_policy(a: QuoteArgs, lead: Lead, rules: Rules, db: Session) -> str | None:
    reasons = []
    d = a.discount_pct
    if d > 0 and not (a.quantity >= rules.auto_discount_min_qty and d <= rules.auto_discount_max_pct):
        reasons.append(
            f"{d:g}% discount on {a.quantity} unit(s) is outside the auto-approval rule "
            f"(up to {rules.auto_discount_max_pct:g}% on {rules.auto_discount_min_qty}+ units)"
        )
    if rules.quote_approval_above is not None:
        try:
            p = _find_product(db, lead.org_id, a.product_name)
            total = float(p.price) * a.quantity * (1 - d / 100)
            if total > rules.quote_approval_above:
                reasons.append(f"Quote total {p.currency} {total:,.0f} is above your approval limit of {rules.quote_approval_above:,.0f}")
        except ToolError:
            pass  # unknown product: the handler reports it
    return "; ".join(reasons) or None


def _always_human(a: BaseModel, lead: Lead, rules: Rules, db: Session) -> str | None:
    return "Sending a real email to a customer always needs a human decision"


@dataclass
class ToolSpec:
    name: str
    args_model: type[BaseModel]
    handler: Callable[[Ctx, BaseModel], tuple[str, dict]]
    policy: Callable[[BaseModel, Lead, Rules, Session], str | None] = lambda a, l, r, d: None


REGISTRY: dict[str, ToolSpec] = {
    "create_quote": ToolSpec("create_quote", QuoteArgs, _create_quote, _quote_policy),
    "create_followup_task": ToolSpec("create_followup_task", TaskArgs, _create_task),
    "draft_email": ToolSpec("draft_email", EmailArgs, _draft_email),
    # Not proposable by the model or by workflows (their schemas list tools explicitly). A human starts it, a human approves it.
    "send_email": ToolSpec("send_email", EmailArgs, _send_email, _always_human),
}
TOOL_NAMES = tuple(REGISTRY)


# ---- execution --------------------------------------------------------------------------

def _execute(db: Session, call: ToolCall, spec: ToolSpec, args: BaseModel, lead: Lead) -> None:
    """Run the handler in a savepoint so a failure leaves no half-written rows behind."""
    try:
        with db.begin_nested():
            summary, result = spec.handler(Ctx(db, call.org_id, lead), args)
        call.status, call.summary, call.result, call.error = "executed", summary, result, None
    except ToolError as e:
        call.status, call.error = "failed", str(e)
        call.summary = f"{spec.name} could not run"
    except Exception as e:  # unexpected: log it, keep the agent alive
        log.exception("Tool %s crashed", spec.name)
        call.status, call.error = "failed", f"Unexpected error: {e}"[:300]
        call.summary = f"{spec.name} crashed"


def run_tool(
    db: Session,
    *,
    org_id: str,
    lead: Lead,
    tool: str,
    raw_args: dict,
    run_id: str | None = None,
    conversation_id: str | None = None,
) -> ToolCall:
    call = ToolCall(
        org_id=org_id, lead_id=lead.id, run_id=run_id, conversation_id=conversation_id,
        tool=tool, args=raw_args or {}, status="failed", summary="",
    )
    db.add(call)

    spec = REGISTRY.get(tool)
    if spec is None or lead.org_id != org_id:  # unknown tool, or a lead from another tenant
        call.error, call.summary = f"Unknown tool '{tool}'", "Rejected unknown tool"
        db.flush()
        return call
    try:
        args = spec.args_model.model_validate(raw_args or {})
    except ValidationError as e:
        call.error = "Invalid arguments: " + "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())[:300]
        call.summary = f"{tool} had invalid arguments"
        db.flush()
        return call

    call.args = args.model_dump()
    rules = load_rules(db, org_id)
    reasons = [r for r in (spec.policy(args, lead, rules, db),) if r]
    if tool in rules.always_approve_tools:
        reasons.append("Your approval rules require a human to approve every " + tool.replace("_", " "))
    reason = "; ".join(reasons)
    if reason:
        call.status, call.approval_reason = "pending_approval", reason
        call.summary = f"{tool} waiting for approval"
        integrations.notify_slack(db, org_id, f"Approval needed ({tool.replace('_', ' ')}): {reason[:200]}")
    else:
        _execute(db, call, spec, args, lead)
    db.flush()
    return call


def decide_tool_call(
    db: Session, *, org_id: str, call_id: str, approve: bool, decided_by: str, reason: str | None = None
) -> ToolCall | None:
    """Human decision on a pending call. Returns None when the call is not found in this org."""
    call = db.scalar(select(ToolCall).where(ToolCall.id == call_id, ToolCall.org_id == org_id))
    if call is None:
        return None
    if call.status != "pending_approval":
        raise ToolError("This action is not waiting for approval")
    call.decided_by, call.decided_at = decided_by, datetime.now(timezone.utc)
    if not approve:
        call.status, call.summary = "rejected", f"{call.tool} rejected by {decided_by}" + (f": {reason}" if reason else "")
        if reason:
            call.result = {"rejection_reason": reason}
        db.flush()
        return call

    lead = db.scalar(select(Lead).where(Lead.id == call.lead_id, Lead.org_id == org_id)) if call.lead_id else None
    spec = REGISTRY.get(call.tool)
    if lead is None or spec is None:
        call.status, call.error, call.summary = "failed", "The lead no longer exists", f"{call.tool} could not run"
    else:
        _execute(db, call, spec, spec.args_model.model_validate(call.args), lead)
    db.flush()
    return call
