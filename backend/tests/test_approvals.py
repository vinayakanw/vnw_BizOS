from app.core.db import SessionLocal
from app.llm.factory import set_llm
from app.models import User
from sqlalchemy import select
from tests.test_sales_agent import BUY, OK_REPLY, ScriptedLLM, _chat, _seed

QUOTE = {"tool": "create_quote", "product_name": "DevBook 14", "quantity": 15}


def _run(client, headers, actions):
    _seed(client, headers)
    set_llm(ScriptedLLM([BUY], [{**OK_REPLY, "actions": actions}]))
    r = _chat(client, headers)
    assert r.status_code == 200, r.text
    return r.json()


def _rules(**over):
    base = {"auto_discount_max_pct": 5, "auto_discount_min_qty": 10, "quote_approval_above": None, "always_approve_tools": []}
    return {**base, **over}


def test_default_rules_and_update(client, two_orgs):
    a, b = two_orgs
    r = client.get("/approvals/rules", headers=a).json()
    assert r["auto_discount_max_pct"] == 5 and r["auto_discount_min_qty"] == 10 and r["always_approve_tools"] == []

    new = _rules(auto_discount_max_pct=10, quote_approval_above=500000, always_approve_tools=["draft_email"])
    assert client.put("/approvals/rules", headers=a, json=new).json() == new
    assert client.get("/approvals/rules", headers=a).json() == new
    assert client.get("/approvals/rules", headers=b).json()["auto_discount_max_pct"] == 5  # B unaffected
    assert client.put("/approvals/rules", headers=a, json=_rules(auto_discount_max_pct=150)).status_code == 422
    assert client.put("/approvals/rules", headers=a, json=_rules(always_approve_tools=["send_email"])).status_code == 422


def test_raised_discount_limit_lets_discount_through(client, two_orgs):
    a, _ = two_orgs
    client.put("/approvals/rules", headers=a, json=_rules(auto_discount_max_pct=10))
    body = _run(client, a, [{**QUOTE, "discount_pct": 8}])
    assert body["actions"][0]["status"] == "executed"  # would have needed approval under the default 5%


def test_value_limit_requires_approval(client, two_orgs):
    a, _ = two_orgs
    client.put("/approvals/rules", headers=a, json=_rules(quote_approval_above=500000))
    body = _run(client, a, [QUOTE])  # 15 x 54,999 = 824,985
    assert body["actions"][0]["status"] == "pending_approval"
    reason = client.get("/approvals", headers=a).json()[0]["approval_reason"]
    assert "above your approval limit" in reason


def test_always_approve_tool(client, two_orgs):
    a, _ = two_orgs
    client.put("/approvals/rules", headers=a, json=_rules(always_approve_tools=["create_followup_task"]))
    body = _run(client, a, [{"tool": "create_followup_task", "title": "Call", "due_in_days": 1}])
    assert body["actions"][0]["status"] == "pending_approval"
    d = client.get(f"/leads/{body['lead']['id']}", headers=a).json()
    assert d["tasks"] == []
    call_id = client.get("/approvals", headers=a).json()[0]["id"]
    assert client.post(f"/approvals/{call_id}/approve", headers=a).json()["status"] == "executed"
    assert len(client.get(f"/leads/{body['lead']['id']}", headers=a).json()["tasks"]) == 1


def test_reject_with_reason_and_count(client, two_orgs):
    a, b = two_orgs
    _run(client, a, [{**QUOTE, "discount_pct": 25}])
    assert client.get("/approvals/count", headers=a).json() == {"pending": 1}
    assert client.get("/approvals/count", headers=b).json() == {"pending": 0}
    call_id = client.get("/approvals", headers=a).json()[0]["id"]
    r = client.post(f"/approvals/{call_id}/reject", headers=a, json={"reason": "Too deep a discount"}).json()
    assert r["status"] == "rejected" and r["result"] == {"rejection_reason": "Too deep a discount"}
    assert "Too deep a discount" in r["summary"]
    assert client.get("/approvals/count", headers=a).json() == {"pending": 0}


def test_only_owners_and_admins_decide(client, two_orgs):
    a, _ = two_orgs
    _run(client, a, [{**QUOTE, "discount_pct": 25}])
    call_id = client.get("/approvals", headers=a).json()[0]["id"]
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == "a@a.com"))
        u.role = "member"
        db.commit()
    assert client.post(f"/approvals/{call_id}/approve", headers=a).status_code == 403
    assert client.post(f"/approvals/{call_id}/reject", headers=a).status_code == 403
    assert client.put("/approvals/rules", headers=a, json=_rules()).status_code == 403
    assert client.get("/approvals", headers=a).status_code == 200  # can still see the queue
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == "a@a.com"))
        u.role = "admin"
        db.commit()
    assert client.post(f"/approvals/{call_id}/approve", headers=a).status_code == 200


def test_rules_apply_to_workflow_steps_too(client, two_orgs):
    a, _ = two_orgs
    client.put("/approvals/rules", headers=a, json=_rules(always_approve_tools=["draft_email"]))
    wf = {"name": "Mail", "trigger": "lead.hot", "steps": [{"tool": "draft_email", "args": {"subject": "Hi", "body": "Hello"}}]}
    client.post("/workflows", headers=a, json=wf)
    _run(client, a, [])
    assert client.get("/workflows/runs", headers=a).json()[0]["steps"][0]["status"] == "pending_approval"
