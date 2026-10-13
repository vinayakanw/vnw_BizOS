from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class BusinessProfile(Base, TimestampMixin):
    """One row per organization. Extra business context the agents will use."""

    __tablename__ = "business_profiles"

    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    description: Mapped[str | None] = mapped_column(Text)
    target_customers: Mapped[str | None] = mapped_column(Text)
    tone: Mapped[str | None] = mapped_column(String(100))
    discount_policy: Mapped[str | None] = mapped_column(Text)
    support_email: Mapped[str | None] = mapped_column(String(320))
