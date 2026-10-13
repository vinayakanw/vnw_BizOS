from app.llm.factory import set_llm
from tests.test_sales_agent import BUY, OK_REPLY, ScriptedLLM, _chat, _seed

HOT_TASK = {
    "name": "Call hot leads",
    "trigger": "lead.hot",
    "steps": [{"tool": "create_followup_task", "args": {"title": "Call {lead.name} about {lead.quantity} units", "due_in_days": 0}}],
}


def _chat_hot(client, headers, analysis=BUY, message=None):
    _seed(client, headers)
    set_llm(ScriptedLLM([analysis], [OK_REPLY]))
    r = _chat(client, headers) if message is None else _chat(client, headers, message)
    assert r.status_code == 200, r.text
    return r.json()


def test_workflow_fires_on_hot_lead_and_renders_variables(client, two_orgs):
    a, _ = two_orgs
    assert client.post("/workflows", headers=a, json=HOT_TASK).status_code == 201
    body = _chat_hot(client, a)
    d = client.get(f"/leads/{body['lead']['id']}", headers=a).json()
    assert [t["title"] for t in d["tasks"]] == ["Call Rahul Sharma about 15 units"]
    steps = client.get("/agents/runs", headers=a).json()[0]["steps"]
    assert any(s["step"] == "Workflow 'Call hot leads'" for s in steps)
    runs = client.get("/workflows/runs", headers=a).json()
    assert runs[0]["status"] == "completed" and runs[0]["lead_name"] == "Rahul Sharma"


def test_runs_once_per_lead_and_disabled_does_not_run(client, two_orgs):
    a, _ = two_orgs
    wf = client.post("/workflows", headers=a, json=HOT_TASK).json()
    body = _chat_hot(client, a)
    _chat(client, a, "More details please", body["conversation_id"])
    assert len(client.get("/workflows/runs", headers=a).json()) == 1  # lead already HOT, and runs once anyway

    client.patch(f"/workflows/{wf['id']}", headers=a, json={"enabled": False})
    set_llm(ScriptedLLM([{**BUY, "customer_name": "Priya"}], [OK_REPLY]))
    _chat(client, a)  # new conversation, new lead
    assert len(client.get("/workflows/runs", headers=a).json()) == 1


def test_conditions_gate_the_workflow(client, two_orgs):
    a, _ = two_orgs
    wf = {**HOT_TASK, "conditions": [{"field": "quantity", "op": "gte", "value": 100}]}
    client.post("/workflows", headers=a, json=wf)
    _chat_hot(client, a)  # quantity is 15
    assert client.get("/workflows/runs", headers=a).json() == []


def test_step_condition_skips_email_without_address(client, two_orgs):
    a, _ = two_orgs
    wf = {
        "name": "Mail",
        "trigger": "lead.hot",
        "steps": [{"tool": "draft_email", "args": {"subject": "Hi {lead.name}", "body": "Hello"}, "condition": {"field": "email", "op": "is_set"}}],
    }
    client.post("/workflows", headers=a, json=wf)
    _chat_hot(client, a)  # BUY has no email
    run = client.get("/workflows/runs", headers=a).json()[0]
    assert run["steps"][0]["status"] == "skipped"


def test_escalation_and_created_triggers(client, two_orgs):
    a, _ = two_orgs
    client.post("/workflows/install-defaults", headers=a)
    ask = {**BUY, "requests_discount": True}
    body = _chat_hot(client, a, ask)
    d = client.get(f"/leads/{body['lead']['id']}", headers=a).json()
    titles = " | ".join(t["title"] for t in d["tasks"])
    assert "Prepare bulk pricing for 15 units" in titles  # lead.created + quantity >= 10
    assert "Review escalation for Rahul Sharma" in titles  # conversation.escalated
    assert "Call Rahul Sharma now" in titles  # lead.hot


def test_workflow_failure_is_recorded_and_chat_still_works(client, two_orgs):
    a, _ = two_orgs
    bad = {"name": "Bad quote", "trigger": "lead.hot", "steps": [{"tool": "create_quote", "args": {"product_name": "Nope", "quantity": 1}}]}
    client.post("/workflows", headers=a, json=bad)
    body = _chat_hot(client, a)
    assert body["reply"]
    run = client.get("/workflows/runs", headers=a).json()[0]
    assert run["status"] == "failed" and "No active product" in run["steps"][0]["error"]


def test_workflow_quote_with_discount_still_needs_approval(client, two_orgs):
    a, _ = two_orgs
    wf = {
        "name": "Auto discount",
        "trigger": "lead.hot",
        "steps": [{"tool": "create_quote", "args": {"product_name": "DevBook 14", "quantity": 15, "discount_pct": 30}}],
    }
    client.post("/workflows", headers=a, json=wf)
    _chat_hot(client, a)
    assert client.get("/workflows/runs", headers=a).json()[0]["steps"][0]["status"] == "pending_approval"
    assert len(client.get("/approvals", headers=a).json()) == 1


def test_validation_rejects_bad_definitions(client, two_orgs):
    a, _ = two_orgs
    base = {"name": "x", "trigger": "lead.hot", "steps": [{"tool": "create_followup_task", "args": {"title": "t"}}]}
    assert client.post("/workflows", headers=a, json={**base, "trigger": "payment.received"}).status_code == 422
    assert client.post("/workflows", headers=a, json={**base, "steps": [{"tool": "send_email", "args": {}}]}).status_code == 422
    assert client.post("/workflows", headers=a, json={**base, "steps": [{"tool": "draft_email", "args": {"to": "a@b.com"}}]}).status_code == 422
    assert client.post("/workflows", headers=a, json={**base, "steps": []}).status_code == 422
    assert client.post("/workflows", headers=a, json={**base, "conditions": [{"field": "password", "op": "eq", "value": "x"}]}).status_code == 422


def test_install_defaults_is_idempotent_and_manual_run(client, two_orgs):
    a, _ = two_orgs
    assert len(client.post("/workflows/install-defaults", headers=a).json()) == 4
    assert len(client.post("/workflows/install-defaults", headers=a).json()) == 4

    body = _chat_hot(client, a)
    lead_id = body["lead"]["id"]
    wf = next(w for w in client.get("/workflows", headers=a).json() if w["trigger"] == "lead.hot")
    assert wf["run_count"] == 1
    r = client.post(f"/workflows/{wf['id']}/run", headers=a, json={"lead_id": lead_id})
    assert r.status_code == 200 and r.json()["trigger"] == "manual"
    assert client.delete(f"/workflows/{wf['id']}", headers=a).status_code == 204


def test_workflows_are_tenant_isolated(client, two_orgs):
    a, b = two_orgs
    wf = client.post("/workflows", headers=a, json=HOT_TASK).json()
    body = _chat_hot(client, a)
    assert client.get("/workflows", headers=b).json() == []
    assert client.get("/workflows/runs", headers=b).json() == []
    assert client.patch(f"/workflows/{wf['id']}", headers=b, json={"enabled": False}).status_code == 404
    assert client.delete(f"/workflows/{wf['id']}", headers=b).status_code == 404
    assert client.post(f"/workflows/{wf['id']}/run", headers=b, json={"lead_id": body["lead"]["id"]}).status_code == 404

    # B's own lead going HOT must not trigger A's workflow
    set_llm(ScriptedLLM([BUY], [OK_REPLY]))
    _chat(client, b)
    assert len(client.get("/workflows/runs", headers=a).json()) == 1

    # B cannot run its own workflow on A's lead
    wf_b = client.post("/workflows", headers=b, json=HOT_TASK).json()
    assert client.post(f"/workflows/{wf_b['id']}/run", headers=b, json={"lead_id": body["lead"]["id"]}).status_code == 404
