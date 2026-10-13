import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def new_id() -> str:
    return str(uuid.uuid4())


class TenantMixin:
    """Every business-owned table inherits this. All queries must filter on org_id."""

    @declared_attr
    def org_id(cls) -> Mapped[str]:
        from sqlalchemy import ForeignKey, String

        return mapped_column(
            String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
        )
