from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_id


class ChatSettings(Base, TimestampMixin):
    """Public customer chat for one business. Off until the owner turns it on."""

    __tablename__ = "chat_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    slug: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    welcome_message: Mapped[str] = mapped_column(Text, default="Hi! How can we help you today?", nullable=False)
    sales_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    support_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
