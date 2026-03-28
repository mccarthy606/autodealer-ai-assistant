"""Add client integration credential columns to dealerships.

Revision ID: 008
Revises: 007
Create Date: 2026-03-28
"""

from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dealerships", sa.Column("whatsapp_webhook_secret", sa.String(128), nullable=True))
    op.add_column("dealerships", sa.Column("ml_access_token", sa.String(512), nullable=True))
    op.add_column("dealerships", sa.Column("ml_refresh_token", sa.String(512), nullable=True))
    op.add_column("dealerships", sa.Column("ml_app_id", sa.String(64), nullable=True))
    op.add_column("dealerships", sa.Column("ml_client_secret", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column("dealerships", "ml_client_secret")
    op.drop_column("dealerships", "ml_app_id")
    op.drop_column("dealerships", "ml_refresh_token")
    op.drop_column("dealerships", "ml_access_token")
    op.drop_column("dealerships", "whatsapp_webhook_secret")
