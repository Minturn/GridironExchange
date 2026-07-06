from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db import utcnow
from app.engine.trading import (
    BadOrder,
    CapExceeded,
    InsufficientCash,
    InsufficientShares,
    MarketLocked,
    execute_trade,
)
from app.models import PriceHistory, Trade
from tests.conftest import make_listing, make_player, make_user


@pytest.fixture
def setup(session, league):
    user = make_user(session, league)
    player = make_player(session)
    listing = make_listing(session, league, player)  # p0=100, slope=0.32, cap 25
    return user, player, listing


def test_buy_updates_cash_holding_outstanding_and_ledger(session, setup):
    user, player, listing = setup
    r = execute_trade(session, user_id=user.id, player_id=player.id, side="buy", shares=10)
    assert r.gross == Decimal("1016.00")
    assert r.fee == Decimal("10.16")
    assert user.cash == Decimal("8973.84")
    assert r.cash_after == user.cash
    assert listing.shares_outstanding == 10
    trade = session.execute(select(Trade)).scalar_one()
    assert (trade.side, trade.shares, trade.cash_after) == ("buy", 10, user.cash)
    tick = session.execute(select(PriceHistory)).scalar_one()
    assert tick.price == Decimal("103.20")


def test_sell_returns_along_the_curve(session, setup):
    user, player, _ = setup
    execute_trade(session, user_id=user.id, player_id=player.id, side="buy", shares=10)
    r = execute_trade(session, user_id=user.id, player_id=player.id, side="sell", shares=10)
    assert r.total == Decimal("1005.84")
    # round trip loses exactly the two fees
    assert user.cash == Decimal("10000.00") - Decimal("10.16") - Decimal("10.16")


def test_share_cap_enforced(session, setup):
    user, player, _ = setup
    with pytest.raises(CapExceeded):
        execute_trade(session, user_id=user.id, player_id=player.id, side="buy", shares=26)
    execute_trade(session, user_id=user.id, player_id=player.id, side="buy", shares=25)
    with pytest.raises(CapExceeded):
        execute_trade(session, user_id=user.id, player_id=player.id, side="buy", shares=1)


def test_insufficient_cash_rejected_before_any_mutation(session, league, setup):
    _, player, listing = setup
    broke = make_user(session, league, username="broke", cash="100.00")
    with pytest.raises(InsufficientCash):
        execute_trade(session, user_id=broke.id, player_id=player.id, side="buy", shares=10)
    session.rollback()
    assert broke.cash == Decimal("100.00")
    assert listing.shares_outstanding == 0


def test_cannot_sell_shares_you_do_not_hold(session, setup):
    user, player, _ = setup
    with pytest.raises(InsufficientShares):
        execute_trade(session, user_id=user.id, player_id=player.id, side="sell", shares=1)


def test_game_lock_blocks_and_expires(session, setup):
    user, player, listing = setup
    listing.locked_until = utcnow() + timedelta(hours=3)
    session.commit()
    with pytest.raises(MarketLocked):
        execute_trade(session, user_id=user.id, player_id=player.id, side="buy", shares=1)
    after = listing.locked_until + timedelta(minutes=1)
    r = execute_trade(
        session, user_id=user.id, player_id=player.id, side="buy", shares=1, now=after
    )
    assert r.shares == 1


def test_second_buyer_pays_more(session, league, setup):
    user1, player, _ = setup
    user2 = make_user(session, league, username="sal")
    r1 = execute_trade(session, user_id=user1.id, player_id=player.id, side="buy", shares=10)
    r2 = execute_trade(session, user_id=user2.id, player_id=player.id, side="buy", shares=10)
    assert r2.price_avg > r1.price_avg
    assert r2.price_avg == Decimal("104.80")


def test_rejects_unknown_player_and_bad_orders(session, setup):
    user, player, _ = setup
    with pytest.raises(BadOrder):
        execute_trade(session, user_id=user.id, player_id="nobody", side="buy", shares=1)
    with pytest.raises(BadOrder):
        execute_trade(session, user_id=user.id, player_id=player.id, side="hold", shares=1)
    with pytest.raises(BadOrder):
        execute_trade(session, user_id=user.id, player_id=player.id, side="buy", shares=0)


def test_cash_is_derivable_from_the_trade_ledger(session, setup):
    """SPEC §6.1: net worth must reconcile from ledger rows alone."""
    user, player, _ = setup
    for side, n in (("buy", 10), ("buy", 5), ("sell", 8), ("buy", 3), ("sell", 10)):
        execute_trade(session, user_id=user.id, player_id=player.id, side=side, shares=n)
    cash = Decimal("10000.00")
    for t in session.execute(select(Trade).order_by(Trade.id)).scalars():
        cash += (t.gross - t.fee) if t.side == "sell" else -(t.gross + t.fee)
        assert t.cash_after == cash
    assert user.cash == cash
