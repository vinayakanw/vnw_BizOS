from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin, new_id
from app.models.product import JsonType

ORDER_STATUSES = ("placed", "packed", "shipped", "out_for_delivery", "delivered", "cancelled", "returned")


class Order(Base, TenantMixin, TimestampMixin):
    """An order the business entered or imported. The support agent reads these to answer "where is my order"."""

    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("org_id", "order_ref", name="uq_orders_org_ref"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_ref: Mapped[str] = mapped_column(String(60), nullable=False)  # stored upper case, no spaces
    customer_name: Mapped[str | None] = mapped_column(String(200))
    customer_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="placed", nullable=False)
    carrier: Mapped[str | None] = mapped_column(String(100))
    tracking_id: Mapped[str | None] = mapped_column(String(100))
    tracking_url: Mapped[str | None] = mapped_column(String(500))
    items: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)  # [{"name": "...", "quantity": 2}]
    total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    placed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expected_delivery: Mapped[date | None] = mapped_column(Date)
