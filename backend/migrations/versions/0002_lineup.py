"""add users.lineup_json (lineup scoring mode)

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-06

Backfill: nullable, default NULL — a null lineup means "auto-start my best players"
(app/engine/scoring.py), so existing users need no data change.
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("lineup_json", sa.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("users", "lineup_json")
