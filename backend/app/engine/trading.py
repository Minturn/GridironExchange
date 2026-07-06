"""Trade execution (SPEC §3.4, §6.1).

Invariants enforced here, in one place:
- serialized per player: the listing row is locked (SELECT … FOR UPDATE on Postgres;
  SQLite serializes at the connection level anyway) so concurrent buys both pay
  correct curve prices;
- cash ≥ 0 always — buys validate against the full quoted cost including fee;
- per-player share cap; game locks; no selling shares you don't hold;
- every execution writes an immutable Trade ledger row + a PriceHistory point.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.engine import amm
from app.models import Holding, League, Listing, PriceHistory, Trade, User


class TradeError(Exception):
    """Base for all order rejections — message is user-facing."""


class BadOrder(TradeError):
    pass


class MarketLocked(TradeError):
    pass


class InsufficientCash(TradeError):
    pass


class InsufficientShares(TradeError):
    pass


class CapExceeded(TradeError):
    pass


@dataclass(frozen=True)
class TradeResult:
    trade_id: int
    side: str
    shares: int
    price_avg: Decimal
    gross: Decimal
    fee: Decimal
    total: Decimal
    cash_after: Decimal
    price_after: Decimal


def execute_trade(
    session: Session,
    *,
    user_id: int,
    player_id: str,
    side: str,
    shares: int,
    now: datetime | None = None,
) -> TradeResult:
    if side not in ("buy", "sell"):
        raise BadOrder(f"side must be buy or sell, got {side!r}")
    if not isinstance(shares, int) or shares <= 0:
        raise BadOrder("shares must be a positive whole number")

    user = session.get(User, user_id)
    if user is None:
        raise BadOrder("unknown user")
    league = session.get(League, user.league_id)
    rules = league.rules
    now = now or utcnow()

    listing = session.execute(
        select(Listing)
        .where(Listing.league_id == league.id, Listing.player_id == player_id)
        .with_for_update()
    ).scalar_one_or_none()
    if listing is None:
        raise BadOrder("player is not listed in this league")
    if listing.locked_until is not None and listing.locked_until > now:
        raise MarketLocked(f"trading locked until {listing.locked_until:%a %H:%M} UTC (game in progress)")

    holding = session.execute(
        select(Holding).where(Holding.user_id == user.id, Holding.player_id == player_id)
    ).scalar_one_or_none()
    if holding is None:
        holding = Holding(league_id=league.id, user_id=user.id, player_id=player_id, shares=0)
        session.add(holding)

    s = listing.shares_outstanding
    if side == "buy":
        if holding.shares + shares > rules.share_cap:
            raise CapExceeded(
                f"cap is {rules.share_cap} shares/player — you hold {holding.shares}"
            )
        quote = amm.quote_buy(listing.p0, listing.slope, s, shares, rules.fee_rate)
        if user.cash < quote.total:
            raise InsufficientCash(f"order costs ${quote.total} — you have ${user.cash}")
        user.cash = amm.money(user.cash - quote.total)
        holding.shares += shares
        listing.shares_outstanding = s + shares
    else:
        if holding.shares < shares:
            raise InsufficientShares(f"you hold {holding.shares} shares")
        quote = amm.quote_sell(listing.p0, listing.slope, s, shares, rules.fee_rate)
        user.cash = amm.money(user.cash + quote.total)
        holding.shares -= shares
        listing.shares_outstanding = s - shares

    trade = Trade(
        league_id=league.id,
        user_id=user.id,
        player_id=player_id,
        ts=now,
        side=side,
        shares=shares,
        price_avg=quote.price_avg,
        gross=quote.gross,
        fee=quote.fee,
        cash_after=user.cash,
    )
    session.add(trade)
    session.add(
        PriceHistory(league_id=league.id, player_id=player_id, ts=now, price=quote.price_after)
    )
    session.commit()

    return TradeResult(
        trade_id=trade.id,
        side=side,
        shares=shares,
        price_avg=quote.price_avg,
        gross=quote.gross,
        fee=quote.fee,
        total=quote.total,
        cash_after=user.cash,
        price_after=quote.price_after,
    )
