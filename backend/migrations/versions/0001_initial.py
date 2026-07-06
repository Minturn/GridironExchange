"""initial schema — SPEC §7; league_id on every league-scoped table from day one

Revision ID: 0001
Revises:
Create Date: 2026-07-05

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

MONEY = sa.Numeric(12, 2)
POINTS = sa.Numeric(7, 2)
SLOPE = sa.Numeric(12, 6)


def upgrade() -> None:
    op.create_table(
        "leagues",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("invite_code", sa.String(40), nullable=False, unique=True),
        sa.Column("season_year", sa.Integer, nullable=False),
        sa.Column("settings_json", sa.JSON, nullable=True),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("league_id", sa.Integer, sa.ForeignKey("leagues.id"), nullable=False),
        sa.Column("username", sa.String(40), nullable=False),
        sa.Column("pw_hash", sa.String(200), nullable=True),
        sa.Column("is_commissioner", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("cash", MONEY, nullable=False, server_default="0.00"),
        sa.UniqueConstraint("league_id", "username"),
    )
    op.create_table(
        "players",
        sa.Column("id", sa.String(20), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("team", sa.String(4), nullable=True),
        sa.Column("pos", sa.String(4), nullable=False),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("bye_week", sa.Integer, nullable=True),
    )
    op.create_table(
        "listings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("league_id", sa.Integer, sa.ForeignKey("leagues.id"), nullable=False),
        sa.Column("player_id", sa.String(20), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("p0", MONEY, nullable=False),
        sa.Column("slope", SLOPE, nullable=False),
        sa.Column("shares_outstanding", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime, nullable=True),
        sa.UniqueConstraint("league_id", "player_id"),
    )
    op.create_table(
        "holdings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("league_id", sa.Integer, sa.ForeignKey("leagues.id"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("player_id", sa.String(20), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("shares", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("user_id", "player_id"),
    )
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("league_id", sa.Integer, sa.ForeignKey("leagues.id"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("player_id", sa.String(20), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("ts", sa.DateTime, nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("shares", sa.Integer, nullable=False),
        sa.Column("price_avg", MONEY, nullable=False),
        sa.Column("gross", MONEY, nullable=False),
        sa.Column("fee", MONEY, nullable=False),
        sa.Column("cash_after", MONEY, nullable=False),
    )
    op.create_index("ix_trades_league_ts", "trades", ["league_id", "ts"])
    op.create_table(
        "dividends",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("league_id", sa.Integer, sa.ForeignKey("leagues.id"), nullable=False),
        sa.Column("week", sa.Integer, nullable=False),
        sa.Column("player_id", sa.String(20), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("shares_held", sa.Integer, nullable=False),
        sa.Column("pts", POINTS, nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("ts", sa.DateTime, nullable=False),
        sa.UniqueConstraint("league_id", "week", "player_id", "user_id"),
    )
    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("league_id", sa.Integer, sa.ForeignKey("leagues.id"), nullable=False),
        sa.Column("player_id", sa.String(20), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("ts", sa.DateTime, nullable=False),
        sa.Column("price", MONEY, nullable=False),
    )
    op.create_index("ix_price_history_player_ts", "price_history", ["league_id", "player_id", "ts"])
    op.create_table(
        "stat_weeks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("season", sa.Integer, nullable=False),
        sa.Column("week", sa.Integer, nullable=False),
        sa.Column("player_id", sa.String(20), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("pts", POINTS, nullable=False),
        sa.Column("is_final", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("season", "week", "player_id"),
    )


def downgrade() -> None:
    for t in (
        "stat_weeks",
        "price_history",
        "dividends",
        "trades",
        "holdings",
        "listings",
        "players",
        "users",
        "leagues",
    ):
        op.drop_table(t)
