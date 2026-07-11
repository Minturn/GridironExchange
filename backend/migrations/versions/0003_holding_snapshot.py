"""add holding_snapshots (dividend record-date at kickoff)

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-09

New table only — nothing to backfill. Weeks with no snapshot fall back to live
holdings in post_week_dividends, so existing leagues/dividends are unaffected until
the game-lock job starts writing snapshots at kickoff.
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "holding_snapshots",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("league_id", sa.Integer, sa.ForeignKey("leagues.id"), nullable=False),
        sa.Column("week", sa.Integer, nullable=False),
        sa.Column("player_id", sa.String(20), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("shares", sa.Integer, nullable=False),
        sa.UniqueConstraint("league_id", "week", "player_id", "user_id"),
    )


def downgrade() -> None:
    op.drop_table("holding_snapshots")
