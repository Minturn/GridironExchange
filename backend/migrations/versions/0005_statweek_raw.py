"""add stat_weeks.raw (global raw stat line, for per-league scoring)

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-30

Nullable JSON — existing rows and manual stat-fixes have no raw line and keep paying
off `pts` (full PPR), so nothing changes until the sync starts storing raw stats.
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stat_weeks", sa.Column("raw", sa.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("stat_weeks", "raw")
