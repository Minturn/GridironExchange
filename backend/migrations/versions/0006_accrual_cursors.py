"""add accrual_cursors (restart-safe live-poll diff baseline)

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

POINTS = sa.Numeric(7, 2)


def upgrade() -> None:
    op.create_table(
        "accrual_cursors",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("league_id", sa.Integer, sa.ForeignKey("leagues.id"), nullable=False),
        sa.Column("week", sa.Integer, nullable=False),
        sa.Column("player_id", sa.String(20), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("cume", POINTS, nullable=False, server_default="0"),
        sa.UniqueConstraint("league_id", "week", "player_id"),
    )


def downgrade() -> None:
    op.drop_table("accrual_cursors")
