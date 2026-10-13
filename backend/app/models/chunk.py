from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.core.config import settings
from app.models.base import Base, TenantMixin, TimestampMixin, new_id

# pgvector on Postgres, plain JSON list on SQLite (tests only).
EmbeddingType = Vector(settings.embedding_dim).with_variant(JSON(), "sqlite")


class Chunk(Base, TenantMixin, TimestampMixin):
    """One searchable piece of business knowledge (document passage or FAQ)."""

    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # document | faq
    source_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(EmbeddingType, nullable=False)
