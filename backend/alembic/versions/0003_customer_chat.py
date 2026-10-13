"""customer chat: conversation contact + human takeover, chat settings

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("customer_email", sa.String(length=320), nullable=True))
    op.add_column("conversations", sa.Column("customer_phone", sa.String(length=50), nullable=True))
    op.add_column("conversations", sa.Column("human_active", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.create_table(
        "chat_settings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=60), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("welcome_message", sa.Text(), nullable=False),
        sa.Column("sales_enabled", sa.Boolean(), nullable=False),
        sa.Column("support_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(op.f("ix_chat_settings_org_id"), "chat_settings", ["org_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_chat_settings_org_id"), table_name="chat_settings")
    op.drop_table("chat_settings")
    op.drop_column("conversations", "human_active")
    op.drop_column("conversations", "customer_phone")
    op.drop_column("conversations", "customer_email")
