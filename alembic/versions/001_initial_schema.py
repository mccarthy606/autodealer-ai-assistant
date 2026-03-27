"""Initial schema.

Revision ID: 001
Revises:
Create Date: 2025-02-08

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dealerships",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=True),
        sa.Column("default_language", sa.String(8), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("phone", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "inventory_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dealership_id", sa.Integer(), nullable=False),
        sa.Column("brand", sa.String(128), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("trim", sa.String(128), nullable=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("condition", sa.Enum("new", "used", "zero_km", name="conditionenum"), nullable=False),
        sa.Column("km", sa.Integer(), nullable=True),
        sa.Column("price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("status", sa.Enum("available", "in_transit", "preorder", "sold", name="statusenum"), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("vin", sa.String(64), nullable=True),
        sa.Column("external_id", sa.String(128), nullable=True),
        sa.Column("source", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["dealership_id"], ["dealerships.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inv_dealer_brand_model", "inventory_items", ["dealership_id", "brand", "model"], unique=False)
    op.create_index("ix_inv_dealer_status", "inventory_items", ["dealership_id", "status"], unique=False)
    op.create_index("ix_inv_external_id", "inventory_items", ["dealership_id", "external_id"], unique=True)
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dealership_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(32), nullable=True),
        sa.Column("user_phone", sa.String(32), nullable=False),
        sa.Column("state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_message_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["dealership_id"], ["dealerships.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conv_dealer_phone", "conversations", ["dealership_id", "user_phone"], unique=True)
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("direction", sa.Enum("in", "out", name="messagedirectionenum"), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "leads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dealership_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("intent", sa.Enum("visit", "info", "financing", name="leadintentenum"), nullable=True),
        sa.Column("preferred_brand", sa.String(128), nullable=True),
        sa.Column("preferred_model", sa.String(128), nullable=True),
        sa.Column("budget_min", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("budget_max", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("status", sa.Enum("new", "qualified", "handed_off", "closed", name="leadstatusenum"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["dealership_id"], ["dealerships.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dealership_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["dealership_id"], ["dealerships.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_events_dealer_type_created", "events", ["dealership_id", "type", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_events_dealer_type_created", table_name="events")
    op.drop_table("events")
    op.drop_table("leads")
    op.drop_table("messages")
    op.drop_index("ix_conv_dealer_phone", table_name="conversations")
    op.drop_table("conversations")
    op.drop_index("ix_inv_external_id", table_name="inventory_items")
    op.drop_index("ix_inv_dealer_status", table_name="inventory_items")
    op.drop_index("ix_inv_dealer_brand_model", table_name="inventory_items")
    op.drop_table("inventory_items")
    op.drop_table("dealerships")
