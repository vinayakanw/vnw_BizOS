"""customer features: presence, quote links, orders, chat photos

Revision ID: 0004
Revises: 0003
"""
import secrets

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TS = sa.text("(CURRENT_TIMESTAMP)")


def upgrade() -> None:
    op.add_column("conversations", sa.Column("customer_last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversations", sa.Column("customer_notified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversations", sa.Column("lookup_failures", sa.Integer(), server_default="0", nullable=False))

    op.add_column("quotes", sa.Column("public_token", sa.String(length=64), nullable=True))
    op.add_column("quotes", sa.Column("customer_response", sa.String(length=20), nullable=True))
    op.add_column("quotes", sa.Column("customer_note", sa.Text(), nullable=True))
    op.add_column("quotes", sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("quotes", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    # Existing quotes get a link token too.
    conn = op.get_bind()
    for (qid,) in conn.execute(sa.text("SELECT id FROM quotes")).fetchall():
        conn.execute(sa.text("UPDATE quotes SET public_token = :t WHERE id = :i"), {"t": secrets.token_urlsafe(24), "i": qid})
    op.create_index(op.f("ix_quotes_public_token"), "quotes", ["public_token"], unique=True)

    op.create_table(
        "orders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("order_ref", sa.String(length=60), nullable=False),
        sa.Column("customer_name", sa.String(length=200), nullable=True),
        sa.Column("customer_email", sa.String(length=320), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("carrier", sa.String(length=100), nullable=True),
        sa.Column("tracking_id", sa.String(length=100), nullable=True),
        sa.Column("tracking_url", sa.String(length=500), nullable=True),
        sa.Column("items", sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("total", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_delivery", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=TS, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=TS, nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "order_ref", name="uq_orders_org_ref"),
    )
    op.create_index(op.f("ix_orders_org_id"), "orders", ["org_id"], unique=False)
    op.create_index(op.f("ix_orders_customer_email"), "orders", ["customer_email"], unique=False)

    op.create_table(
        "chat_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("content_type", sa.String(length=50), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=TS, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=TS, nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chat_attachments_org_id"), "chat_attachments", ["org_id"], unique=False)
    op.create_index(op.f("ix_chat_attachments_conversation_id"), "chat_attachments", ["conversation_id"], unique=False)
    op.create_index(op.f("ix_chat_attachments_message_id"), "chat_attachments", ["message_id"], unique=False)


def downgrade() -> None:
    op.drop_table("chat_attachments")
    op.drop_table("orders")
    op.drop_index(op.f("ix_quotes_public_token"), table_name="quotes")
    for c in ("expires_at", "responded_at", "customer_note", "customer_response", "public_token"):
        op.drop_column("quotes", c)
    for c in ("lookup_failures", "customer_notified_at", "customer_last_seen_at"):
        op.drop_column("conversations", c)
