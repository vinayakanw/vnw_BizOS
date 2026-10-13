"""Reply emails, transcripts, quote page, order lookup, language rules, photos."""

import json
from datetime import timedelta

import pytest

from app import customer_comms as comms
from app.agents.sales import prompts as sales_prompts
from app.agents.support import prompts as support_prompts
from app.core.db import SessionLocal
from app.llm.factory import set_llm
from app.models import Conversation, LeadNote, LeadTask, Quote
from tests.conftest import register
from tests.test_customer_chat import _enable, _say, _start
from tests.test_integrations import EMAIL, HOOK, outbox  # noqa: F401  (outbox is a fixture)
from tests.test_sales_agent import BUY, OK_REPLY, ScriptedLLM, _seed
from tests.test_support import ANSWER, FAQ_Q, SupportLLM

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
QUOTE = {"tool": "create_quote", "product_name": "DevBook 14", "quantity": 15}


def _poll(client, slug, token):
    return client.get(f"/public/chat/{slug}/messages?after=0", headers={"X-Visitor-Token": token})


def _conv_id(client, h):
    return client.get("/inbox?show=all", headers=h).json()[0]["id"]


def _leave(cid, minutes=10):
    """The customer closed the page."""
    with SessionLocal() as db:
        c = db.get(Conversation, cid)
        c.customer_last_seen_at = comms.now() - timedelta(minutes=minutes)
        db.commit()


def _reply(client, h, cid, text="We can do it by Friday."):
    r = client.post(f"/inbox/{cid}/reply", headers=h, json={"body": text})
    assert r.status_code == 200, r.text
    return r.json()


def _setup(client, h, email=True, mode="sales"):
    _seed(client, h)
    slug = _enable(client, h)
    if email:
        assert client.put("/integrations/email", headers=h, json=EMAIL).status_code == 200
    return slug, _start(client, slug, mode=mode)


# ------------------------------------------------------------------ 1. reply email

def test_staff_reply_is_emailed_only_when_the_customer_left(client, two_orgs, outbox):
    a, _ = two_orgs
    sent, _posts = outbox
    slug, token = _setup(client, a)
    set_llm(ScriptedLLM([BUY], [OK_REPLY]))
    _say(client, slug, token, "I need 15 laptops")
    cid = _conv_id(client, a)

    # page is open (just polled): no email
    _poll(client, slug, token)
    assert _reply(client, a, cid)["email_status"] == "skipped_online"
    assert sent == []

    # page closed for a while: email goes out with a resume link, to the address from the form
    _leave(cid)
    assert _reply(client, a, cid, "Any update?")["email_status"] == "sent"
    cfg, to, subject, body = sent[0]
    assert to == "priya@example.com" and "Org A" in subject and "Any update?" in body

    # a second reply right away does not spam
    assert _reply(client, a, cid, "And one more thing")["email_status"] == "skipped_recent"
    assert len(sent) == 1

    # the link in the email reopens the same chat
    link = next(w for w in body.split() if "/chat/acme-shop?t=" in w)
    resumed = client.get("/public/chat/acme-shop/messages?after=0", headers={"X-Visitor-Token": link.split("?t=")[1]})
    assert resumed.status_code == 200 and resumed.json()[-1]["role"] == "human"
    assert client.get("/public/chat/acme-shop/me", headers={"X-Visitor-Token": token}).json() == {"mode": "sales", "name": "Priya"}


def test_reply_without_email_setup_or_when_mail_fails(client, two_orgs, outbox, monkeypatch):
    a, _ = two_orgs
    slug, token = _setup(client, a, email=False)
    set_llm(ScriptedLLM([BUY], [OK_REPLY]))
    _say(client, slug, token, "hi")
    cid = _conv_id(client, a)
    _leave(cid)
    assert _reply(client, a, cid)["email_status"] == "no_email_setup"
    assert client.get(f"/public/chat/{slug}").json()["email_enabled"] is False

    client.put("/integrations/email", headers=a, json=EMAIL)
    from app.integrations import providers

    monkeypatch.setattr(providers, "send_email", lambda *x: (_ for _ in ()).throw(providers.IntegrationError("down")))
    _leave(cid)
    assert _reply(client, a, cid, "second")["email_status"] == "failed"  # the reply itself is still saved
    assert len(client.get(f"/inbox/{cid}", headers=a).json()["messages"]) >= 3


# ------------------------------------------------------------------ 6. transcript

def test_transcript_goes_to_the_form_email_and_is_limited(client, two_orgs, outbox):
    a, _ = two_orgs
    sent, _p = outbox
    slug, token = _setup(client, a)
    assert client.get(f"/public/chat/{slug}").json()["email_enabled"] is True
    set_llm(ScriptedLLM([BUY], [OK_REPLY]))
    _say(client, slug, token, "I need 15 laptops")
    r = client.post(f"/public/chat/{slug}/transcript", headers={"X-Visitor-Token": token})
    assert r.status_code == 200 and r.json() == {"sent": True, "to": "p***@example.com"}
    _, to, _, body = sent[0]
    assert to == "priya@example.com" and "You: I need 15 laptops" in body and "DevBook" in body
    for _i in range(2):
        client.post(f"/public/chat/{slug}/transcript", headers={"X-Visitor-Token": token})
    assert client.post(f"/public/chat/{slug}/transcript", headers={"X-Visitor-Token": token}).status_code == 429
    assert client.post(f"/public/chat/{slug}/transcript").status_code == 401


def test_transcript_needs_email_setup(client, two_orgs):
    a, _ = two_orgs
    slug, token = _setup(client, a, email=False)
    assert client.post(f"/public/chat/{slug}/transcript", headers={"X-Visitor-Token": token}).status_code == 409


# ------------------------------------------------------------------ 2. quote link

def _quote_chat(client, a):
    slug, token = _setup(client, a)
    set_llm(ScriptedLLM([BUY], [{**OK_REPLY, "actions": [QUOTE]}]))
    r = _say(client, slug, token, "I need 15 laptops, send a quote")
    assert r.status_code == 200, r.text
    msgs = r.json()["messages"]
    link = next(m["content"] for m in msgs if "quote" in m["content"].lower() and "/quote/" in m["content"])
    return slug, token, link.split("/quote/")[1].split()[0]


def test_quote_link_reaches_the_customer_and_the_customer_can_accept(client, two_orgs, outbox):
    a, b = two_orgs
    slug, token, qt = _quote_chat(client, a)

    v = client.get(f"/public/quote/{qt}").json()
    assert v["business"] == "Org A" and v["number"] == "Q-0001" and v["status"] == "sent" and v["total"] == 15 * 54999
    assert "lead_id" not in v and "org_id" not in v

    r = client.post(f"/public/quote/{qt}/respond", json={"action": "accept", "note": "Please deliver to Pune"})
    assert r.status_code == 200 and r.json()["status"] == "accepted"
    assert client.post(f"/public/quote/{qt}/respond", json={"action": "decline"}).status_code == 409  # one answer only

    with SessionLocal() as db:
        assert db.query(LeadNote).filter(LeadNote.author_name == "Customer").count() == 1
        t = db.query(LeadTask).filter(LeadTask.created_by == "Quote page").one()
        assert "accepted" in t.title and "confirm the order" in t.title
    lead_id = client.get("/leads", headers=a).json()[0]["id"]
    q = client.get(f"/leads/{lead_id}", headers=a).json()["quotes"][0]
    assert q["customer_response"] == "accepted" and q["customer_note"] == "Please deliver to Pune" and q["public_token"] == qt
    assert client.get("/leads", headers=a).json()[0]["status"] != "CONVERTED"  # a person decides that


def test_quote_page_edge_cases(client, two_orgs):
    a, b = two_orgs
    slug, token, qt = _quote_chat(client, a)
    assert client.get("/public/quote/not-a-real-token").status_code == 404
    assert client.post(f"/public/quote/{qt}/respond", json={"action": "changes"}).status_code == 422  # needs a note
    assert client.post(f"/public/quote/{qt}/respond", json={"action": "nope"}).status_code == 422
    with SessionLocal() as db:
        q = db.query(Quote).one()
        q.expires_at = comms.now() - timedelta(days=1)
        db.commit()
    assert client.get(f"/public/quote/{qt}").json()["status"] == "expired"
    assert client.post(f"/public/quote/{qt}/respond", json={"action": "accept"}).status_code == 410
    with SessionLocal() as db:  # a draft that was never sent is not reachable
        q = db.query(Quote).one()
        q.status = "draft"
        db.commit()
    assert client.get(f"/public/quote/{qt}").status_code == 404


def test_changes_request_creates_a_revision_task(client, two_orgs):
    a, _ = two_orgs
    _, _, qt = _quote_chat(client, a)
    assert client.post(f"/public/quote/{qt}/respond", json={"action": "changes", "note": "Need 20 units"}).status_code == 200
    with SessionLocal() as db:
        assert "revised quote" in db.query(LeadTask).filter(LeadTask.created_by == "Quote page").one().title


def test_approved_quote_is_delivered_to_the_customer(client, two_orgs, outbox):
    a, _ = two_orgs
    sent, _p = outbox
    slug, token = _setup(client, a)
    big = {**QUOTE, "discount_pct": 25}  # above the auto-discount limit: needs approval
    set_llm(ScriptedLLM([BUY], [{**OK_REPLY, "actions": [big]}]))
    r = _say(client, slug, token, "I need 15 laptops with 25% off")
    assert all("/quote/" not in m["content"] for m in r.json()["messages"])  # nothing goes out before a human approves
    pending = client.get("/approvals", headers=a).json()
    assert len(pending) == 1
    _leave(_conv_id(client, a))
    assert client.post(f"/approvals/{pending[0]['id']}/approve", headers=a).status_code == 200
    chat = _poll(client, slug, token).json()
    assert any("/quote/" in m["content"] for m in chat)
    assert sent and "quote" in sent[-1][2].lower() and sent[-1][1] == "priya@example.com"  # customer was offline, so also emailed


def test_staff_can_resend_a_quote_and_not_other_tenants(client, two_orgs, outbox):
    a, b = two_orgs
    _, _, qt = _quote_chat(client, a)
    lead_id = client.get("/leads", headers=a).json()[0]["id"]
    qid = client.get(f"/leads/{lead_id}", headers=a).json()["quotes"][0]["id"]
    assert client.post(f"/quotes/{qid}/deliver", headers=b).status_code == 404
    r = client.post(f"/quotes/{qid}/deliver", headers=a)
    assert r.status_code == 200 and r.json()["chat"] is True and qt in r.json()["url"]


# ------------------------------------------------------------------ 3. orders

def _order(**kw):
    return {"order_ref": "ORD-1042", "customer_email": "priya@example.com", "customer_name": "Priya", "status": "shipped", "carrier": "BlueDart",
            "tracking_id": "BD998877", "tracking_url": "https://track.example.com/BD998877", "expected_delivery": "2026-10-12",
            "items": [{"name": "DevBook 14", "quantity": 2}], "total": 109998, **kw}


ORDER_Q = {"category": "order_status", "order_reference": "ORD-1042", "issue_summary": "Where is my order"}


def test_order_crud_import_and_isolation(client, two_orgs):
    a, b = two_orgs
    r = client.post("/orders", headers=a, json=_order(order_ref=" ord-1042 "))
    assert r.status_code == 201 and r.json()["order_ref"] == "ORD-1042"
    assert client.post("/orders", headers=a, json=_order()).status_code == 409
    assert client.post("/orders", headers=a, json=_order(order_ref="X", status="lost")).status_code == 422
    assert client.post("/orders", headers=a, json=_order(order_ref="Y", tracking_url="javascript:alert(1)")).status_code == 422
    oid = r.json()["id"]
    assert client.get("/orders", headers=b).json() == []
    assert client.put(f"/orders/{oid}", headers=b, json=_order()).status_code == 404
    assert client.delete(f"/orders/{oid}", headers=b).status_code == 404
    assert client.put(f"/orders/{oid}", headers=a, json=_order(status="delivered")).json()["status"] == "delivered"
    assert client.get("/orders?q=priya", headers=a).json()[0]["order_ref"] == "ORD-1042"

    csv_text = "order_ref,customer_email,status,items,total,expected_delivery\nORD-2001,a@b.com,packed,2 x Laptop; Mouse,\"1,200\",2026-11-01\nORD-1042,priya@example.com,shipped,,,\nBAD,notanemail,placed,,,\n"
    res = client.post("/orders/import", headers=a, json={"csv": csv_text}).json()
    assert res["created"] == 1 and res["updated"] == 1 and len(res["errors"]) == 1 and "Row 4" in res["errors"][0]
    got = {o["order_ref"]: o for o in client.get("/orders", headers=a).json()}
    assert got["ORD-2001"]["items"] == [{"name": "Laptop", "quantity": 2}, {"name": "Mouse", "quantity": 1}] and got["ORD-2001"]["total"] == 1200
    assert client.post("/orders/import", headers=a, json={"csv": "a,b\n1,2"}).status_code == 422
    assert client.delete(f"/orders/{oid}", headers=a).status_code == 204


def test_support_agent_answers_from_the_real_order(client, two_orgs):
    a, b = two_orgs
    slug, token = _setup(client, a, email=False, mode="support")
    client.post("/orders", headers=a, json=_order())
    llm = SupportLLM([ORDER_Q], [{"reply": "Your order is on its way with BlueDart.", "needs_human": False}])
    set_llm(llm)
    r = _say(client, slug, token, "Where is my order ORD-1042?")
    assert r.status_code == 200 and r.json()["handoff"] is False and r.json()["ticket"] is None
    prompt = llm.reply_prompts[0]
    assert "<order>" in prompt and "BlueDart" in prompt and "BD998877" in prompt and "2 x DevBook 14" in prompt and "shipped, on the way" in prompt
    assert "109998" not in prompt  # no price or address goes to the model


def test_order_needs_matching_email_and_wrong_lookups_escalate(client, two_orgs):
    a, b = two_orgs
    slug, token = _setup(client, a, email=False, mode="support")
    client.post("/orders", headers=a, json=_order(customer_email="someone.else@example.com"))
    client.post("/orders", headers=b, json=_order(order_ref="ORD-9", customer_email="priya@example.com"))  # another business
    llm = SupportLLM([ORDER_Q], [{"reply": "I could not find that order.", "needs_human": True, "escalation_reason": "x"}])
    set_llm(llm)
    r = _say(client, slug, token, "Where is my order ORD-1042?")  # exists, but under another email
    assert r.json()["handoff"] is True and r.json()["ticket"]
    assert "not_found" in llm.reply_prompts[0] and "BlueDart" not in llm.reply_prompts[0]
    llm9 = SupportLLM([{**ORDER_Q, "order_reference": "ORD-9"}], [{"reply": "Not found", "needs_human": True}])
    set_llm(llm9)
    _say(client, slug, token, "and ORD-9?")  # exists, but only for the other business
    assert "not_found" in llm9.reply_prompts[0]
    with SessionLocal() as db:
        assert db.query(Conversation).one().lookup_failures == 2


def test_lookup_stops_after_too_many_failures_and_no_reference_just_asks(client, two_orgs):
    a, _ = two_orgs
    slug, token = _setup(client, a, email=False, mode="support")
    client.post("/orders", headers=a, json=_order())
    # no number given: ask for it, no escalation, no ticket
    llm = SupportLLM([{"category": "order_status"}], [{"reply": "What is your order number?", "needs_human": False}])
    set_llm(llm)
    r = _say(client, slug, token, "where is my order")
    assert r.json()["handoff"] is False and "no_reference" in llm.reply_prompts[0]
    # guessing numbers: after 5 misses even the right number is refused
    for i in range(5):
        set_llm(SupportLLM([{**ORDER_Q, "order_reference": f"ORD-{i}"}], [{"reply": "no", "needs_human": True}]))
        _say(client, slug, token, f"try {i}")
    llm = SupportLLM([ORDER_Q], [{"reply": "A teammate will check.", "needs_human": True}])
    set_llm(llm)
    _say(client, slug, token, "ORD-1042 please")
    assert "BlueDart" not in llm.reply_prompts[0]


def test_loose_order_number_matches_only_the_customers_own_orders(client, two_orgs):
    a, _ = two_orgs
    slug, token = _setup(client, a, email=False, mode="support")
    client.post("/orders", headers=a, json=_order())
    llm = SupportLLM([{**ORDER_Q, "order_reference": "#1042"}], [{"reply": "ok", "needs_human": False}])
    set_llm(llm)
    _say(client, slug, token, "order #1042")
    assert "BlueDart" in llm.reply_prompts[0]


# ------------------------------------------------------------------ 4. Hindi / Hinglish

def test_both_agents_are_told_to_answer_in_the_customers_language():
    for system in (sales_prompts.REPLY_SYSTEM, support_prompts.REPLY_SYSTEM):
        assert "Devanagari" in system and "Hinglish" in system and "same language and script" in system


def test_hindi_text_goes_through_to_the_model_and_back(client, two_orgs):
    a, _ = two_orgs
    slug, token = _setup(client, a, email=False)
    reply = {"reply": "जी हाँ, DevBook 14 उपलब्ध है, कीमत Rs 54,999।", "needs_human": False}
    llm = ScriptedLLM([BUY], [reply])
    set_llm(llm)
    r = _say(client, slug, token, "मुझे 15 लैपटॉप चाहिए")
    assert r.json()["messages"][0]["content"] == reply["reply"]
    assert "मुझे 15 लैपटॉप चाहिए" in llm.reply_prompts[0]


# ------------------------------------------------------------------ 5. photos

def _photo(client, slug, token, data=PNG, name="damage.png", ctype="image/png", **form):
    return client.post(f"/public/chat/{slug}/photo", headers={"X-Visitor-Token": token}, files={"file": (name, data, ctype)}, data=form)


def test_photo_goes_to_a_person_and_the_ai_does_not_see_it(client, two_orgs):
    a, b = two_orgs
    slug, token = _setup(client, a, email=False, mode="support")
    set_llm(None)
    r = _photo(client, slug, token, caption="The screen is cracked")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["handoff"] is True and body["ticket"] == "T-0001"
    mine = [m for m in body["messages"] if m["role"] == "customer"][0]
    assert mine["content"] == "The screen is cracked" and mine["attachment_id"]
    assert any("team member" in m["content"] for m in body["messages"] if m["role"] == "agent")

    img = client.get(f"/public/chat/{slug}/photo/{mine['attachment_id']}", headers={"X-Visitor-Token": token})
    assert img.status_code == 200 and img.headers["content-type"] == "image/png" and img.content == PNG
    # staff see it in the inbox, with the same bytes; other businesses do not
    cid = _conv_id(client, a)
    msg = [m for m in client.get(f"/inbox/{cid}", headers=a).json()["messages"] if m["attachment_id"]][0]
    staff = client.get(f"/inbox/attachments/{msg['attachment_id']}", headers=a)
    assert staff.status_code == 200 and staff.content == PNG
    assert client.get(f"/inbox/attachments/{msg['attachment_id']}", headers=b).status_code == 404
    assert client.get(f"/inbox/attachments/{msg['attachment_id']}").status_code == 401
    assert client.get(f"/inbox?show=waiting", headers=a).json()[0]["state"] == "needs_human"
    # a different customer's token cannot read this photo
    other = _start(client, slug, mode="support", email="other@example.com")
    assert client.get(f"/public/chat/{slug}/photo/{mine['attachment_id']}", headers={"X-Visitor-Token": other}).status_code == 404


def test_hindi_acknowledgement_and_sales_photo(client, two_orgs):
    a, _ = two_orgs
    slug, token = _setup(client, a, email=False)
    r = _photo(client, slug, token, lang="hi")
    assert "धन्यवाद" in r.json()["messages"][-1]["content"] and r.json()["ticket"] is None  # sales chats have no ticket


def test_photo_validation(client, two_orgs):
    a, _ = two_orgs
    slug, token = _setup(client, a, email=False)
    assert _photo(client, slug, token, data=b"<?php echo 1;", name="x.png", ctype="image/png").status_code == 415  # not an image, whatever it claims
    assert _photo(client, slug, token, data=b"GIF89a....", name="x.gif", ctype="image/gif").status_code == 415
    assert _photo(client, slug, token, data=PNG + b"\x00" * (4 * 1024 * 1024)).status_code == 413
    assert client.post(f"/public/chat/{slug}/photo", files={"file": ("a.png", PNG, "image/png")}).status_code == 401
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 20
    webp = b"RIFF\x00\x00\x00\x00WEBPVP8 "
    assert _photo(client, slug, token, data=jpeg, name="a.jpg", ctype="image/jpeg").status_code == 200
    assert _photo(client, slug, token, data=webp, name="a.webp", ctype="image/webp").status_code == 200


def test_photo_count_is_capped(client, two_orgs, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    a, _ = two_orgs
    slug, token = _setup(client, a, email=False)
    codes = [_photo(client, slug, token).status_code for _ in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429
