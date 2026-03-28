"""Add multi-tenancy columns to dealerships table.

Adds whatsapp_access_token, admin_username, admin_password_hash
to support per-dealership WABA tokens and admin credentials.

Revision ID: 006
Revises: 004
Create Date: 2026-03-27
"""

import sqlalchemy as sa
from alembic import op

revision = "006"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dealerships",
        sa.Column("whatsapp_access_token", sa.String(512), nullable=True),
    )
    op.add_column(
        "dealerships",
        sa.Column("admin_username", sa.String(128), nullable=True),
    )
    op.add_column(
        "dealerships",
        sa.Column("admin_password_hash", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dealerships", "admin_password_hash")
    op.drop_column("dealerships", "admin_username")
    op.drop_column("dealerships", "whatsapp_access_token")
