"""The analytics catalog. Every number the analytics agent can ever state comes from one of these functions.

Each one reads only the given org's rows and returns:
  title, window_days, facts (headline numbers), columns + rows (a table to show the user).
Aggregation is done in Python so it behaves the same on SQLite and Postgres (fine at SMB data sizes).
"""

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentRun, Lead, LeadTask, Quote, Ticket, ToolCall
from app.workflows.engine import days_since_contact

CLOSED = ("CONVERTED", "LOST")
STATUS_ORDER = ("HOT", "WARM", "QUALIFYING", "NEW", "CONVERTED", "LOST")


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _f(v) -> float:
    return float(v) if v is not None else 0.0


def _name(l: Lead) -> str:
    return l.name or l.email or "Unknown customer"


def _pct(a: float, b: float) -> float:
    return round(100 * a / b, 1) if b else 0.0


def pipeline_summary(db: Session, org_id: str, days: int | None = None, **_) -> dict:
    q = select(Lead).where(Lead.org_id == org_id)
    if days:
        q = q.where(Lead.created_at >= _since(days))
    leads = db.scalars(q).all()
    by = defaultdict(lambda: [0, 0.0])
    for l in leads:
        by[l.status][0] += 1
        by[l.status][1] += _f(l.potential_value)
    won, lost = by["CONVERTED"][0], by["LOST"][0]
    facts = {
        "total_leads": len(leads),
        "open_pipeline_value": sum(v for s, (_, v) in by.items() if s not in CLOSED),
        "won_value": by["CONVERTED"][1],
        "lost_value": by["LOST"][1],
        "win_rate_pct": _pct(won, won + lost),
        "currency": "INR",
    }
    return {
        "title": "Pipeline by status",
        "window_days": days,
        "facts": facts,
        "columns": ["status", "leads", "potential_value"],
        "rows": [[s, by[s][0], by[s][1]] for s in STATUS_ORDER if s in by],
    }


def leads_over_time(db: Session, org_id: str, days: int | None = 14, **_) -> dict:
    days = days or 14
    leads = db.scalars(select(Lead).where(Lead.org_id == org_id, Lead.created_at >= _since(days))).all()
    per_day = Counter(_utc(l.created_at).date() for l in leads)
    today = datetime.now(timezone.utc).date()
    rows = [[(today - timedelta(days=i)).isoformat(), per_day.get(today - timedelta(days=i), 0)] for i in range(days - 1, -1, -1)]
    return {
        "title": f"New leads per day (UTC dates)",
        "window_days": days,
        "facts": {"new_leads": len(leads), "busiest_day_leads": max((r[1] for r in rows), default=0)},
        "columns": ["date", "new_leads"],
        "rows": rows,
    }


def top_leads(db: Session, org_id: str, n: int | None = 5, order_by: str | None = "score", **_) -> dict:
    n = n or 5
    key = (lambda l: _f(l.potential_value)) if order_by == "value" else (lambda l: l.score)
    leads = [l for l in db.scalars(select(Lead).where(Lead.org_id == org_id, Lead.status.notin_(CLOSED))).all()]
    leads.sort(key=key, reverse=True)
    top = leads[:n]
    return {
        "title": f"Top {len(top)} open leads by {'potential value' if order_by == 'value' else 'score'}",
        "window_days": None,
        "facts": {"open_leads": len(leads), "shown": len(top)},
        "columns": ["lead", "company", "status", "score", "potential_value"],
        "rows": [[_name(l), l.company or "", l.status, l.score, _f(l.potential_value)] for l in top],
    }


def stale_leads(db: Session, org_id: str, days: int | None = 3, n: int | None = 10, **_) -> dict:
    days, n = days or 3, n or 10
    leads = db.scalars(select(Lead).where(Lead.org_id == org_id, Lead.status.notin_(CLOSED))).all()
    quiet = sorted(((days_since_contact(l), l) for l in leads if days_since_contact(l) >= days), key=lambda x: -x[0])
    return {
        "title": f"Open leads quiet for {days}+ days",
        "window_days": days,
        "facts": {"quiet_leads": len(quiet), "open_leads": len(leads)},
        "columns": ["lead", "status", "days_quiet", "potential_value"],
        "rows": [[_name(l), l.status, int(d), _f(l.potential_value)] for d, l in quiet[:n]],
    }


def quotes_summary(db: Session, org_id: str, days: int | None = 30, **_) -> dict:
    days = days or 30
    quotes = db.scalars(select(Quote).where(Quote.org_id == org_id, Quote.created_at >= _since(days))).all()
    per_product = defaultdict(lambda: [0, 0.0])
    for q in quotes:
        for it in q.items or []:
            per_product[it.get("product", "?")][0] += int(it.get("quantity", 0))
            per_product[it.get("product", "?")][1] += _f(it.get("line_total"))
    rows = sorted(([p, u, v] for p, (u, v) in per_product.items()), key=lambda r: -r[2])
    return {
        "title": "Quotes by product (before discount)",
        "window_days": days,
        "facts": {
            "quotes": len(quotes),
            "total_quoted_value_after_discount": sum(_f(q.total) for q in quotes),
            "average_discount_pct": round(sum(_f(q.discount_pct) for q in quotes) / len(quotes), 1) if quotes else 0.0,
            "currency": quotes[0].currency if quotes else "INR",
        },
        "columns": ["product", "units_quoted", "value_before_discount"],
        "rows": rows,
    }


def approvals_summary(db: Session, org_id: str, days: int | None = 30, **_) -> dict:
    days = days or 30
    calls = db.scalars(select(ToolCall).where(ToolCall.org_id == org_id, ToolCall.created_at >= _since(days))).all()
    by_tool = defaultdict(Counter)
    for c in calls:
        by_tool[c.tool][c.status] += 1
    st = Counter(c.status for c in calls)
    human = [c for c in calls if c.decided_by]
    return {
        "title": "Agent actions by tool",
        "window_days": days,
        "facts": {
            "total_actions": len(calls),
            "executed": st["executed"],
            "pending_approval": st["pending_approval"],
            "rejected": st["rejected"],
            "failed": st["failed"],
            "decided_by_a_human": len(human),
            "human_rejection_rate_pct": _pct(sum(1 for c in human if c.status == "rejected"), len(human)),
        },
        "columns": ["tool", "executed", "pending_approval", "rejected", "failed"],
        "rows": [[t, c["executed"], c["pending_approval"], c["rejected"], c["failed"]] for t, c in sorted(by_tool.items())],
    }


def tasks_summary(db: Session, org_id: str, n: int | None = 10, **_) -> dict:
    n = n or 10
    tasks = db.scalars(select(LeadTask).where(LeadTask.org_id == org_id)).all()
    now = datetime.now(timezone.utc)
    open_ = sorted((t for t in tasks if t.status == "open"), key=lambda t: _utc(t.due_at) if t.due_at else now)
    overdue = [t for t in open_ if t.due_at and _utc(t.due_at) < now]
    return {
        "title": "Open tasks (soonest due first)",
        "window_days": None,
        "facts": {"open": len(open_), "done": len(tasks) - len(open_), "overdue": len(overdue)},
        "columns": ["task", "due", "overdue"],
        "rows": [[t.title, _utc(t.due_at).date().isoformat() if t.due_at else "", bool(t in overdue)] for t in open_[:n]],
    }


def agent_activity(db: Session, org_id: str, days: int | None = 30, **_) -> dict:
    days = days or 30
    runs = db.scalars(select(AgentRun).where(AgentRun.org_id == org_id, AgentRun.agent == "sales", AgentRun.created_at >= _since(days))).all()
    st = Counter(r.status for r in runs)
    durs = [r.duration_ms for r in runs if r.duration_ms]
    return {
        "title": "Sales agent runs by outcome",
        "window_days": days,
        "facts": {
            "runs": len(runs),
            "escalation_rate_pct": _pct(st["escalated"], len(runs)),
            "failure_rate_pct": _pct(st["failed"], len(runs)),
            "average_seconds": round(sum(durs) / len(durs) / 1000, 1) if durs else 0.0,
        },
        "columns": ["outcome", "runs"],
        "rows": [[k, v] for k, v in sorted(st.items())],
    }


def tickets_summary(db: Session, org_id: str, days: int | None = 30, **_) -> dict:
    days = days or 30
    tickets = db.scalars(select(Ticket).where(Ticket.org_id == org_id, Ticket.created_at >= _since(days))).all()
    st = Counter(t.status for t in tickets)
    by_cat = defaultdict(Counter)
    for t in tickets:
        by_cat[t.category][t.status] += 1
    return {
        "title": "Support tickets by category",
        "window_days": days,
        "facts": {
            "tickets": len(tickets),
            "open": st["open"],
            "in_progress": st["in_progress"],
            "resolved": st["resolved"],
            "high_priority_unresolved": sum(1 for t in tickets if t.priority == "high" and t.status != "resolved"),
        },
        "columns": ["category", "open", "in_progress", "resolved"],
        "rows": [[c, n["open"], n["in_progress"], n["resolved"]] for c, n in sorted(by_cat.items())],
    }


CATALOG: dict[str, tuple[Callable[..., dict], str]] = {
    "pipeline_summary": (pipeline_summary, "Leads and money by status: open pipeline value, won, lost, win rate. Optional days = only leads created in the last N days."),
    "leads_over_time": (leads_over_time, "New leads per day for the last N days (days, default 14)."),
    "top_leads": (top_leads, "Best open leads. n = how many (default 5), order_by = score or value."),
    "stale_leads": (stale_leads, "Open leads that have gone quiet. days = quiet for at least this many days (default 3), n = how many to list."),
    "quotes_summary": (quotes_summary, "Quotes in the last N days (default 30): count, total value, average discount, units and value per product."),
    "approvals_summary": (approvals_summary, "Actions the agent and workflows took in the last N days (default 30): executed, waiting for approval, rejected, failed, per tool."),
    "tasks_summary": (tasks_summary, "Follow-up tasks: how many open, done and overdue, and the next ones due."),
    "tickets_summary": (tickets_summary, "Support tickets created in the last N days (default 30): open, in progress, resolved, high priority, per category."),
    "agent_activity": (agent_activity, "How the sales agent performed in the last N days (default 30): runs, escalation rate, failure rate, average time."),
}


def run_metric(db: Session, org_id: str, metric: str, **params) -> dict:
    fn, _ = CATALOG[metric]
    return {"metric": metric, **fn(db, org_id, **params)}
