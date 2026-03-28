"""Add ML sync status columns to dealerships.

Revision ID: 009
Revises: 008
Create Date: 2026-03-28
"""

from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dealerships", sa.Column("ml_last_sync_at", sa.DateTime(), nullable=True))
    op.add_column("dealerships", sa.Column("ml_last_sync_added", sa.Integer(), nullable=True))
    op.add_column("dealerships", sa.Column("ml_last_sync_updated", sa.Integer(), nullable=True))
    op.add_column("dealerships", sa.Column("ml_last_sync_sold", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("dealerships", "ml_last_sync_sold")
    op.drop_column("dealerships", "ml_last_sync_updated")
    op.drop_column("dealerships", "ml_last_sync_added")
    op.drop_column("dealerships", "ml_last_sync_at")
