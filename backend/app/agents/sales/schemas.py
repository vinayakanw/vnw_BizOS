from typing import Literal

from pydantic import BaseModel, Field


class Analysis(BaseModel):
    """Structured reading of the customer's message (and conversation so far)."""

    category: Literal["product_inquiry", "pricing", "purchase_intent", "support", "general", "other"]
    purchase_stage: Literal["browsing", "evaluating", "ready_to_buy"] = "browsing"
    customer_name: str | None = None
    company: str | None = None
    email: str | None = None
    phone: str | None = None
    quantity: int | None = Field(default=None, ge=1)
    budget_per_unit: float | None = Field(default=None, ge=0)
    currency: str | None = None
    requirement_summary: str | None = None
    use_case: str | None = None
    timeline: str | None = None
    product_search_terms: list[str] = Field(default_factory=list)
    wants_human: bool = False
    requests_discount: bool = False
    requested_discount_pct: float | None = Field(default=None, ge=0, le=100)
    chosen_product_name: str | None = None  # exact product the customer named or clearly chose
    sensitive_request: bool = False  # refunds, contracts, legal, payments, personal data


class ProposedAction(BaseModel):
    """An action the model *proposes*. Code validates it, applies policy and decides whether it runs."""

    tool: Literal["create_quote", "create_followup_task", "draft_email"]
    # create_quote
    product_name: str | None = None
    quantity: int | None = None
    discount_pct: float | None = None
    # create_followup_task
    title: str | None = None
    due_in_days: int | None = None
    # draft_email
    subject: str | None = None
    body: str | None = None

    def args(self) -> dict:
        keep = {
            "create_quote": ("product_name", "quantity", "discount_pct"),
            "create_followup_task": ("title", "due_in_days"),
            "draft_email": ("subject", "body"),
        }[self.tool]
        return {k: getattr(self, k) for k in keep if getattr(self, k) is not None}


class Reply(BaseModel):
    reply: str = Field(min_length=1)
    needs_human: bool = False
    escalation_reason: str | None = None
    actions: list[ProposedAction] = Field(default_factory=list)
