from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin, new_id
from app.models.product import JsonType


class AgentRun(Base, TenantMixin, TimestampMixin):
    """One execution of an agent, with a human-readable step trace (the Agent Activity log)."""

    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    agent: Mapped[str] = mapped_column(String(30), default="sales", nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)  # running|completed|escalated|failed
    summary: Mapped[str | None] = mapped_column(Text)
    steps: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
