from typing import Literal

from pydantic import BaseModel, Field


class SupportAnalysis(BaseModel):
    category: Literal["faq", "order_status", "delivery", "return_refund", "warranty", "complaint", "technical", "greeting", "other"]
    urgency: Literal["low", "normal", "high"] = "normal"
    sentiment: Literal["positive", "neutral", "negative", "angry"] = "neutral"
    customer_name: str | None = None
    email: str | None = None
    phone: str | None = None
    order_reference: str | None = None
    issue_summary: str | None = None  # one short line
    search_terms: list[str] = Field(default_factory=list)
    wants_human: bool = False
    sensitive_request: bool = False  # refund demand, payment dispute, legal threat, safety issue, personal data


class SupportReply(BaseModel):
    reply: str = Field(min_length=1)
    needs_human: bool = False
    escalation_reason: str | None = None
