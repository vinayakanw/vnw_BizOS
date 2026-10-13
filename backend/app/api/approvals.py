from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth
from app import customer_comms as comms
from app.core.db import get_db
from app.models import ApprovalRules, Lead, Quote, ToolCall
from app.schemas_agent import ReasonIn, RulesIn, ToolCallOut
from app.tools.registry import Rules, ToolError, decide_tool_call, load_rules, run_tool

router = APIRouter(tags=["approvals"])


def _out(db: Session, org_id: str, calls: list[ToolCall]) -> list[ToolCallOut]:
    ids = {c.lead_id for c in calls if c.lead_id}
    names = {}
    if ids:
        for l in db.scalars(select(Lead).where(Lead.id.in_(ids), Lead.org_id == org_id)).all():
            names[l.id] = l.name or l.email or "Unknown customer"
    out = []
    for c in calls:
        o = ToolCallOut.model_validate(c)
        o.lead_name = names.get(c.lead_id) if c.lead_id else None
        out.append(o)
    return out


@router.get("/approvals", response_model=list[ToolCallOut])
def pending_approvals(auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    calls = db.scalars(
        select(ToolCall).where(ToolCall.org_id == auth.org_id, ToolCall.status == "pending_approval").order_by(ToolCall.created_at.asc())
    ).all()
    return _out(db, auth.org_id, list(calls))


@router.get("/tool-calls", response_model=list[ToolCallOut])
def tool_calls(limit: int = Query(default=50, ge=1, le=200), auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    calls = db.scalars(select(ToolCall).where(ToolCall.org_id == auth.org_id).order_by(ToolCall.created_at.desc()).limit(limit)).all()
    return _out(db, auth.org_id, list(calls))


def _require_approver(auth: AuthContext) -> None:
    if auth.user.role not in ("owner", "admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owners and admins can do this")


def _decide(call_id: str, approve: bool, auth: AuthContext, db: Session, reason: str | None = None) -> ToolCallOut:
    _require_approver(auth)
    try:
        call = decide_tool_call(
            db, org_id=auth.org_id, call_id=call_id, approve=approve, decided_by=auth.user.full_name, reason=(reason or "").strip() or None
        )
    except ToolError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    if call is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Action not found")
    db.commit()
    db.refresh(call)
    if approve and call.tool == "create_quote" and call.status == "executed":  # an approved quote now reaches the customer
        quote_id = (call.result or {}).get("quote_id")
        quote = db.scalar(select(Quote).where(Quote.id == quote_id, Quote.org_id == auth.org_id)) if quote_id else None
        if quote is not None:
            comms.deliver_quote(db, auth.org, quote)
    return _out(db, auth.org_id, [call])[0]


@router.post("/approvals/{call_id}/approve", response_model=ToolCallOut)
def approve(call_id: str, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    return _decide(call_id, True, auth, db)


@router.post("/approvals/{call_id}/reject", response_model=ToolCallOut)
def reject(call_id: str, body: ReasonIn | None = None, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    return _decide(call_id, False, auth, db, body.reason if body else None)


@router.get("/approvals/count")
def pending_count(auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    n = db.scalar(select(func.count()).select_from(ToolCall).where(ToolCall.org_id == auth.org_id, ToolCall.status == "pending_approval"))
    return {"pending": n or 0}


def _rules_out(r: Rules) -> dict:
    return {
        "auto_discount_max_pct": r.auto_discount_max_pct,
        "auto_discount_min_qty": r.auto_discount_min_qty,
        "quote_approval_above": r.quote_approval_above,
        "always_approve_tools": r.always_approve_tools,
    }


@router.get("/approvals/rules")
def get_rules(auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    return _rules_out(load_rules(db, auth.org_id))


@router.put("/approvals/rules")
def put_rules(body: RulesIn, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    _require_approver(auth)
    row = db.scalar(select(ApprovalRules).where(ApprovalRules.org_id == auth.org_id))
    if row is None:
        row = ApprovalRules(org_id=auth.org_id, auto_discount_max_pct=0, auto_discount_min_qty=1)
        db.add(row)
    row.auto_discount_max_pct = body.auto_discount_max_pct
    row.auto_discount_min_qty = body.auto_discount_min_qty
    row.quote_approval_above = body.quote_approval_above
    row.always_approve_tools = list(dict.fromkeys(body.always_approve_tools))
    db.commit()
    return _rules_out(load_rules(db, auth.org_id))


@router.post("/tool-calls/{call_id}/send", response_model=ToolCallOut)
def send_draft(call_id: str, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    """A human sends an email draft. Goes through the normal tool path so it is validated, logged, and attributed to them."""
    _require_approver(auth)
    draft = db.scalar(select(ToolCall).where(ToolCall.id == call_id, ToolCall.org_id == auth.org_id))
    if draft is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Draft not found")
    if draft.tool != "draft_email" or draft.status != "executed" or not draft.result:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a saved email draft can be sent")
    lead = db.scalar(select(Lead).where(Lead.id == draft.lead_id, Lead.org_id == auth.org_id)) if draft.lead_id else None
    if lead is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "The lead no longer exists")
    raw = {"subject": draft.result.get("subject"), "body": draft.result.get("body")}
    already = db.scalars(
        select(ToolCall).where(ToolCall.org_id == auth.org_id, ToolCall.lead_id == lead.id, ToolCall.tool == "send_email", ToolCall.status == "executed")
    ).all()
    if any(c.args == raw for c in already):
        raise HTTPException(status.HTTP_409_CONFLICT, "This email was already sent")
    call = run_tool(db, org_id=auth.org_id, lead=lead, tool="send_email", raw_args=raw, conversation_id=draft.conversation_id)
    if call.status == "pending_approval":  # the clicking human is the approver
        call = decide_tool_call(db, org_id=auth.org_id, call_id=call.id, approve=True, decided_by=auth.user.full_name)  # type: ignore[assignment]
    db.commit()
    db.refresh(call)
    return _out(db, auth.org_id, [call])[0]
