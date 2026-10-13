from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin, new_id
from app.models.product import JsonType


class Workflow(Base, TenantMixin, TimestampMixin):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    trigger: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    conditions: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)
    steps: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)


class WorkflowRun(Base, TenantMixin, TimestampMixin):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workflow_id: Mapped[str] = mapped_column(String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    lead_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("leads.id", ondelete="SET NULL"), index=True)
    trigger: Mapped[str] = mapped_column(String(40), nullable=False)  # a trigger name, or "manual"
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # completed | partial | failed
    steps: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
