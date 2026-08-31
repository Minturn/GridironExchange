"""add dividend_accruals (live ownership-over-time accrual, SPEC §14)

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-30

New table only — nothing to backfill. Only written when a league runs dividend_mode
"accrual" and the live-poll job records ticks; snapshot-mode leagues are untouched.
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

MONEY = sa.Numeric(12, 2)
POINTS = sa.Numeric(7, 2)


def upgrade() -> None:
    op.create_table(
        "dividend_accruals",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("league_id", sa.Integer, sa.ForeignKey("leagues.id"), nullable=False),
        sa.Column("week", sa.Integer, nullable=False),
        sa.Column("player_id", sa.String(20), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("ts", sa.DateTime, nullable=False),
        sa.Column("shares_held", sa.Integer, nullable=False),
        sa.Column("points_delta", POINTS, nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("settled", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_accrual_league_week", "dividend_accruals", ["league_id", "week"]
    )


def downgrade() -> None:
    op.drop_index("ix_accrual_league_week", table_name="dividend_accruals")
    op.drop_table("dividend_accruals")
