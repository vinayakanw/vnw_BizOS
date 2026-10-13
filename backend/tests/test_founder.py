import json
from datetime import datetime, timedelta, timezone

from app.core.db import SessionLocal
from app.llm.base import LLMUnavailable
from app.llm.factory import set_llm
from app.models import Lead, LeadTask, Organization, ToolCall
from tests.conftest import register


class FounderLLM:
    def __init__(self, out=None, fail=False):
        self.out, self.fail, self.prompts = out, fail, []

    def generate(self, system, prompt, *, json_mode=False):
        assert "TASK: FOUNDER_BRIEFING" in system
        self.prompts.append(prompt)
        if self.fail:
            raise LLMUnavailable("down")
        return json.dumps(self.out)


def _org_id(client, headers):
    return client.get("/auth/me", headers=headers).json()["org"]["id"]


def _populate(client, headers):
    org_id = _org_id(client, headers)
    old = datetime.now(timezone.utc) - timedelta(days=5)
    with SessionLocal() as db:
        hot = Lead(org_id=org_id, name="Rahul", status="HOT", score=90, potential_value=900000, last_interaction_at=old)
        quiet = Lead(org_id=org_id, name="Quiet Co", status="WARM", score=40, potential_value=100000, last_interaction_at=old)
        db.add_all([hot, quiet])
        db.flush()
        db.add(LeadTask(org_id=org_id, lead_id=hot.id, title="Call Rahul", due_at=old))
        db.add(ToolCall(org_id=org_id, lead_id=hot.id, tool="create_quote", args={}, status="pending_approval", summary="x"))
        db.add(ToolCall(org_id=org_id, lead_id=hot.id, tool="draft_email", args={}, status="failed", summary="y", error="boom"))
        db.commit()


def test_attention_items_are_computed_in_code(client, two_orgs):
    a, b = two_orgs
    _populate(client, a)
    body = client.get("/agents/founder/attention", headers=a).json()
    ids = [i["id"] for i in body["items"]]
    assert {"approvals", "hot_leads", "overdue_tasks", "quiet_leads", "failed_actions"} <= set(ids)
    assert body["items"][0]["severity"] == "high"
    assert body["facts"]["open_pipeline_value"] == 1000000 and body["facts"]["actions_waiting_approval"] == 1
    other = client.get("/agents/founder/attention", headers=b).json()
    assert other["items"] == [] and other["facts"]["open_leads"] == 0  # tenant isolation


def test_briefing_keeps_valid_picks_and_drops_invented_ones(client, two_orgs):
    a, _ = two_orgs
    _populate(client, a)
    llm = FounderLLM({
        "headline": "Rahul needs a call.", "summary": "One hot lead is waiting.",
        "priorities": [
            {"item_id": "hot_leads", "why": "Rs 9,00,000 at stake."},
            {"item_id": "made_up", "why": "invented"},
            {"item_id": "hot_leads", "why": "duplicate"},
            {"item_id": "approvals", "why": "A quote is waiting."},
        ],
    })
    set_llm(llm)
    r = client.post("/agents/founder/briefing", headers=a, json={"days": 7})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["ai_written"] is True and [p["item"]["id"] for p in b["priorities"]] == ["hot_leads", "approvals"]
    assert "Rahul" in llm.prompts[0]
    assert client.get("/agents/founder/briefings", headers=a).json()[0]["id"] == b["id"]
    runs = client.get("/agents/runs", headers=a).json()
    assert any(x["agent"] == "founder" and x["status"] == "completed" for x in runs)


def test_briefing_works_without_the_model(client, two_orgs):
    a, _ = two_orgs
    _populate(client, a)
    set_llm(FounderLLM(fail=True))
    b = client.post("/agents/founder/briefing", headers=a, json={"days": 7}).json()
    assert b["ai_written"] is False and b["priorities"] and "need your attention" in b["headline"]


def test_empty_workspace_and_bad_days(client, two_orgs):
    a, _ = two_orgs
    set_llm(FounderLLM({"headline": "All quiet.", "summary": "Nothing needs attention.", "priorities": []}))
    b = client.post("/agents/founder/briefing", headers=a, json={"days": 7}).json()
    assert b["priorities"] == []
    assert client.post("/agents/founder/briefing", headers=a, json={"days": 0}).status_code == 422
    assert client.post("/agents/founder/briefing", headers=a, json={"days": 99}).status_code == 422


def test_briefings_are_tenant_scoped(client, two_orgs):
    a, b = two_orgs
    set_llm(FounderLLM({"headline": "h", "summary": "s", "priorities": []}))
    bid = client.post("/agents/founder/briefing", headers=a, json={}).json()["id"]
    assert client.get(f"/agents/founder/briefings/{bid}", headers=b).status_code == 404
    assert client.get("/agents/founder/briefings", headers=b).json() == []
