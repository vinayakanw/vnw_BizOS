from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin, new_id
from app.models.product import JsonType


class Briefing(Base, TenantMixin, TimestampMixin):
    """A founder briefing: the numbers it was built from, the attention items, and the written summary."""

    __tablename__ = "briefings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    period_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    headline: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ai_written: Mapped[bool] = mapped_column(default=True, nullable=False)
    facts: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    priorities: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)  # [{item, why}]
    run_id: Mapped[str | None] = mapped_column(String(36))
