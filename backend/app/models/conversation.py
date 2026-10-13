from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin, new_id


class Conversation(Base, TenantMixin, TimestampMixin):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    channel: Mapped[str] = mapped_column(String(30), default="dashboard", nullable=False)
    customer_name: Mapped[str | None] = mapped_column(String(200))
    lead_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("leads.id", ondelete="SET NULL"), index=True)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    escalation_reason: Mapped[str | None] = mapped_column(Text)
    customer_email: Mapped[str | None] = mapped_column(String(320))
    customer_phone: Mapped[str | None] = mapped_column(String(50))
    # True once a staff member has replied. The AI stays quiet until someone hands the chat back.
    human_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default=false())
    # Presence: the public page pings on every poll. Used to decide if a staff reply also needs an email.
    customer_last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    customer_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Failed order lookups in this conversation (caps guessing of order numbers).
    lookup_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")


class Message(Base, TenantMixin, TimestampMixin):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # customer | agent | human
    content: Mapped[str] = mapped_column(Text, nullable=False)


class ChatAttachment(Base, TenantMixin, TimestampMixin):
    """A photo a customer sent in chat. Stored in the database because the host disk is ephemeral."""

    __tablename__ = "chat_attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_id: Mapped[str] = mapped_column(String(36), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
