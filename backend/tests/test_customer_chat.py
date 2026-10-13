import json

import pytest

from app.core.db import SessionLocal
from app.integrations import providers
from app.llm.base import LLMUnavailable
from app.llm.factory import set_llm
from app.models import Conversation, Lead
from tests.test_founder import _org_id
from tests.test_sales_agent import BUY, OK_REPLY, ScriptedLLM, _seed
from tests.test_support import ANSWER, FAQ_Q, SupportLLM

HOOK = "https://hooks.slack.com/services/T000/B000/XXXX"
VISITOR = {"mode": "sales", "name": "Priya", "email": "priya@example.com"}


class Down:
    def generate(self, *a, **k):
        raise LLMUnavailable("model down: secret-detail")


class Boom:
    def generate(self, *a, **k):
        raise AssertionError("the AI must not be called")


def _enable(client, h, slug="acme-shop", **extra):
    r = client.put("/chat/settings", headers=h, json={"slug": slug, "enabled": True, "welcome_message": "Welcome to Acme!", **extra})
    assert r.status_code == 200, r.text
    return slug


def _start(client, slug, **kw):
    r = client.post(f"/public/chat/{slug}/start", json={**VISITOR, **kw})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _say(client, slug, token, text="hello"):
    return client.post(f"/public/chat/{slug}/message", headers={"X-Visitor-Token": token}, json={"message": text})


def test_chat_is_off_until_the_owner_turns_it_on(client, two_orgs):
    a, _ = two_orgs
    s = client.get("/chat/settings", headers=a).json()
    assert s["enabled"] is False and s["slug"]
    assert client.get(f"/public/chat/{s['slug']}").status_code == 404
    _enable(client, a, s["slug"])
    info = client.get(f"/public/chat/{s['slug']}").json()
    assert info["name"] == "Org A" and info["welcome_message"] == "Welcome to Acme!"
    assert client.get("/public/chat/does-not-exist").status_code == 404


def test_settings_validation_permissions_and_unique_slug(client, two_orgs):
    a, b = two_orgs
    _enable(client, a, "taken-name")
    r = client.put("/chat/settings", headers=b, json={"slug": "taken-name", "enabled": True, "welcome_message": "x"})
    assert r.status_code == 409
    for bad in ["ab", "-bad-", "Has Space", "x" * 41]:
        assert client.put("/chat/settings", headers=b, json={"slug": bad, "enabled": False, "welcome_message": "x"}).status_code == 422
    assert client.put("/chat/settings", headers=b, json={"slug": "okay", "enabled": True, "welcome_message": "x", "sales_enabled": False, "support_enabled": False}).status_code == 422


def test_sales_chat_creates_a_lead_with_form_contact_and_leaks_nothing_internal(client, two_orgs):
    a, _ = two_orgs
    _seed(client, a)
    slug = _enable(client, a)
    set_llm(ScriptedLLM([{**BUY, "customer_name": None}], [OK_REPLY]))
    token = _start(client, slug)
    r = _say(client, slug, token, "I need 15 laptops, budget 60000 each")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"products", "messages", "last_seq", "handoff", "human_active", "ticket"}  # nothing internal
    assert body["products"] and body["products"][0]["name"].startswith("DevBook")  # the product the AI named shows as a card
    assert set(body["products"][0]) == {"name", "price", "currency", "blurb", "in_stock"}  # no id, sku or cost
    assert body["messages"][0]["role"] == "agent" and "DevBook" in body["messages"][0]["content"]
    assert set(body["messages"][0]) == {"seq", "role", "content", "attachment_id"}
    lead = client.get("/leads", headers=a).json()[0]
    assert lead["email"] == "priya@example.com" and lead["name"] == "Priya"
    inbox = client.get("/inbox", headers=a).json()
    assert len(inbox) == 1 and inbox[0]["mode"] == "sales" and inbox[0]["lead_id"] == lead["id"]


def test_support_chat_faq_and_escalation_with_ticket_reference(client, two_orgs, monkeypatch):
    a, _ = two_orgs
    _seed(client, a)
    slug = _enable(client, a)
    posts = []
    monkeypatch.setattr(providers, "post_slack", lambda url, text: posts.append(text))
    client.put("/integrations/slack", headers=a, json={"webhook_url": HOOK})
    ana = {"category": "order_status", "order_reference": "ORD-77", "issue_summary": "Where is my order", "urgency": "high"}
    set_llm(SupportLLM([FAQ_Q, ana], [ANSWER, {"reply": "A teammate will check.", "needs_human": True, "escalation_reason": "needs lookup"}]))
    token = _start(client, slug, mode="support")
    r = _say(client, slug, token, "warranty?").json()
    assert r["handoff"] is False and r["ticket"] is None and "warranty" in r["messages"][0]["content"]
    r = _say(client, slug, token, "Where is my order ORD-77?").json()
    assert r["handoff"] is True and r["ticket"] == "T-0001"
    assert any("needs a person" in p for p in posts) and any("New support ticket" in p for p in posts)
    t = client.get("/tickets", headers=a).json()[0]
    assert t["email"] == "priya@example.com"  # contact from the form reached the ticket


def test_tokens_cannot_be_reused_across_orgs_or_as_staff_tokens(client, two_orgs):
    a, b = two_orgs
    slug_a, slug_b = _enable(client, a, "shop-a"), _enable(client, b, "shop-b")
    token = _start(client, slug_a)
    set_llm(Boom())
    assert _say(client, slug_b, token).status_code == 401  # another business
    assert _say(client, slug_a, "garbage").status_code == 401
    assert client.post(f"/public/chat/{slug_a}/message", json={"message": "x"}).status_code == 401
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401  # not a staff token
    staff = a["Authorization"].split()[1]
    assert _say(client, slug_a, staff).status_code == 401  # a staff token is not a visitor token


def test_human_takeover_flow(client, two_orgs):
    a, _ = two_orgs
    _seed(client, a)
    slug = _enable(client, a)
    set_llm(SupportLLM([{"category": "complaint", "issue_summary": "Broken item", "sentiment": "angry"}], [{"reply": "Sorry, a teammate will help.", "needs_human": True}]))
    token = _start(client, slug, mode="support")
    r = _say(client, slug, token, "This is broken and I am furious").json()
    assert r["handoff"] is True and r["human_active"] is False
    conv_id = client.get("/inbox", headers=a).json()[0]["id"]
    assert client.get("/inbox/count", headers=a).json() == {"waiting": 1}  # escalated, nobody has answered yet

    d = client.post(f"/inbox/{conv_id}/reply", headers=a, json={"body": "Hi Priya, I'm on it."}).json()
    assert d["item"]["state"] == "human" and d["messages"][-1]["role"] == "human"
    assert client.get("/tickets", headers=a).json()[0]["status"] == "in_progress"
    assert client.get("/inbox/count", headers=a).json() == {"waiting": 0}

    # the customer's page picks the reply up by polling
    after = r["last_seq"]
    polled = client.get(f"/public/chat/{slug}/messages?after={after}", headers={"X-Visitor-Token": token}).json()
    assert [m["content"] for m in polled] == ["Hi Priya, I'm on it."] and all(m["role"] == "human" for m in polled)

    # the customer writes back: the AI must stay quiet and the inbox shows someone is waiting
    set_llm(Boom())
    back = _say(client, slug, token, "Thanks, my order number is 55").json()
    assert back["messages"] == [] and back["human_active"] is True
    assert client.get("/inbox/count", headers=a).json() == {"waiting": 1}
    assert client.get("/inbox?show=waiting", headers=a).json()[0]["last_message_role"] == "customer"

    # hand back to the AI and it answers again
    d = client.post(f"/inbox/{conv_id}/handback", headers=a).json()
    assert d["item"]["state"] == "ai"
    set_llm(SupportLLM([FAQ_Q], [ANSWER]))
    assert _say(client, slug, token, "one more question").json()["messages"][0]["role"] == "agent"


def test_inbox_is_tenant_scoped_and_test_chats_are_not_replyable(client, two_orgs):
    a, b = two_orgs
    _seed(client, a)
    slug = _enable(client, a)
    set_llm(SupportLLM([FAQ_Q], [ANSWER]))
    token = _start(client, slug, mode="support")
    _say(client, slug, token, "warranty?")
    conv_id = client.get("/inbox", headers=a).json()[0]["id"]
    assert client.get("/inbox", headers=b).json() == []
    assert client.get(f"/inbox/{conv_id}", headers=b).status_code == 404
    assert client.post(f"/inbox/{conv_id}/reply", headers=b, json={"body": "x"}).status_code == 404
    # a dashboard test conversation can be read but not replied to, and is not in the inbox list
    set_llm(ScriptedLLM([BUY], [OK_REPLY]))
    test_conv = client.post("/agents/sales/chat", headers=a, json={"message": "hi 15 laptops"}).json()["conversation_id"]
    assert all(i["id"] != test_conv for i in client.get("/inbox", headers=a).json())
    d = client.get(f"/inbox/{test_conv}", headers=a).json()
    assert d["can_reply"] is False
    assert client.post(f"/inbox/{test_conv}/reply", headers=a, json={"body": "x"}).status_code == 409


def test_failures_and_limits_do_not_leak_details(client, two_orgs, monkeypatch):
    a, _ = two_orgs
    slug = _enable(client, a)
    token = _start(client, slug)
    set_llm(Down())
    r = _say(client, slug, token)
    assert r.status_code == 503 and "secret-detail" not in r.text and "try again" in r.text
    import app.api.public as pub

    monkeypatch.setattr(pub, "MAX_CUSTOMER_MESSAGES", 1)
    set_llm(ScriptedLLM([BUY], [OK_REPLY]))
    # the failed attempt above already counts as one saved customer message
    assert _say(client, slug, token).status_code == 429


def test_per_conversation_rate_limit(client, two_orgs):
    a, _ = two_orgs
    _seed(client, a)
    slug = _enable(client, a)
    set_llm(SupportLLM([FAQ_Q], [ANSWER]))
    token = _start(client, slug, mode="support")
    codes = [_say(client, slug, token).status_code for _ in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429


def test_start_requires_a_valid_email_and_enabled_mode(client, two_orgs):
    a, _ = two_orgs
    slug = _enable(client, a, support_enabled=False)
    assert client.post(f"/public/chat/{slug}/start", json={**VISITOR, "email": "nope"}).status_code == 422
    assert client.post(f"/public/chat/{slug}/start", json={**VISITOR, "mode": "support"}).status_code == 404
    assert client.post(f"/public/chat/{slug}/start", json={**VISITOR, "mode": "admin"}).status_code == 422
