from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin, new_id


class Ticket(Base, TenantMixin, TimestampMixin):
    """A support case. One per support conversation."""

    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    number: Mapped[str] = mapped_column(String(20), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), default="normal", nullable=False)  # low | normal | high
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False, index=True)  # open | in_progress | resolved
    customer_name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    order_reference: Mapped[str | None] = mapped_column(String(100))
    escalation_reason: Mapped[str | None] = mapped_column(Text)
