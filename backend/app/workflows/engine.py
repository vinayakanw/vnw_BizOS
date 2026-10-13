"""Workflow engine. Runs enabled workflows for an org when an event happens.

- Steps go through the same tool layer as the agent (validation, policy, approval gate, audit log).
- A workflow runs at most once per lead (manual runs excepted).
- A broken workflow is recorded as failed and never breaks the caller.
"""

import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Lead, Workflow, WorkflowRun
from app.tools import run_tool
from app.workflows.definitions import Condition, Step

log = logging.getLogger("bizos.workflows")

_VAR = re.compile(r"\{lead\.(name|company|email|phone|score|status|quantity|potential_value|requirement|next_action|days_since_contact)\}")
_SHORT_KEYS = {"title", "subject"}


def days_since_contact(lead: Lead) -> float:
    base = lead.last_interaction_at or lead.created_at
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return max((datetime.now(timezone.utc) - base).total_seconds() / 86400, 0.0)


def _value(lead: Lead, field: str):
    if field == "days_since_contact":
        return days_since_contact(lead)
    v = getattr(lead, field, None)
    return float(v) if hasattr(v, "quantize") else v  # Decimal -> float


def check(cond: Condition, lead: Lead) -> bool:
    v = _value(lead, cond.field)
    if cond.op == "is_set":
        return v not in (None, "")
    if cond.op == "not_set":
        return v in (None, "")
    if v is None:
        return False
    try:
        if cond.op in ("gte", "lte"):
            a, b = float(v), float(cond.value)  # type: ignore[arg-type]
            return a >= b if cond.op == "gte" else a <= b
    except (TypeError, ValueError):
        return False
    a, b = str(v).lower(), str(cond.value).lower()
    return {"eq": a == b, "neq": a != b, "contains": b in a}[cond.op]


def render(text: str, lead: Lead) -> str:
    def sub(m: re.Match) -> str:
        key = m.group(1)
        v = lead.name or lead.email or "the customer" if key == "name" else _value(lead, key)
        if v in (None, ""):
            return ""
        if key == "potential_value":
            return f"{(lead.currency or 'INR')} {float(v):,.0f}"
        if key == "quantity":
            return str(int(v))
        if key == "days_since_contact":
            return str(int(v))
        return str(v)

    return _VAR.sub(sub, text)


def _render_args(args: dict, lead: Lead) -> dict:
    out = {}
    for k, v in args.items():
        if isinstance(v, str):
            v = render(v, lead).strip()
            v = v[:200] if k in _SHORT_KEYS else v[:4000]
        out[k] = v
    return out


def _execute(db: Session, wf: Workflow, lead: Lead, trigger: str) -> WorkflowRun:
    run = WorkflowRun(org_id=wf.org_id, workflow_id=wf.id, lead_id=lead.id, trigger=trigger, status="completed", steps=[])
    db.add(run)
    trace: list[dict] = []
    ok = bad = 0
    for raw in wf.steps:
        step = Step.model_validate(raw)
        if step.condition and not check(step.condition, lead):
            trace.append({"tool": step.tool, "status": "skipped", "summary": "Condition not met", "error": None, "tool_call_id": None})
            continue
        call = run_tool(db, org_id=wf.org_id, lead=lead, tool=step.tool, raw_args=_render_args(step.args, lead))
        trace.append({"tool": step.tool, "status": call.status, "summary": call.summary, "error": call.error, "tool_call_id": call.id})
        if call.status == "failed":
            bad += 1
        else:
            ok += 1
    run.steps = trace
    run.status = "failed" if bad and not ok else "partial" if bad else "completed"
    return run


def run_workflow(db: Session, wf: Workflow, lead: Lead, trigger: str) -> WorkflowRun:
    """Run one workflow on one lead, isolated in a savepoint. Never raises."""
    if wf.org_id != lead.org_id:  # defensive: never mix tenants
        raise ValueError("Workflow and lead belong to different organizations")
    try:
        with db.begin_nested():
            run = _execute(db, wf, lead, trigger)
    except Exception as e:
        log.exception("Workflow %s crashed", wf.id)
        run = WorkflowRun(
            org_id=wf.org_id, workflow_id=wf.id, lead_id=lead.id, trigger=trigger,
            status="failed", steps=[], error=f"Unexpected error: {e}"[:300],
        )
        db.add(run)
    db.flush()
    return run


def fire(db: Session, *, org_id: str, lead: Lead, trigger: str) -> list[tuple[Workflow, WorkflowRun]]:
    """Run every enabled workflow of this org that listens to `trigger`."""
    results = []
    wfs = db.scalars(
        select(Workflow).where(Workflow.org_id == org_id, Workflow.enabled.is_(True), Workflow.trigger == trigger).order_by(Workflow.created_at)
    ).all()
    for wf in wfs:
        try:
            if not all(check(Condition.model_validate(c), lead) for c in wf.conditions):
                continue
        except Exception:
            log.exception("Bad conditions on workflow %s", wf.id)
            continue
        done_before = db.scalar(
            select(WorkflowRun.id).where(
                WorkflowRun.org_id == org_id, WorkflowRun.workflow_id == wf.id, WorkflowRun.lead_id == lead.id,
                WorkflowRun.status.in_(("completed", "partial")), WorkflowRun.trigger != "manual",
            ).limit(1)
        )
        if done_before:
            continue
        results.append((wf, run_workflow(db, wf, lead, trigger)))
    return results
