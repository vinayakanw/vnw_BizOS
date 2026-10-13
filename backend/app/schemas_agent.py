from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChatIn(BaseModel):
    conversation_id: str | None = None
    message: str = Field(min_length=1, max_length=2000)
    customer_name: str | None = Field(default=None, max_length=200)


class LeadOut(BaseModel):
    id: str
    name: str | None
    company: str | None
    email: str | None
    phone: str | None
    requirement: str | None
    use_case: str | None
    timeline: str | None
    quantity: int | None
    budget_per_unit: float | None
    currency: str | None
    potential_value: float | None
    purchase_stage: str
    intent: str
    score: int
    status: str
    score_reasons: list[str]
    next_action: str | None
    last_interaction_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class LeadPatch(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    # CONVERTED / LOST are set by a human. OPEN puts the lead back on the agent's score-based status.
    status: str | None = Field(default=None, pattern="^(CONVERTED|LOST|OPEN)$")


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class NoteOut(BaseModel):
    id: str
    author_name: str
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    seq: int
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationOut(BaseModel):
    id: str
    escalated: bool
    escalation_reason: str | None
    created_at: datetime
    messages: list[MessageOut]


class QuoteOut(BaseModel):
    id: str
    number: str
    items: list[dict]
    currency: str
    subtotal: float
    discount_pct: float
    total: float
    status: str
    public_token: str | None = None
    customer_response: str | None = None
    customer_note: str | None = None
    responded_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskOut(BaseModel):
    id: str
    title: str
    due_at: datetime | None
    status: str
    created_by: str

    model_config = {"from_attributes": True}


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_in_days: int = Field(default=1, ge=0, le=365)


class TaskPatch(BaseModel):
    status: str = Field(pattern="^(open|done)$")


class ToolCallOut(BaseModel):
    id: str
    lead_id: str | None
    lead_name: str | None = None
    tool: str
    args: dict
    summary: str
    status: str
    approval_reason: str | None
    result: dict | None
    error: str | None
    decided_by: str | None
    decided_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RulesIn(BaseModel):
    auto_discount_max_pct: float = Field(ge=0, le=100)
    auto_discount_min_qty: int = Field(ge=1, le=100000)
    quote_approval_above: float | None = Field(default=None, ge=0)
    always_approve_tools: list[Literal["create_quote", "create_followup_task", "draft_email"]] = []


class ReasonIn(BaseModel):
    reason: str | None = Field(default=None, max_length=300)


class ActionOut(BaseModel):
    id: str
    tool: str
    status: str
    summary: str
    error: str | None = None


class LeadDetail(BaseModel):
    lead: LeadOut
    notes: list[NoteOut]
    conversations: list[ConversationOut]
    quotes: list[QuoteOut] = []
    tasks: list[TaskOut] = []
    tool_calls: list[ToolCallOut] = []


class PipelineSummary(BaseModel):
    counts: dict[str, int]
    open_value: float
    won_value: float
    lost_value: float
    total: int
    conversion_rate: float  # converted / (converted + lost), 0 when none closed


class StepOut(BaseModel):
    t: str
    step: str
    detail: str = ""


class ProductMatchOut(BaseModel):
    name: str
    price: float
    currency: str
    stock: int | None
    within_budget: bool | None


class ChatOut(BaseModel):
    conversation_id: str
    reply: str
    escalated: bool
    escalation_reason: str | None
    lead: LeadOut | None
    run_id: str
    steps: list[StepOut]
    products: list[ProductMatchOut]
    actions: list[ActionOut] = []


class RunOut(BaseModel):
    id: str
    agent: str
    conversation_id: str | None
    status: str
    summary: str | None
    steps: list[StepOut]
    error: str | None
    duration_ms: int | None
    created_at: datetime

    model_config = {"from_attributes": True}
