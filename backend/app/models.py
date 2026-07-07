"""Schema per SPEC.md §7.

Product-proofing rule (SPEC §11): every league-scoped table carries league_id from
migration 1, even though the pilot has exactly one league. `players` and `stat_weeks`
are global NFL facts and deliberately have no league_id.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow

MONEY = Numeric(12, 2)
POINTS = Numeric(7, 2)
SLOPE = Numeric(12, 6)

# Engine knobs live in leagues.settings_json so each league can have its own economy
# (SPEC §11). Values LOCKED by the Phase 2 backtest vs. the real 2025 season —
# see docs/balance.md before touching them. Stored as strings → Decimal so JSON
# round-trips stay exact.
DEFAULT_RULES = {
    "p0_factor": "1.00",        # P0 = p0_factor × projected season pts
    "p0_floor": "5.00",         # deep-bench price floor
    "dividend_multiplier": "0.30",  # $/fantasy-point/share, weekly
    "fee_rate": "0.01",         # on every trade, burned
    "share_cap": 25,            # max shares per member per player
    "slope_pct": "0.12",        # one member maxing the cap moves price ~+12%
    "starting_cash": "10000.00",
    # scoring: "market" (raw), "relative" (position-normalized), or "lineup"
    # (only starters score). Commissioner-selectable. See app/engine/scoring.py.
    "scoring_mode": "market",
    "lineup_slots": {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1},
}


@dataclass(frozen=True)
class LeagueRules:
    p0_factor: Decimal
    p0_floor: Decimal
    dividend_multiplier: Decimal
    fee_rate: Decimal
    share_cap: int
    slope_pct: Decimal
    starting_cash: Decimal
    scoring_mode: str
    lineup_slots: dict


class League(Base):
    __tablename__ = "leagues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    invite_code: Mapped[str] = mapped_column(String(40), unique=True)
    season_year: Mapped[int] = mapped_column(Integer)
    settings_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    users: Mapped[list["User"]] = relationship(back_populates="league")

    @property
    def rules(self) -> LeagueRules:
        raw = {**DEFAULT_RULES, **(self.settings_json or {})}
        return LeagueRules(
            p0_factor=Decimal(str(raw["p0_factor"])),
            p0_floor=Decimal(str(raw["p0_floor"])),
            dividend_multiplier=Decimal(str(raw["dividend_multiplier"])),
            fee_rate=Decimal(str(raw["fee_rate"])),
            share_cap=int(raw["share_cap"]),
            slope_pct=Decimal(str(raw["slope_pct"])),
            starting_cash=Decimal(str(raw["starting_cash"])),
            scoring_mode=str(raw.get("scoring_mode") or "market"),
            lineup_slots=dict(raw.get("lineup_slots") or DEFAULT_RULES["lineup_slots"]),
        )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("league_id", "username"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    username: Mapped[str] = mapped_column(String(40))
    pw_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)  # auth lands Phase 5
    is_commissioner: Mapped[bool] = mapped_column(Boolean, default=False)
    cash: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    # lineup mode: list of player_ids the manager has set as starters (null = auto)
    lineup_json: Mapped[list | None] = mapped_column(JSON, nullable=True)

    league: Mapped[League] = relationship(back_populates="users")


class Player(Base):
    """Global NFL fact, keyed by the Sleeper player id."""

    __tablename__ = "players"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    team: Mapped[str | None] = mapped_column(String(4), nullable=True)
    pos: Mapped[str] = mapped_column(String(4))
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bye_week: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (UniqueConstraint("league_id", "player_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"))
    p0: Mapped[Decimal] = mapped_column(MONEY)
    slope: Mapped[Decimal] = mapped_column(SLOPE)
    shares_outstanding: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    player: Mapped[Player] = relationship()


class Holding(Base):
    __tablename__ = "holdings"
    __table_args__ = (UniqueConstraint("user_id", "player_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"))
    shares: Mapped[int] = mapped_column(Integer, default=0)


class Trade(Base):
    """Immutable ledger row (SPEC §6.1) — net worth must be derivable from these alone."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"))
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    side: Mapped[str] = mapped_column(String(4))  # buy | sell
    shares: Mapped[int] = mapped_column(Integer)
    price_avg: Mapped[Decimal] = mapped_column(MONEY)
    gross: Mapped[Decimal] = mapped_column(MONEY)
    fee: Mapped[Decimal] = mapped_column(MONEY)
    cash_after: Mapped[Decimal] = mapped_column(MONEY)


class Dividend(Base):
    """Immutable ledger row. Unique key = the idempotence guard for the Tuesday run."""

    __tablename__ = "dividends"
    __table_args__ = (UniqueConstraint("league_id", "week", "player_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    week: Mapped[int] = mapped_column(Integer)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    shares_held: Mapped[int] = mapped_column(Integer)
    pts: Mapped[Decimal] = mapped_column(POINTS)
    amount: Mapped[Decimal] = mapped_column(MONEY)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"))
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    price: Mapped[Decimal] = mapped_column(MONEY)


class StatWeek(Base):
    """Global NFL fact: one player's fantasy points for one week."""

    __tablename__ = "stat_weeks"
    __table_args__ = (UniqueConstraint("season", "week", "player_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    season: Mapped[int] = mapped_column(Integer)
    week: Mapped[int] = mapped_column(Integer)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"))
    pts: Mapped[Decimal] = mapped_column(POINTS)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
