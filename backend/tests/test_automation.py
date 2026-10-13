from datetime import datetime, timedelta, timezone

from app.automation import scheduler
from app.core.db import SessionLocal
from app.llm.factory import set_llm
from app.models import Lead
from tests.test_sales_agent import BUY, OK_REPLY, ScriptedLLM, _chat, _seed

NUDGE = {
    "name": "Nudge",
    "trigger": "lead.inactive",
    "conditions": [{"field": "days_since_contact", "op": "gte", "value": 3}],
    "steps": [{"tool": "create_followup_task", "args": {"title": "Follow up {lead.name}: quiet {lead.days_since_contact} days", "due_in_days": 0}}],
}


def _lead(client, headers):
    _seed(client, headers)
    set_llm(ScriptedLLM([BUY], [OK_REPLY]))
    return _chat(client, headers).json()["lead"]["id"]


def _age(lead_id, days):
    with SessionLocal() as db:
        lead = db.get(Lead, lead_id)
        lead.last_interaction_at = datetime.now(timezone.utc) - timedelta(days=days)
        db.commit()


def test_recent_lead_is_not_nudged_old_lead_is(client, two_orgs):
    a, _ = two_orgs
    client.post("/workflows", headers=a, json=NUDGE)
    lead_id = _lead(client, a)

    assert client.post("/workflows/check-inactive", headers=a).json() == {"runs": 0}  # contacted just now
    _age(lead_id, 4)
    assert client.post("/workflows/check-inactive", headers=a).json() == {"runs": 1}
    d = client.get(f"/leads/{lead_id}", headers=a).json()
    assert d["tasks"][0]["title"] == "Follow up Rahul Sharma: quiet 4 days"

    # runs only once per lead
    assert client.post("/workflows/check-inactive", headers=a).json() == {"runs": 0}
    assert len(client.get("/workflows/runs", headers=a).json()) == 1


def test_closed_leads_are_never_nudged(client, two_orgs):
    a, _ = two_orgs
    client.post("/workflows", headers=a, json=NUDGE)
    lead_id = _lead(client, a)
    _age(lead_id, 10)
    client.patch(f"/leads/{lead_id}", headers=a, json={"status": "LOST"})
    assert client.post("/workflows/check-inactive", headers=a).json() == {"runs": 0}


def test_inactive_check_is_tenant_isolated(client, two_orgs):
    a, b = two_orgs
    client.post("/workflows", headers=a, json=NUDGE)
    lead_b = _lead(client, b)  # B has a lead but no workflow
    _age(lead_b, 10)
    assert client.post("/workflows/check-inactive", headers=b).json() == {"runs": 0}
    assert client.post("/workflows/check-inactive", headers=a).json() == {"runs": 0}  # A's workflow never touches B's lead
    assert client.get(f"/leads/{lead_b}", headers=b).json()["tasks"] == []


def test_scheduler_tick_runs_for_all_orgs(client, two_orgs):
    a, b = two_orgs
    client.post("/workflows", headers=a, json=NUDGE)
    client.post("/workflows", headers=b, json=NUDGE)
    la, lb = _lead(client, a), _lead(client, b)
    _age(la, 5)
    _age(lb, 5)
    assert scheduler.tick() == 2
    assert scheduler.state["last_tick_at"] is not None
    assert len(client.get(f"/leads/{la}", headers=a).json()["tasks"]) == 1
    assert len(client.get(f"/leads/{lb}", headers=b).json()["tasks"]) == 1


def test_scheduler_status(client, two_orgs):
    a, _ = two_orgs
    s = client.get("/workflows/scheduler/status", headers=a).json()
    assert s["enabled"] is False and "interval_seconds" in s  # off in tests


def test_delete_lead_removes_everything_and_respects_tenants(client, two_orgs):
    a, b = two_orgs
    lead_id = _lead(client, a)
    client.post(f"/leads/{lead_id}/notes", headers=a, json={"body": "n"})
    client.post(f"/leads/{lead_id}/tasks", headers=a, json={"title": "t"})
    assert client.delete(f"/leads/{lead_id}", headers=b).status_code == 404
    assert client.get(f"/leads/{lead_id}", headers=a).status_code == 200  # untouched

    assert client.delete(f"/leads/{lead_id}", headers=a).status_code == 204
    assert client.get(f"/leads/{lead_id}", headers=a).status_code == 404
    assert client.get("/leads", headers=a).json() == []
    assert client.get("/leads/summary", headers=a).json()["total"] == 0
