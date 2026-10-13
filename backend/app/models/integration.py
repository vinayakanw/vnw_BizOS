from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin, new_id
from app.models.product import JsonType


class Integration(Base, TenantMixin, TimestampMixin):
    """One row per org per kind (email | slack). Secret fields inside `config` are stored encrypted."""

    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("org_id", "kind", name="uq_integration_org_kind"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    config: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
