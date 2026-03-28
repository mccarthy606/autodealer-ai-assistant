"""Add billing subscription columns to dealerships table.

Adds subscription_status, subscription_id, ls_customer_id, plan,
trial_ends_at, grace_period_ends_at to support per-dealership billing.

Revision ID: 007
Revises: 006
Create Date: 2026-03-27
"""

import sqlalchemy as sa
from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dealerships",
        sa.Column("subscription_status", sa.String(32), nullable=True),
    )
    op.add_column(
        "dealerships",
        sa.Column("subscription_id", sa.String(128), nullable=True),
    )
    op.add_column(
        "dealerships",
        sa.Column("ls_customer_id", sa.String(128), nullable=True),
    )
    op.add_column(
        "dealerships",
        sa.Column("plan", sa.String(64), nullable=True),
    )
    op.add_column(
        "dealerships",
        sa.Column("trial_ends_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "dealerships",
        sa.Column("grace_period_ends_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dealerships", "grace_period_ends_at")
    op.drop_column("dealerships", "trial_ends_at")
    op.drop_column("dealerships", "plan")
    op.drop_column("dealerships", "ls_customer_id")
    op.drop_column("dealerships", "subscription_id")
    op.drop_column("dealerships", "subscription_status")
