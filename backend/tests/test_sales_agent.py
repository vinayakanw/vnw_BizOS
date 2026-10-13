import json

from app.agents.sales.scoring import ScoreInput, recommend_next_action, score_lead
from app.llm.base import LLMError, LLMUnavailable
from app.llm.factory import set_llm
from app.llm.structured import generate_structured


class ScriptedLLM:
    """Stands in for Gemini. Analysis/reply outputs are consumed in order; the last one repeats."""

    def __init__(self, analyses, replies):
        self.analyses, self.replies = list(analyses), list(replies)
        self.analyze_prompts: list[str] = []
        self.reply_prompts: list[str] = []

    def generate(self, system, prompt, *, json_mode=False):
        if "TASK: ANALYZE_MESSAGE" in system:
            self.analyze_prompts.append(prompt)
            out = self.analyses.pop(0) if len(self.analyses) > 1 else self.analyses[0]
        elif "TASK: WRITE_REPLY" in system:
            self.reply_prompts.append(prompt)
            out = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        else:
            raise AssertionError("unexpected prompt")
        return json.dumps(out)


LAPTOP_MSG = "Hi, I need 15 laptops for my startup. My budget is around Rs 60,000 per laptop. Do you have something suitable?"

BUY = {
    "category": "purchase_intent",
    "purchase_stage": "ready_to_buy",
    "quantity": 15,
    "budget_per_unit": 60000,
    "currency": "INR",
    "requirement_summary": "15 developer laptops",
    "use_case": "developer team",
    "product_search_terms": ["developer laptop"],
    "customer_name": "Rahul Sharma",
    "company": "Acme Startup",
}
OK_REPLY = {"reply": "Yes! The DevBook 14 is Rs 54,999. Could you share your email?", "needs_human": False}


def _seed(client, headers):
    r = client.post("/demo/seed", headers=headers)
    assert r.status_code == 201, r.text


def _chat(client, headers, message=LAPTOP_MSG, conversation_id=None):
    return client.post(
        "/agents/sales/chat", headers=headers, json={"message": message, "conversation_id": conversation_id}
    )


# ---- scoring (pure) ------------------------------------------------------------------

def test_scoring_matches_spec_example_and_thresholds():
    full = score_lead(
        ScoreInput(quantity=15, budget_per_unit=60000, use_case="devs", purchase_stage="ready_to_buy", product_match=True, company="Acme")
    )
    assert full.status == "HOT" and full.intent == "HIGH" and full.score == 85
    assert "Specific quantity (15 units)" in full.reasons and "Defined budget" in full.reasons
    assert recommend_next_action(full, None) == "Contact within 15 minutes"

    assert score_lead(ScoreInput()).status == "NEW"
    mid = score_lead(ScoreInput(budget_per_unit=1000, use_case="x", purchase_stage="evaluating"))
    assert mid.status == "QUALIFYING" and mid.intent == "MEDIUM"
    assert "quantity" in mid.missing
    assert recommend_next_action(mid, "Discount requested").startswith("Human review needed")
    assert score_lead(
        ScoreInput(quantity=50, budget_per_unit=1, requirement="r", timeline="t", email="e", phone="p", company="c", purchase_stage="ready_to_buy", product_match=True)
    ).score == 100


# ---- structured output -----------------------------------------------------------------

class _Flaky:
    def __init__(self, outputs):
        self.outputs, self.calls = outputs, 0

    def generate(self, system, prompt, *, json_mode=False):
        self.calls += 1
        return self.outputs[min(self.calls - 1, len(self.outputs) - 1)]


def test_structured_retries_once_then_succeeds_and_strips_fences():
    from app.agents.sales.schemas import Reply

    llm = _Flaky(["definitely not json", '```json\n{"reply": "hello"}\n```'])
    assert generate_structured(llm, "TASK", "p", Reply).reply == "hello" and llm.calls == 2


def test_structured_fails_after_retry():
    from app.agents.sales.schemas import Reply

    llm = _Flaky(["nope", "still nope"])
    try:
        generate_structured(llm, "TASK", "p", Reply)
        raise AssertionError("should have raised")
    except LLMError:
        assert llm.calls == 2


# ---- end to end -----------------------------------------------------------------------------

def test_full_flow_creates_scored_lead_with_trace(client, two_orgs):
    a, _ = two_orgs
    _seed(client, a)
    llm = ScriptedLLM([BUY], [OK_REPLY])
    set_llm(llm)

    r = _chat(client, a)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reply"] == OK_REPLY["reply"] and body["escalated"] is False

    lead = body["lead"]
    assert lead["status"] == "HOT" and lead["intent"] == "HIGH" and lead["score"] == 85
    assert lead["quantity"] == 15 and lead["budget_per_unit"] == 60000
    assert lead["potential_value"] == 900000 and lead["name"] == "Rahul Sharma"
    assert lead["next_action"] == "Contact within 15 minutes"

    assert body["products"][0]["name"] == "DevBook 14" and body["products"][0]["within_budget"] is True
    names = [s["step"] for s in body["steps"]]
    assert names[0] == "Received customer message"
    for expected in ("Analyzed message", "Searched products", "Searched knowledge", "Drafted reply", "Scored lead", "Completed"):
        assert expected in names

    # the model was given real catalog data and the business policy
    assert "DevBook 14" in llm.reply_prompts[0] and "54999" in llm.reply_prompts[0]
    assert "Up to 5% on orders of 10" in llm.reply_prompts[0]

    assert len(client.get("/leads", headers=a).json()) == 1
    run = client.get("/agents/runs", headers=a).json()[0]
    assert run["status"] == "completed" and run["id"] == body["run_id"] and run["steps"]


def test_followup_merges_into_same_lead(client, two_orgs):
    a, _ = two_orgs
    _seed(client, a)
    followup = {"category": "purchase_intent", "purchase_stage": "ready_to_buy", "email": "rahul@acme.com", "timeline": "within 2 weeks"}
    llm = ScriptedLLM([BUY, followup], [OK_REPLY])
    set_llm(llm)

    first = _chat(client, a).json()
    second = _chat(client, a, "My email is rahul@acme.com, we need them within 2 weeks", first["conversation_id"]).json()

    assert second["conversation_id"] == first["conversation_id"]
    leads = client.get("/leads", headers=a).json()
    assert len(leads) == 1
    lead = leads[0]
    assert lead["quantity"] == 15 and lead["email"] == "rahul@acme.com" and lead["timeline"] == "within 2 weeks"
    assert lead["score"] == 100  # 85 + timeline 10 + contact 10, capped
    assert "15 laptops" in llm.analyze_prompts[1]  # history was supplied


def test_discount_request_escalates(client, two_orgs):
    a, _ = two_orgs
    _seed(client, a)
    ask = {**BUY, "requests_discount": True}
    set_llm(ScriptedLLM([ask], [{"reply": "I will check with the team on that.", "needs_human": False}]))

    body = _chat(client, a, "Can you give 20% off on 15 laptops?").json()
    assert body["escalated"] is True and "Discount" in body["escalation_reason"]
    assert body["lead"]["next_action"].startswith("Human review needed")
    assert client.get("/agents/runs", headers=a).json()[0]["status"] == "escalated"


def test_model_flagged_escalation(client, two_orgs):
    a, _ = two_orgs
    _seed(client, a)
    set_llm(ScriptedLLM([{**BUY, "quantity": None}], [{"reply": "A teammate will confirm.", "needs_human": True, "escalation_reason": "No installation info"}]))
    body = _chat(client, a, "Do you install on site?").json()
    assert body["escalated"] and "No installation info" in body["escalation_reason"]


def test_small_talk_creates_no_lead(client, two_orgs):
    a, _ = two_orgs
    set_llm(ScriptedLLM([{"category": "general"}], [{"reply": "Hello! How can I help?"}]))
    body = _chat(client, a, "hi").json()
    assert body["lead"] is None
    assert client.get("/leads", headers=a).json() == []
    assert any(s["step"] == "Lead capture skipped" for s in body["steps"])


def test_knowledge_is_used_in_reply_prompt(client, two_orgs):
    a, _ = two_orgs
    _seed(client, a)
    llm = ScriptedLLM([{"category": "product_inquiry", "product_search_terms": ["warranty"]}], [{"reply": "1 year."}])
    set_llm(llm)
    _chat(client, a, "What warranty do your laptops come with?")
    assert "1 year on-site warranty" in llm.reply_prompts[0]


# ---- tenant isolation ---------------------------------------------------------------------------

def test_orgs_cannot_see_each_others_conversations_leads_or_catalog(client, two_orgs):
    a, b = two_orgs
    client.post("/products", headers=a, json={"name": "Zeta Widget", "price": 100, "category": "Widgets"})
    llm = ScriptedLLM([{"category": "product_inquiry", "product_search_terms": ["widget"]}], [{"reply": "ok"}])
    set_llm(llm)

    conv = _chat(client, a, "tell me about widgets").json()["conversation_id"]
    assert "Zeta Widget" in llm.reply_prompts[0]

    # B cannot continue A's conversation
    assert _chat(client, b, "hello", conv).status_code == 404

    # B asks the same thing: A's product must never reach the model
    body = _chat(client, b, "tell me about widgets").json()
    assert "Zeta Widget" not in llm.reply_prompts[1]
    assert any("no products found" in s["detail"] for s in body["steps"] if s["step"] == "Searched products")
    assert body["products"] == []

    leads_a = client.get("/leads", headers=a).json()
    leads_b = client.get("/leads", headers=b).json()
    assert len(leads_a) == 1 and len(leads_b) == 1  # each org sees only its own lead
    assert leads_a[0]["id"] != leads_b[0]["id"]
    assert len(client.get("/agents/runs", headers=b).json()) == 1  # only B's own run


# ---- failure handling ---------------------------------------------------------------------------

class _Down:
    def generate(self, system, prompt, *, json_mode=False):
        raise LLMUnavailable("Gemini is rate limiting right now")


def test_llm_outage_returns_503_and_records_failed_run(client, two_orgs):
    a, _ = two_orgs
    set_llm(_Down())
    r = _chat(client, a)
    assert r.status_code == 503 and "rate limiting" in r.json()["detail"]
    run = client.get("/agents/runs", headers=a).json()[0]
    assert run["status"] == "failed" and run["error"] and run["steps"][-1]["step"] == "Failed"


def test_missing_api_key_gives_clear_503(client, two_orgs):
    a, _ = two_orgs
    r = _chat(client, a)
    assert r.status_code == 503 and "LLM_API_KEY" in r.json()["detail"]


def test_garbage_model_output_returns_502(client, two_orgs):
    a, _ = two_orgs
    set_llm(_Flaky(["nope"]))
    assert _chat(client, a).status_code == 502


def test_message_validation_and_auth(client, two_orgs):
    a, _ = two_orgs
    assert client.post("/agents/sales/chat", headers=a, json={"message": ""}).status_code == 422
    assert client.post("/agents/sales/chat", json={"message": "hi"}).status_code == 401
    for path in ("/leads", "/agents/runs"):
        assert client.get(path).status_code == 401
    assert client.post("/demo/seed").status_code == 401


# ---- demo seed ---------------------------------------------------------------------------------------

def test_demo_seed_loads_once_per_empty_workspace_and_indexes_faqs(client, two_orgs):
    a, b = two_orgs
    r = client.post("/demo/seed", headers=a)
    assert r.status_code == 201 and r.json() == {"products": 9, "faqs": 7}
    assert len(client.get("/products", headers=a).json()) == 9
    assert client.post("/demo/seed", headers=a).status_code == 409
    assert client.get("/products", headers=b).json() == []
    hits = client.post("/knowledge/search", headers=a, json={"query": "warranty period"}).json()
    assert hits and hits[0]["source_type"] == "faq"
    assert client.get("/profile", headers=a).json()["discount_policy"].startswith("Up to 5%")
