import json
from datetime import datetime, timedelta, timezone

from app.core.db import SessionLocal
from app.llm.factory import set_llm
from app.models import Lead
from tests.test_sales_agent import BUY, OK_REPLY, ScriptedLLM, _chat, _seed


class AnalyticsLLM:
    """Plays both steps. plan -> dict, answer -> text built from whatever results the prompt carries."""

    def __init__(self, plan, answer="ok"):
        self.plan, self.answer, self.answer_prompt = plan, answer, ""

    def generate(self, system, prompt, *, json_mode=False):
        if "TASK: PLAN_ANALYTICS" in system:
            return json.dumps(self.plan)
        if "TASK: WRITE_ANSWER" in system:
            self.answer_prompt = prompt
            return json.dumps({"answer": self.answer})
        raise AssertionError("unexpected prompt")


def _lead(client, headers, name="Rahul Sharma"):
    _seed(client, headers)
    set_llm(ScriptedLLM([{**BUY, "customer_name": name}], [OK_REPLY]))
    return _chat(client, headers).json()["lead"]["id"]


def _ask(client, headers, q="How is my pipeline?"):
    return client.post("/agents/analytics/ask", headers=headers, json={"question": q})


def test_answer_is_grounded_on_real_numbers(client, two_orgs):
    a, _ = two_orgs
    _lead(client, a)
    llm = AnalyticsLLM({"metrics": [{"metric": "pipeline_summary"}]}, "You have 1 hot lead worth Rs 9,00,000.")
    set_llm(llm)
    r = _ask(client, a)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"].startswith("You have 1 hot lead")
    res = body["results"][0]
    assert res["metric"] == "pipeline_summary"
    assert res["facts"]["total_leads"] == 1 and res["facts"]["open_pipeline_value"] == 900000
    assert ["HOT", 1, 900000.0] in res["rows"]
    assert "900000" in llm.answer_prompt  # the answer step only sees the computed numbers
    assert any(s["step"] == "Ran report" for s in body["steps"])


def test_reports_only_see_the_callers_org(client, two_orgs):
    a, b = two_orgs
    _lead(client, a, "Alice Lead")
    set_llm(AnalyticsLLM({"metrics": [{"metric": "top_leads", "n": 10}, {"metric": "pipeline_summary"}]}))
    body = _ask(client, b).json()  # org B has no leads at all
    assert body["results"][0]["rows"] == []
    assert body["results"][1]["facts"]["total_leads"] == 0
    assert "Alice Lead" not in json.dumps(body)


def test_out_of_scope_question_gets_honest_refusal(client, two_orgs):
    a, _ = two_orgs
    set_llm(AnalyticsLLM({"metrics": [], "out_of_scope": True}))
    body = _ask(client, a, "Forecast my revenue for next year").json()
    assert body["out_of_scope"] is True and body["results"] == []
    assert "can't answer" in body["answer"]


def test_params_are_clamped_and_bad_plans_fail_cleanly(client, two_orgs):
    a, _ = two_orgs
    set_llm(AnalyticsLLM({"metrics": [{"metric": "leads_over_time", "days": 100000}]}))
    rows = _ask(client, a).json()["results"][0]["rows"]
    assert len(rows) == 365  # clamped

    set_llm(AnalyticsLLM({"metrics": [{"metric": "drop_all_tables"}]}))  # not in the catalog
    assert _ask(client, a).status_code == 502
    runs = client.get("/agents/runs", headers=a).json()
    assert any(r["status"] == "failed" and r["agent"] == "analytics" for r in runs)


def test_stale_and_top_leads_metrics(client, two_orgs):
    a, _ = two_orgs
    lead_id = _lead(client, a)
    with SessionLocal() as db:
        lead = db.get(Lead, lead_id)
        lead.last_interaction_at = datetime.now(timezone.utc) - timedelta(days=6)
        db.commit()
    set_llm(AnalyticsLLM({"metrics": [{"metric": "stale_leads", "days": 3}, {"metric": "top_leads", "order_by": "value"}]}))
    res = _ask(client, a).json()["results"]
    assert res[0]["facts"]["quiet_leads"] == 1 and res[0]["rows"][0][2] == 6
    assert res[1]["rows"][0][0] == "Rahul Sharma"


def test_quotes_approvals_tasks_agent_metrics(client, two_orgs):
    a, _ = two_orgs
    _seed(client, a)
    acts = [{"tool": "create_quote", "product_name": "DevBook 14", "quantity": 15, "discount_pct": 5}, {"tool": "create_followup_task", "title": "Call", "due_in_days": 0}]
    set_llm(ScriptedLLM([BUY], [{**OK_REPLY, "actions": acts}]))
    _chat(client, a)
    set_llm(AnalyticsLLM({"metrics": [{"metric": m} for m in ("quotes_summary", "approvals_summary", "tasks_summary")]}))
    q, ap, t = _ask(client, a).json()["results"]
    assert q["facts"]["quotes"] == 1 and q["facts"]["average_discount_pct"] == 5.0
    assert q["rows"][0][:2] == ["DevBook 14", 15]
    assert ap["facts"]["executed"] == 2 and ap["facts"]["pending_approval"] == 0
    assert t["facts"]["open"] == 1
    set_llm(AnalyticsLLM({"metrics": [{"metric": "agent_activity"}]}))
    assert _ask(client, a).json()["results"][0]["facts"]["runs"] == 1


def test_overview_needs_no_llm_and_is_isolated(client, two_orgs):
    a, b = two_orgs
    _lead(client, a)
    ov = client.get("/agents/analytics/overview", headers=a).json()
    assert ov["pipeline"]["facts"]["total_leads"] == 1
    assert len(ov["leads_over_time"]["rows"]) == 14 and sum(r[1] for r in ov["leads_over_time"]["rows"]) == 1
    assert client.get("/agents/analytics/overview", headers=b).json()["pipeline"]["facts"]["total_leads"] == 0


def test_question_validation_and_auth(client, two_orgs):
    a, _ = two_orgs
    assert client.post("/agents/analytics/ask", headers=a, json={"question": "hi"}).status_code == 422
    assert client.post("/agents/analytics/ask", json={"question": "How many leads?"}).status_code == 401
