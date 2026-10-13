from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

import secrets

from app.models.base import Base, TenantMixin, TimestampMixin, new_id
from app.models.product import JsonType


class ToolCall(Base, TenantMixin, TimestampMixin):
    """Every action an agent proposes. The audit log and the approval queue in one table."""

    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str | None] = mapped_column(String(36), index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), index=True)
    lead_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("leads.id", ondelete="SET NULL"), index=True)
    tool: Mapped[str] = mapped_column(String(50), nullable=False)
    args: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # executed | pending_approval | rejected | failed
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    approval_reason: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JsonType)
    error: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[str | None] = mapped_column(String(200))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Quote(Base, TenantMixin, TimestampMixin):
    __tablename__ = "quotes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    lead_id: Mapped[str] = mapped_column(String(36), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    number: Mapped[str] = mapped_column(String(20), nullable=False)
    items: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    discount_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    # draft | sent | accepted | declined | changes_requested
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    # The customer opens /quote/<public_token>. Unguessable, one quote only.
    public_token: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, default=lambda: secrets.token_urlsafe(24))
    customer_response: Mapped[str | None] = mapped_column(String(20))  # accepted | declined | changes_requested
    customer_note: Mapped[str | None] = mapped_column(Text)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LeadTask(Base, TenantMixin, TimestampMixin):
    __tablename__ = "lead_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    lead_id: Mapped[str] = mapped_column(String(36), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(10), default="open", nullable=False)  # open | done
    created_by: Mapped[str] = mapped_column(String(200), default="Sales Agent", nullable=False)


class ApprovalRules(Base, TenantMixin, TimestampMixin):
    """Per-organization limits. No row means the defaults from settings apply."""

    __tablename__ = "approval_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    auto_discount_max_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    auto_discount_min_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    quote_approval_above: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    always_approve_tools: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)
