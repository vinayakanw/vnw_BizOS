from app.llm.factory import set_llm
from tests.test_sales_agent import BUY, OK_REPLY, ScriptedLLM, _chat, _seed


def _reply(*actions):
    return {**OK_REPLY, "actions": list(actions)}


def _run(client, headers, actions, msg="Please send me a quote for 15 DevBook 14"):
    _seed(client, headers)
    set_llm(ScriptedLLM([BUY], [_reply(*actions)]))
    r = _chat(client, headers, msg)
    assert r.status_code == 200, r.text
    return r.json()


QUOTE = {"tool": "create_quote", "product_name": "DevBook 14", "quantity": 15}


def test_quote_runs_automatically_with_prices_from_db(client, two_orgs):
    a, _ = two_orgs
    body = _run(client, a, [QUOTE])
    act = body["actions"][0]
    assert act["status"] == "executed" and "Q-0001" in act["summary"]
    d = client.get(f"/leads/{body['lead']['id']}", headers=a).json()
    q = d["quotes"][0]
    assert q["subtotal"] == 54999 * 15 and q["total"] == 54999 * 15 and q["discount_pct"] == 0
    assert d["tool_calls"][0]["status"] == "executed"


def test_small_discount_within_policy_runs_large_one_waits(client, two_orgs):
    a, _ = two_orgs
    body = _run(client, a, [{**QUOTE, "discount_pct": 5}])
    assert body["actions"][0]["status"] == "executed"
    d = client.get(f"/leads/{body['lead']['id']}", headers=a).json()
    assert d["quotes"][0]["total"] == round(54999 * 15 * 0.95, 2)

    set_llm(ScriptedLLM([BUY], [_reply({**QUOTE, "discount_pct": 20})]))
    body2 = _chat(client, a, "20% off please", body["conversation_id"]).json()
    assert body2["actions"][0]["status"] == "pending_approval"
    assert body2["escalated"] is True
    d = client.get(f"/leads/{body['lead']['id']}", headers=a).json()
    assert len(d["quotes"]) == 1  # nothing created until a human approves


def test_approve_creates_quote_reject_does_not(client, two_orgs):
    a, _ = two_orgs
    body = _run(client, a, [{**QUOTE, "discount_pct": 20}])
    pending = client.get("/approvals", headers=a).json()
    assert len(pending) == 1 and pending[0]["lead_name"]
    assert "outside the auto-approval rule" in pending[0]["approval_reason"]

    r = client.post(f"/approvals/{pending[0]['id']}/approve", headers=a)
    assert r.status_code == 200 and r.json()["status"] == "executed" and r.json()["decided_by"] == "Alice Owner"
    d = client.get(f"/leads/{body['lead']['id']}", headers=a).json()
    assert d["quotes"][0]["discount_pct"] == 20
    assert client.get("/approvals", headers=a).json() == []
    # cannot decide twice
    assert client.post(f"/approvals/{pending[0]['id']}/reject", headers=a).status_code == 409

    set_llm(ScriptedLLM([BUY], [_reply({**QUOTE, "discount_pct": 30})]))
    _chat(client, a, "30%?", body["conversation_id"])
    p2 = client.get("/approvals", headers=a).json()[0]
    assert client.post(f"/approvals/{p2['id']}/reject", headers=a).json()["status"] == "rejected"
    assert len(client.get(f"/leads/{body['lead']['id']}", headers=a).json()["quotes"]) == 1


def test_bad_actions_fail_safely(client, two_orgs):
    a, _ = two_orgs
    body = _run(
        client,
        a,
        [
            {"tool": "create_quote", "product_name": "Nonexistent 9000", "quantity": 2},
            {"tool": "create_quote", "product_name": "DevBook 14", "quantity": 9999},  # more than stock
            {"tool": "create_quote", "product_name": "DevBook 14"},  # no quantity
        ],
    )
    assert [x["status"] for x in body["actions"]] == ["failed", "failed", "failed"]
    assert "No active product" in body["actions"][0]["error"]
    assert "in stock" in body["actions"][1]["error"]
    assert "Invalid arguments" in body["actions"][2]["error"]
    assert client.get(f"/leads/{body['lead']['id']}", headers=a).json()["quotes"] == []


def test_task_and_email_draft(client, two_orgs):
    a, _ = two_orgs
    body = _run(
        client,
        a,
        [
            {"tool": "create_followup_task", "title": "Call customer about bulk order", "due_in_days": 1},
            {"tool": "draft_email", "subject": "Your quote", "body": "Hi, here is the quote."},
        ],
    )
    assert [x["status"] for x in body["actions"]] == ["executed", "executed"]
    d = client.get(f"/leads/{body['lead']['id']}", headers=a).json()
    assert d["tasks"][0]["title"] == "Call customer about bulk order"
    email = next(c for c in d["tool_calls"] if c["tool"] == "draft_email")
    assert email["result"]["sent"] is False

    t = client.patch(f"/leads/{body['lead']['id']}/tasks/{d['tasks'][0]['id']}", headers=a, json={"status": "done"})
    assert t.json()["status"] == "done"
    m = client.post(f"/leads/{body['lead']['id']}/tasks", headers=a, json={"title": "Manual task"})
    assert m.status_code == 201 and m.json()["created_by"] == "Alice Owner"


def test_trace_records_actions(client, two_orgs):
    a, _ = two_orgs
    _run(client, a, [QUOTE])
    steps = client.get("/agents/runs", headers=a).json()[0]["steps"]
    assert any(s["step"] == "Ran action" for s in steps)


def test_tools_are_tenant_isolated(client, two_orgs):
    a, b = two_orgs
    body = _run(client, a, [{**QUOTE, "discount_pct": 20}])
    call_id = client.get("/approvals", headers=a).json()[0]["id"]
    assert client.get("/approvals", headers=b).json() == []
    assert client.get("/tool-calls", headers=b).json() == []
    assert client.post(f"/approvals/{call_id}/approve", headers=b).status_code == 404
    assert client.post(f"/approvals/{call_id}/reject", headers=b).status_code == 404
    assert client.get(f"/leads/{body['lead']['id']}", headers=b).status_code == 404
    # still pending for the real owner
    assert len(client.get("/approvals", headers=a).json()) == 1


def test_product_from_other_org_cannot_be_quoted(client, two_orgs):
    a, b = two_orgs
    _seed(client, a)  # only org A has products
    set_llm(ScriptedLLM([BUY], [_reply(QUOTE)]))
    body = _chat(client, b).json()
    assert body["actions"][0]["status"] == "failed"
    assert "No active product" in body["actions"][0]["error"]


def test_discount_request_creates_pending_quote_even_if_reply_model_skips_it(client, two_orgs):
    a, _ = two_orgs
    _seed(client, a)
    ask = {**BUY, "requests_discount": True, "requested_discount_pct": 20, "chosen_product_name": "DevBook 14"}
    set_llm(ScriptedLLM([ask], [OK_REPLY]))  # reply model proposes nothing
    body = _chat(client, a, "Quote for 15 DevBook 14 with 20% discount").json()
    assert [x["tool"] for x in body["actions"]] == ["create_quote"]
    assert body["actions"][0]["status"] == "pending_approval"
    pending = client.get("/approvals", headers=a).json()
    assert pending[0]["args"]["discount_pct"] == 20 and pending[0]["args"]["quantity"] == 15
    assert client.post(f"/approvals/{pending[0]['id']}/approve", headers=a).json()["status"] == "executed"
    quotes = client.get(f"/leads/{body['lead']['id']}", headers=a).json()["quotes"]
    assert quotes[0]["total"] == round(54999 * 15 * 0.8, 2)
