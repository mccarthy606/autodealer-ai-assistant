"""MVP schema extensions: photos, mode, handoff, source, channel, tags, ml.

Revision ID: 002
Revises: 001
Create Date: 2026-02-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- InventoryItem extensions ---
    op.add_column("inventory_items", sa.Column("title", sa.String(255), nullable=True))
    op.add_column("inventory_items", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("inventory_items", sa.Column("photos", postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default="[]"))
    op.add_column("inventory_items", sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default="[]"))
    op.add_column("inventory_items", sa.Column("ml_item_id", sa.String(128), nullable=True))

    # Add 'reserved' to status enum
    op.execute("ALTER TYPE statusenum ADD VALUE IF NOT EXISTS 'reserved'")

    # --- Conversation extensions ---
    op.add_column("conversations", sa.Column("mode", sa.String(16), server_default="bot", nullable=True))
    op.add_column("conversations", sa.Column("handoff_reason", sa.String(64), nullable=True))
    op.add_column("conversations", sa.Column("last_handoff_at", sa.DateTime(), nullable=True))
    op.add_column("conversations", sa.Column("updated_at", sa.DateTime(), nullable=True))

    # --- Message extensions ---
    op.add_column("messages", sa.Column("channel", sa.String(32), nullable=True))
    op.add_column("messages", sa.Column("attachments", postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default="[]"))

    # --- Lead extensions ---
    op.add_column("leads", sa.Column("source", sa.String(32), nullable=True))
    op.add_column("leads", sa.Column("language", sa.String(8), nullable=True))
    op.add_column("leads", sa.Column("last_car_id", sa.Integer(), nullable=True))
    op.add_column("leads", sa.Column("preferred_time", sa.String(128), nullable=True))
    op.add_column("leads", sa.Column("handoff_reason", sa.String(64), nullable=True))
    op.add_column("leads", sa.Column("conversation_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_leads_last_car", "leads", "inventory_items", ["last_car_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_leads_conversation", "leads", "conversations", ["conversation_id"], ["id"], ondelete="SET NULL")

    # Add 'trade_in' to lead intent enum
    op.execute("ALTER TYPE leadintentenum ADD VALUE IF NOT EXISTS 'trade_in'")

    # --- Dealership extensions ---
    op.add_column("dealerships", sa.Column("business_hours", sa.Text(), nullable=True))
    op.add_column("dealerships", sa.Column("whatsapp_phone_number_id", sa.String(64), nullable=True))
    op.add_column("dealerships", sa.Column("whatsapp_verify_token", sa.String(128), nullable=True))
    op.add_column("dealerships", sa.Column("ml_user_id", sa.String(64), nullable=True))

    # --- Event extensions ---
    op.add_column("events", sa.Column("conversation_id", sa.Integer(), nullable=True))
    op.add_column("events", sa.Column("lead_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    # Events
    op.drop_column("events", "lead_id")
    op.drop_column("events", "conversation_id")

    # Dealership
    op.drop_column("dealerships", "ml_user_id")
    op.drop_column("dealerships", "whatsapp_verify_token")
    op.drop_column("dealerships", "whatsapp_phone_number_id")
    op.drop_column("dealerships", "business_hours")

    # Lead
    op.drop_constraint("fk_leads_conversation", "leads", type_="foreignkey")
    op.drop_constraint("fk_leads_last_car", "leads", type_="foreignkey")
    op.drop_column("leads", "conversation_id")
    op.drop_column("leads", "handoff_reason")
    op.drop_column("leads", "preferred_time")
    op.drop_column("leads", "last_car_id")
    op.drop_column("leads", "language")
    op.drop_column("leads", "source")

    # Message
    op.drop_column("messages", "attachments")
    op.drop_column("messages", "channel")

    # Conversation
    op.drop_column("conversations", "updated_at")
    op.drop_column("conversations", "last_handoff_at")
    op.drop_column("conversations", "handoff_reason")
    op.drop_column("conversations", "mode")

    # InventoryItem
    op.drop_column("inventory_items", "ml_item_id")
    op.drop_column("inventory_items", "tags")
    op.drop_column("inventory_items", "photos")
    op.drop_column("inventory_items", "description")
    op.drop_column("inventory_items", "title")
