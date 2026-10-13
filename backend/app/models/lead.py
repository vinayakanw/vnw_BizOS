from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin, new_id
from app.models.product import JsonType


class Lead(Base, TenantMixin, TimestampMixin):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str | None] = mapped_column(String(36), index=True)

    name: Mapped[str | None] = mapped_column(String(200))
    company: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))

    requirement: Mapped[str | None] = mapped_column(Text)
    use_case: Mapped[str | None] = mapped_column(Text)
    timeline: Mapped[str | None] = mapped_column(String(200))
    quantity: Mapped[int | None] = mapped_column(Integer)
    budget_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    potential_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

    purchase_stage: Mapped[str] = mapped_column(String(20), default="browsing", nullable=False)
    product_match: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    intent: Mapped[str] = mapped_column(String(10), default="LOW", nullable=False)  # LOW | MEDIUM | HIGH
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="NEW", nullable=False, index=True)
    score_reasons: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)
    next_action: Mapped[str | None] = mapped_column(Text)
    last_interaction_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
