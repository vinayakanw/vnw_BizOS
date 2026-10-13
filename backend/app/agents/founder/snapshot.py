"""Founder snapshot. Everything the briefing may say comes from here, computed in code for one org.

`facts` are headline numbers. `items` are the things that need a decision, each with a code-written
title, detail, severity and a link into the app. The model only ranks items and says why they matter.
"""

from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.analytics.metrics import CLOSED, _f, _name, _utc
from app.models import Lead, LeadTask, Quote, Ticket, ToolCall
from app.workflows.engine import days_since_contact

SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}


def _inr(n: float) -> str:
    return f"Rs {n:,.0f}"


def build_snapshot(db: Session, org_id: str, days: int = 7) -> dict:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    leads = db.scalars(select(Lead).where(Lead.org_id == org_id)).all()
    open_leads = [l for l in leads if l.status not in CLOSED]
    new_leads = [l for l in leads if _utc(l.created_at) >= since]
    quotes = db.scalars(select(Quote).where(Quote.org_id == org_id, Quote.created_at >= since)).all()
    tasks = db.scalars(select(LeadTask).where(LeadTask.org_id == org_id, LeadTask.status == "open")).all()
    tickets = db.scalars(select(Ticket).where(Ticket.org_id == org_id)).all()
    calls = db.scalars(select(ToolCall).where(ToolCall.org_id == org_id, ToolCall.created_at >= since)).all()
    pending = db.scalars(select(ToolCall).where(ToolCall.org_id == org_id, ToolCall.status == "pending_approval")).all()

    won = [l for l in leads if l.status == "CONVERTED"]
    lost = [l for l in leads if l.status == "LOST"]
    overdue = [t for t in tasks if t.due_at and _utc(t.due_at) < now]
    unresolved = [t for t in tickets if t.status != "resolved"]
    high_tickets = [t for t in unresolved if t.priority == "high"]
    hot_waiting = [l for l in open_leads if l.status == "HOT" and days_since_contact(l) >= 1]
    quiet = [l for l in open_leads if l.status != "HOT" and days_since_contact(l) >= 3]
    failed = [c for c in calls if c.status == "failed"]
    resolved_period = [t for t in tickets if t.status == "resolved" and t.updated_at and _utc(t.updated_at) >= since]

    facts = {
        "period_days": days,
        "currency": "INR",
        "new_leads": len(new_leads),
        "open_leads": len(open_leads),
        "open_pipeline_value": sum(_f(l.potential_value) for l in open_leads),
        "hot_leads": sum(1 for l in open_leads if l.status == "HOT"),
        "won_deals_total": len(won),
        "won_value_total": sum(_f(l.potential_value) for l in won),
        "lost_deals_total": len(lost),
        "quotes_created": len(quotes),
        "quoted_value": sum(_f(q.total) for q in quotes),
        "actions_waiting_approval": len(pending),
        "open_tasks": len(tasks),
        "overdue_tasks": len(overdue),
        "unresolved_tickets": len(unresolved),
        "high_priority_tickets": len(high_tickets),
        "tickets_resolved_in_period": len(resolved_period),
    }

    items: list[dict] = []

    if pending:
        oldest = max((now - _utc(c.created_at)).days for c in pending)
        items.append({
            "id": "approvals", "severity": "high" if oldest >= 1 or len(pending) >= 3 else "medium",
            "title": f"{len(pending)} agent action(s) waiting for your approval",
            "detail": f"Oldest has waited {oldest} day(s). Customers are waiting on discounts or quotes." if oldest else "Customers may be waiting on these.",
            "link": "/approvals",
        })
    if hot_waiting:
        value = sum(_f(l.potential_value) for l in hot_waiting)
        names = ", ".join(_name(l) for l in sorted(hot_waiting, key=lambda l: -_f(l.potential_value))[:3])
        items.append({
            "id": "hot_leads", "severity": "high",
            "title": f"{len(hot_waiting)} hot lead(s) with no contact for a day or more",
            "detail": f"Worth {_inr(value)} in total. Biggest: {names}.",
            "link": "/leads",
        })
    if high_tickets:
        items.append({
            "id": "tickets_high", "severity": "high",
            "title": f"{len(high_tickets)} high priority support ticket(s) still unresolved",
            "detail": "Oldest: " + ", ".join(t.number + " " + t.subject[:50] for t in sorted(high_tickets, key=lambda t: t.created_at)[:2]),
            "link": "/tickets",
        })
    if overdue:
        items.append({
            "id": "overdue_tasks", "severity": "medium",
            "title": f"{len(overdue)} follow-up task(s) overdue",
            "detail": "e.g. " + "; ".join(t.title[:60] for t in sorted(overdue, key=lambda t: _utc(t.due_at))[:2]),
            "link": "/leads",
        })
    if quiet:
        value = sum(_f(l.potential_value) for l in quiet)
        items.append({
            "id": "quiet_leads", "severity": "medium" if value > 0 else "low",
            "title": f"{len(quiet)} open lead(s) gone quiet for 3+ days",
            "detail": f"Together worth {_inr(value)}. The Quiet lead nudge workflow can handle these.",
            "link": "/workflows",
        })
    if failed:
        items.append({
            "id": "failed_actions", "severity": "medium",
            "title": f"{len(failed)} agent action(s) failed in the last {days} day(s)",
            "detail": "e.g. " + "; ".join((c.error or c.summary)[:70] for c in failed[:2]),
            "link": "/activity",
        })
    unresolved_other = len(unresolved) - len(high_tickets)
    if unresolved_other > 0:
        items.append({
            "id": "tickets_open", "severity": "low",
            "title": f"{unresolved_other} other support ticket(s) open",
            "detail": "Normal or low priority.",
            "link": "/tickets",
        })

    items.sort(key=lambda i: SEVERITY_RANK[i["severity"]])
    status_counts = Counter(l.status for l in open_leads)
    return {"facts": facts, "items": items, "open_by_status": dict(status_counts)}
