"""Add index on inventory_items (dealership_id, ml_item_id) for outbound flow lookups.

Revision ID: 004
Revises: 003
Create Date: 2026-03-27
"""

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_inv_dealer_ml_item",
        "inventory_items",
        ["dealership_id", "ml_item_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_inv_dealer_ml_item", table_name="inventory_items")
