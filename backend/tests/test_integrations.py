import pytest

from app.core.db import SessionLocal
from app.integrations import providers
from app.models import Integration, Lead, ToolCall
from tests.conftest import register
from tests.test_founder import FounderLLM, _org_id

EMAIL = {"host": "smtp.example.com", "port": 587, "security": "starttls", "username": "me@x.com", "password": "s3cret-pass", "from_email": "me@x.com", "from_name": "Acme"}
HOOK = "https://hooks.slack.com/services/T000/B000/XXXX"


@pytest.fixture()
def outbox(monkeypatch):
    sent, posts = [], []

    def fake_email(cfg, to, subject, body):
        sent.append((cfg, to, subject, body))
        return "<id-1@test>"

    monkeypatch.setattr(providers, "send_email", fake_email)
    monkeypatch.setattr(providers, "post_slack", lambda url, text: posts.append((url, text)))
    return sent, posts


def _draft(client, h, email="cust@x.com"):
    org_id = _org_id(client, h)
    with SessionLocal() as db:
        lead = Lead(org_id=org_id, name="Rahul", email=email, status="HOT", score=90)
        db.add(lead)
        db.flush()
        d = ToolCall(
            org_id=org_id, lead_id=lead.id, tool="draft_email", status="executed", summary="d", args={},
            result={"to": email, "subject": "Your quote", "body": "Hello Rahul", "sent": False},
        )
        db.add(d)
        db.commit()
        return d.id, lead.id


def test_secrets_are_encrypted_and_never_returned(client, two_orgs):
    a, b = two_orgs
    r = client.put("/integrations/email", headers=a, json=EMAIL)
    assert r.status_code == 200 and r.json()["config"]["has_password"] is True
    assert "s3cret-pass" not in r.text and "password" not in r.json()["config"]
    assert "s3cret-pass" not in client.get("/integrations", headers=a).text
    with SessionLocal() as db:
        raw = db.query(Integration).one().config["password"]
    assert raw != "s3cret-pass" and raw.startswith("gAAAA")
    # blank password keeps the stored one
    client.put("/integrations/email", headers=a, json={**EMAIL, "password": ""})
    with SessionLocal() as db:
        assert db.query(Integration).one().config["password"] == raw
    assert client.get("/integrations", headers=b).json()["email"] is None  # tenant isolation


def test_slack_url_must_be_a_slack_webhook(client, two_orgs):
    a, _ = two_orgs
    for bad in ["http://hooks.slack.com/services/a", "https://evil.com/services/a", "https://hooks.slack.com.evil.com/services/a"]:
        assert client.put("/integrations/slack", headers=a, json={"webhook_url": bad}).status_code == 422
    assert client.put("/integrations/slack", headers=a, json={"webhook_url": HOOK}).status_code == 200
    assert "XXXX" not in client.get("/integrations", headers=a).text


def test_test_buttons_and_error_reporting(client, two_orgs, outbox, monkeypatch):
    a, _ = two_orgs
    sent, posts = outbox
    client.put("/integrations/email", headers=a, json=EMAIL)
    client.put("/integrations/slack", headers=a, json={"webhook_url": HOOK})
    assert client.post("/integrations/email/test", headers=a).status_code == 200 and sent[0][1] == "a@a.com"
    assert client.post("/integrations/slack/test", headers=a).status_code == 200 and posts
    monkeypatch.setattr(providers, "send_email", lambda *x: (_ for _ in ()).throw(providers.IntegrationError("bad login")))
    r = client.post("/integrations/email/test", headers=a)
    assert r.status_code == 502 and "bad login" in r.text
    assert client.get("/integrations", headers=a).json()["email"]["last_error"] == "bad login"


def test_send_draft_sends_once_and_is_audited(client, two_orgs, outbox):
    a, _ = two_orgs
    sent, _ = outbox
    client.put("/integrations/email", headers=a, json=EMAIL)
    draft_id, _lead = _draft(client, a)
    r = client.post(f"/tool-calls/{draft_id}/send", headers=a)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tool"] == "send_email" and body["status"] == "executed" and body["decided_by"] == "Alice Owner"
    assert len(sent) == 1 and sent[0][1] == "cust@x.com" and sent[0][2] == "Your quote" and sent[0][0]["password"] == "s3cret-pass"
    assert client.post(f"/tool-calls/{draft_id}/send", headers=a).status_code == 409 and len(sent) == 1


def test_send_fails_cleanly_without_setup_or_address(client, two_orgs, outbox):
    a, _ = two_orgs
    sent, _ = outbox
    draft_id, _ = _draft(client, a)
    r = client.post(f"/tool-calls/{draft_id}/send", headers=a)
    assert r.json()["status"] == "failed" and "not connected" in r.json()["error"] and not sent
    client.put("/integrations/email", headers=a, json=EMAIL)
    draft2, _ = _draft(client, a, email=None)
    r = client.post(f"/tool-calls/{draft2}/send", headers=a)
    assert r.json()["status"] == "failed" and "no email" in r.json()["error"] and not sent


def test_send_requires_a_saved_draft_and_own_org(client, two_orgs, outbox):
    a, b = two_orgs
    client.put("/integrations/email", headers=a, json=EMAIL)
    draft_id, _ = _draft(client, a)
    assert client.post(f"/tool-calls/{draft_id}/send", headers=b).status_code == 404
    with SessionLocal() as db:
        c = db.get(ToolCall, draft_id)
        c.tool = "create_followup_task"
        db.commit()
    assert client.post(f"/tool-calls/{draft_id}/send", headers=a).status_code == 409


def test_member_cannot_send_or_configure(client, two_orgs, outbox):
    a, _ = two_orgs
    from app.models import User

    with SessionLocal() as db:
        u = db.query(User).filter(User.email == "a@a.com").one()
        u.role = "member"
        db.commit()
    assert client.put("/integrations/email", headers=a, json=EMAIL).status_code == 403
    assert client.post("/tool-calls/x/send", headers=a).status_code == 403


def test_agent_cannot_send_email_by_itself(client, two_orgs, outbox):
    """Even if send_email is somehow proposed, policy parks it for a human."""
    from app.tools.registry import run_tool

    a, _ = two_orgs
    sent, _ = outbox
    client.put("/integrations/email", headers=a, json=EMAIL)
    _, lead_id = _draft(client, a)
    with SessionLocal() as db:
        lead = db.get(Lead, lead_id)
        call = run_tool(db, org_id=lead.org_id, lead=lead, tool="send_email", raw_args={"subject": "Hi", "body": "x"})
        assert call.status == "pending_approval" and not sent
        db.rollback()


def test_slack_pings_on_approval_and_ticket_and_briefing_share(client, two_orgs, outbox):
    from app.llm.factory import set_llm
    from app.tools.registry import run_tool

    a, _ = two_orgs
    _, posts = outbox
    client.put("/integrations/slack", headers=a, json={"webhook_url": HOOK})
    _, lead_id = _draft(client, a)
    with SessionLocal() as db:
        lead = db.get(Lead, lead_id)
        run_tool(db, org_id=lead.org_id, lead=lead, tool="send_email", raw_args={"subject": "Hi", "body": "x"})
        db.commit()
    assert any("Approval needed" in t for _, t in posts)
    set_llm(FounderLLM({"headline": "All good", "summary": "Fine.", "priorities": []}))
    bid = client.post("/agents/founder/briefing", headers=a, json={}).json()["id"]
    assert client.post(f"/agents/founder/briefings/{bid}/share", headers=a).status_code == 200
    assert "All good" in posts[-1][1]


def test_slack_failure_never_breaks_the_agent(client, two_orgs, monkeypatch):
    from app.tools.registry import run_tool

    a, _ = two_orgs
    client.put("/integrations/slack", headers=a, json={"webhook_url": HOOK})
    monkeypatch.setattr(providers, "post_slack", lambda *x: (_ for _ in ()).throw(RuntimeError("down")))
    _, lead_id = _draft(client, a)
    with SessionLocal() as db:
        lead = db.get(Lead, lead_id)
        call = run_tool(db, org_id=lead.org_id, lead=lead, tool="send_email", raw_args={"subject": "Hi", "body": "x"})
        assert call.status == "pending_approval"
        db.rollback()
