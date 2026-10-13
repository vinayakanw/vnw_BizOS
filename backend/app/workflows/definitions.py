"""What a workflow is. Stored as JSON, validated here, run by engine.py."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.tools.registry import REGISTRY

TRIGGERS = ("lead.created", "lead.hot", "conversation.escalated", "lead.inactive")
TRIGGER_LABELS = {
    "lead.created": "A new lead is captured",
    "lead.hot": "A lead becomes HOT",
    "conversation.escalated": "A conversation needs a human",
    "lead.inactive": "An open lead goes quiet (checked every few minutes)",
}


class Condition(BaseModel):
    field: Literal["score", "status", "intent", "purchase_stage", "quantity", "potential_value", "days_since_contact", "email", "phone", "company"]
    op: Literal["eq", "neq", "gte", "lte", "contains", "is_set", "not_set"]
    value: str | int | float | None = None


class Step(BaseModel):
    tool: Literal["create_quote", "create_followup_task", "draft_email"]
    args: dict[str, str | int | float] = Field(default_factory=dict)
    condition: Condition | None = None

    @model_validator(mode="after")
    def _known_args(self):
        allowed = set(REGISTRY[self.tool].args_model.model_fields)
        extra = set(self.args) - allowed
        if extra:
            raise ValueError(f"{self.tool} does not take: {', '.join(sorted(extra))}")
        return self


class WorkflowDef(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    trigger: Literal["lead.created", "lead.hot", "conversation.escalated", "lead.inactive"]
    enabled: bool = True
    conditions: list[Condition] = Field(default_factory=list, max_length=5)
    steps: list[Step] = Field(min_length=1, max_length=8)


DEFAULT_WORKFLOWS: list[dict] = [
    {
        "name": "Hot lead: fast response",
        "description": "When a lead turns HOT, create a call task due today and draft a follow-up email if we have their address.",
        "trigger": "lead.hot",
        "steps": [
            {"tool": "create_followup_task", "args": {"title": "Call {lead.name} now (HOT lead, potential value {lead.potential_value})", "due_in_days": 0}},
            {
                "tool": "draft_email",
                "args": {
                    "subject": "Your requirement",
                    "body": "Hi {lead.name},\n\nThanks for getting in touch. We have noted your requirement: {lead.requirement}\n\nWe will share the details shortly. Please reply here if you would like a call.",
                },
                "condition": {"field": "email", "op": "is_set"},
            },
        ],
    },
    {
        "name": "Bulk order prep",
        "description": "For new leads asking for 10 or more units, create a task to prepare bulk pricing.",
        "trigger": "lead.created",
        "conditions": [{"field": "quantity", "op": "gte", "value": 10}],
        "steps": [{"tool": "create_followup_task", "args": {"title": "Prepare bulk pricing for {lead.quantity} units ({lead.name})", "due_in_days": 1}}],
    },
    {
        "name": "Escalation follow-up",
        "description": "When the agent hands a conversation to a human, create a review task due today.",
        "trigger": "conversation.escalated",
        "steps": [{"tool": "create_followup_task", "args": {"title": "Review escalation for {lead.name}: {lead.next_action}", "due_in_days": 0}}],
    },
    {
        "name": "Quiet lead nudge",
        "description": "When an open lead has not been in touch for 3 days, create a follow-up task and draft a nudge email if we have their address.",
        "trigger": "lead.inactive",
        "conditions": [{"field": "days_since_contact", "op": "gte", "value": 3}],
        "steps": [
            {"tool": "create_followup_task", "args": {"title": "Follow up with {lead.name}: quiet for {lead.days_since_contact} days", "due_in_days": 0}},
            {
                "tool": "draft_email",
                "args": {
                    "subject": "Checking in",
                    "body": "Hi {lead.name},\n\nJust checking in on your requirement: {lead.requirement}\n\nLet us know if you have any questions or would like us to prepare a quote.",
                },
                "condition": {"field": "email", "op": "is_set"},
            },
        ],
    },
]
