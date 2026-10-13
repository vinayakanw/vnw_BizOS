import json

from app.llm.factory import set_llm
from tests.test_sales_agent import BUY, OK_REPLY, ScriptedLLM, _chat, _seed


class SupportLLM:
    def __init__(self, analyses, replies):
        self.analyses, self.replies = list(analyses), list(replies)
        self.reply_prompts = []

    def generate(self, system, prompt, *, json_mode=False):
        if "TASK: SUPPORT_ANALYZE" in system:
            out = self.analyses.pop(0) if len(self.analyses) > 1 else self.analyses[0]
        elif "TASK: SUPPORT_REPLY" in system:
            self.reply_prompts.append(prompt)
            out = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        else:
            raise AssertionError("unexpected prompt")
        return json.dumps(out)


FAQ_Q = {"category": "faq", "search_terms": ["warranty"], "issue_summary": "Warranty question"}
ANSWER = {"reply": "All laptops come with a 1 year on-site warranty.", "needs_human": False}


def _chat_s(client, headers, message="Is there a warranty on the laptops?", conv=None):
    r = client.post("/agents/support/chat", headers=headers, json={"message": message, "conversation_id": conv})
    assert r.status_code == 200, r.text
    return r.json()


def test_faq_answered_from_knowledge_without_ticket(client, two_orgs):
    a, _ = two_orgs
    _seed(client, a)
    llm = SupportLLM([FAQ_Q], [ANSWER])
    set_llm(llm)
    body = _chat_s(client, a)
    assert body["reply"].startswith("All laptops") and body["escalated"] is False
    assert body["ticket"] is None and body["sources"]
    assert "[Source:" in llm.reply_prompts[0]  # grounded on retrieved knowledge
    assert client.get("/tickets", headers=a).json() == []


def test_order_not_found_escalates_with_ticket(client, two_orgs):
    a, _ = two_orgs
    _seed(client, a)
    ana = {"category": "order_status", "order_reference": "ORD-77", "email": "x@y.com", "issue_summary": "Where is my order", "urgency": "high"}
    set_llm(SupportLLM([ana], [{"reply": "I could not find that order, a teammate will check.", "needs_human": True, "escalation_reason": "Order not found"}]))
    body = _chat_s(client, a, "Where is my order ORD-77?")
    assert body["escalated"] is True and "Order not found" in body["escalation_reason"]
    t = body["ticket"]
    assert t["number"] == "T-0001" and t["priority"] == "high" and t["order_reference"] == "ORD-77" and t["email"] == "x@y.com"
    assert client.get("/tickets/count", headers=a).json() == {"open": 1}


def test_no_knowledge_escalates_and_followup_updates_same_ticket(client, two_orgs):
    a, _ = two_orgs
    # empty workspace: nothing in the knowledge base
    first = {"category": "technical", "issue_summary": "Laptop will not boot"}
    set_llm(SupportLLM([first, {"category": "technical", "email": "c@d.com", "sentiment": "angry"}], [{"reply": "Sorry to hear that.", "needs_human": False}]))
    one = _chat_s(client, a, "My laptop will not boot")
    assert one["escalated"] and "Nothing in the knowledge base" in one["escalation_reason"]
    two = _chat_s(client, a, "My email is c@d.com and this is unacceptable", one["conversation_id"])
    assert two["ticket"]["id"] == one["ticket"]["id"]
    assert two["ticket"]["email"] == "c@d.com" and two["ticket"]["priority"] == "high"
    assert len(client.get("/tickets", headers=a).json()) == 1


def test_refund_demand_and_human_request_escalate(client, two_orgs):
    a, _ = two_orgs
    _seed(client, a)
    ana = {"category": "return_refund", "sensitive_request": True, "wants_human": True, "search_terms": ["return policy"]}
    set_llm(SupportLLM([ana], [{"reply": "I will pass this to the team.", "needs_human": False}]))
    body = _chat_s(client, a, "Give me my money back or I will sue. Let me talk to a manager")
    assert body["escalated"]
    for part in ("asked for a human", "Sensitive request"):
        assert part in body["escalation_reason"]
    assert body["ticket"]["priority"] == "high"


def test_ticket_management_and_resolved_reopens(client, two_orgs):
    a, _ = two_orgs
    ana = {"category": "complaint", "issue_summary": "Late delivery"}
    set_llm(SupportLLM([ana], [{"reply": "Sorry about that.", "needs_human": True, "escalation_reason": "Review"}]))
    body = _chat_s(client, a, "My delivery is late")
    tid = body["ticket"]["id"]
    d = client.get(f"/tickets/{tid}", headers=a).json()
    assert [m["role"] for m in d["conversation"]["messages"]] == ["customer", "agent"]

    assert client.patch(f"/tickets/{tid}", headers=a, json={"status": "resolved", "priority": "low"}).json()["status"] == "resolved"
    assert client.get("/tickets/count", headers=a).json() == {"open": 0}
    assert client.get("/tickets?status=resolved", headers=a).json()[0]["id"] == tid
    assert client.get("/tickets?status=open", headers=a).json() == []
    assert client.patch(f"/tickets/{tid}", headers=a, json={"status": "closed"}).status_code == 422
    assert client.get("/tickets?status=bogus", headers=a).status_code == 422

    _chat_s(client, a, "Still nothing", body["conversation_id"])
    assert client.get(f"/tickets/{tid}", headers=a).json()["ticket"]["status"] == "open"  # new message reopens it


def test_support_tickets_are_tenant_isolated_and_channels_dont_mix(client, two_orgs):
    a, b = two_orgs
    ana = {"category": "complaint", "issue_summary": "Broken screen"}
    set_llm(SupportLLM([ana], [{"reply": "Sorry.", "needs_human": True, "escalation_reason": "Review"}]))
    body = _chat_s(client, a, "Screen is broken")
    tid, cid = body["ticket"]["id"], body["conversation_id"]
    assert client.get("/tickets", headers=b).json() == []
    assert client.get("/tickets/count", headers=b).json() == {"open": 0}
    assert client.get(f"/tickets/{tid}", headers=b).status_code == 404
    assert client.patch(f"/tickets/{tid}", headers=b, json={"status": "resolved"}).status_code == 404
    r = client.post("/agents/support/chat", headers=b, json={"message": "hi", "conversation_id": cid})
    assert r.status_code == 404  # another tenant's conversation

    # a support conversation cannot be continued through the sales agent, and vice versa
    set_llm(ScriptedLLM([BUY], [OK_REPLY]))
    assert _chat(client, a, conversation_id=cid).status_code == 404
    sales_conv = _chat(client, a).json()["conversation_id"]
    set_llm(SupportLLM([ana], [{"reply": "x", "needs_human": False}]))
    assert client.post("/agents/support/chat", headers=a, json={"message": "hi", "conversation_id": sales_conv}).status_code == 404


def test_analytics_can_report_on_tickets(client, two_orgs):
    from tests.test_analytics import AnalyticsLLM

    a, _ = two_orgs
    ana = {"category": "complaint", "issue_summary": "Late"}
    set_llm(SupportLLM([ana], [{"reply": "Sorry.", "needs_human": True, "escalation_reason": "Review"}]))
    _chat_s(client, a, "Late delivery")
    set_llm(AnalyticsLLM({"metrics": [{"metric": "tickets_summary"}]}))
    r = client.post("/agents/analytics/ask", headers=a, json={"question": "How many support tickets do I have?"}).json()
    assert r["results"][0]["facts"]["tickets"] == 1 and r["results"][0]["facts"]["open"] == 1
