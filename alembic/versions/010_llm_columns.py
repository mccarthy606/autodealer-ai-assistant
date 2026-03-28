"""Add LLM configuration columns to dealerships.

Revision ID: 010
Revises: 009
Create Date: 2026-03-28
"""

from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dealerships", sa.Column("llm_api_key", sa.String(768), nullable=True))
    op.add_column("dealerships", sa.Column("llm_model", sa.String(64), nullable=True))
    op.add_column("dealerships", sa.Column("llm_enabled", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("dealerships", "llm_enabled")
    op.drop_column("dealerships", "llm_model")
    op.drop_column("dealerships", "llm_api_key")
