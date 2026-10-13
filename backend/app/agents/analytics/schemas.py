from typing import Literal

from pydantic import BaseModel, Field

METRICS = Literal[
    "pipeline_summary", "leads_over_time", "top_leads", "stale_leads",
    "quotes_summary", "approvals_summary", "tasks_summary", "tickets_summary", "agent_activity",
]


class MetricCall(BaseModel):
    metric: METRICS
    days: int | None = Field(default=None, ge=1)
    n: int | None = Field(default=None, ge=1)
    order_by: Literal["score", "value"] | None = None


class Plan(BaseModel):
    """Which prepared reports answer the question. The model never sees raw tables or does arithmetic."""

    metrics: list[MetricCall] = Field(default_factory=list)
    out_of_scope: bool = False


class Answer(BaseModel):
    answer: str = Field(min_length=1)
