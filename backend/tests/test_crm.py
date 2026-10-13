from app.llm.factory import set_llm
from tests.test_sales_agent import BUY, LAPTOP_MSG, OK_REPLY, ScriptedLLM, _chat, _seed


def _make_lead(client, headers):
    _seed(client, headers)
    set_llm(ScriptedLLM([BUY], [OK_REPLY]))
    r = _chat(client, headers)
    assert r.status_code == 200, r.text
    return r.json()["lead"]["id"], r.json()["conversation_id"]


def test_detail_has_conversation_history(client, two_orgs):
    a, _ = two_orgs
    lead_id, conv_id = _make_lead(client, a)
    d = client.get(f"/leads/{lead_id}", headers=a).json()
    assert d["lead"]["id"] == lead_id
    assert len(d["conversations"]) == 1 and d["conversations"][0]["id"] == conv_id
    msgs = d["conversations"][0]["messages"]
    assert [m["role"] for m in msgs] == ["customer", "agent"]
    assert msgs[0]["content"] == LAPTOP_MSG


def test_status_change_sticks_after_new_agent_message(client, two_orgs):
    a, _ = two_orgs
    lead_id, conv_id = _make_lead(client, a)
    r = client.patch(f"/leads/{lead_id}", headers=a, json={"status": "CONVERTED"})
    assert r.status_code == 200 and r.json()["status"] == "CONVERTED"

    _chat(client, a, "Thanks!", conv_id)
    assert client.get(f"/leads/{lead_id}", headers=a).json()["lead"]["status"] == "CONVERTED"

    # reopening goes back to the score-based status
    r = client.patch(f"/leads/{lead_id}", headers=a, json={"status": "OPEN"})
    assert r.json()["status"] == "HOT"


def test_edit_contact_fields_and_reject_bad_status(client, two_orgs):
    a, _ = two_orgs
    lead_id, _ = _make_lead(client, a)
    r = client.patch(f"/leads/{lead_id}", headers=a, json={"phone": " 98765 ", "email": ""})
    assert r.status_code == 200
    assert r.json()["phone"] == "98765" and r.json()["email"] is None
    assert client.patch(f"/leads/{lead_id}", headers=a, json={"status": "HOT"}).status_code == 422


def test_notes_add_list_delete(client, two_orgs):
    a, _ = two_orgs
    lead_id, _ = _make_lead(client, a)
    n = client.post(f"/leads/{lead_id}/notes", headers=a, json={"body": "Called, wants a demo"})
    assert n.status_code == 201 and n.json()["author_name"] == "Alice Owner"
    assert len(client.get(f"/leads/{lead_id}", headers=a).json()["notes"]) == 1
    assert client.delete(f"/leads/{lead_id}/notes/{n.json()['id']}", headers=a).status_code == 204
    assert client.get(f"/leads/{lead_id}", headers=a).json()["notes"] == []
    assert client.post(f"/leads/{lead_id}/notes", headers=a, json={"body": ""}).status_code == 422


def test_filter_search_and_summary(client, two_orgs):
    a, _ = two_orgs
    lead_id, _ = _make_lead(client, a)
    assert len(client.get("/leads?status=HOT", headers=a).json()) == 1
    assert client.get("/leads?status=LOST", headers=a).json() == []
    assert client.get("/leads?status=BOGUS", headers=a).status_code == 422
    assert len(client.get("/leads?q=rahul", headers=a).json()) == 1
    assert client.get("/leads?q=zzzz", headers=a).json() == []

    s = client.get("/leads/summary", headers=a).json()
    assert s["total"] == 1 and s["counts"]["HOT"] == 1 and s["open_value"] == 900000 and s["won_value"] == 0

    client.patch(f"/leads/{lead_id}", headers=a, json={"status": "CONVERTED"})
    s = client.get("/leads/summary", headers=a).json()
    assert s["open_value"] == 0 and s["won_value"] == 900000 and s["conversion_rate"] == 1.0


def test_leads_are_tenant_isolated(client, two_orgs):
    a, b = two_orgs
    lead_id, _ = _make_lead(client, a)
    assert client.get(f"/leads/{lead_id}", headers=b).status_code == 404
    assert client.patch(f"/leads/{lead_id}", headers=b, json={"status": "LOST"}).status_code == 404
    assert client.post(f"/leads/{lead_id}/notes", headers=b, json={"body": "x"}).status_code == 404
    assert client.get("/leads", headers=b).json() == []
    assert client.get("/leads/summary", headers=b).json()["total"] == 0

    n = client.post(f"/leads/{lead_id}/notes", headers=a, json={"body": "mine"}).json()
    assert client.delete(f"/leads/{lead_id}/notes/{n['id']}", headers=b).status_code == 404
