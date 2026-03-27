"""Add wamid column to messages for WhatsApp dedup.

Revision ID: 003
Revises: 002
Create Date: 2026-03-27
"""

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("wamid", sa.String(128), nullable=True))
    op.create_index(
        "ix_msg_conv_wamid",
        "messages",
        ["conversation_id", "wamid"],
        unique=True,
        postgresql_where=sa.text("wamid IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_msg_conv_wamid", table_name="messages")
    op.drop_column("messages", "wamid")
