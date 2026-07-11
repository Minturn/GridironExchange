from decimal import Decimal

import pytest
from sqlalchemy import select

from app.engine.dividends import post_week_dividends
from app.engine.trading import execute_trade
from app.models import Dividend, StatWeek
from tests.conftest import make_listing, make_player, make_user


@pytest.fixture
def holding_setup(session, league):
    """ryan holds 10 CMC; sal holds nothing."""
    user = make_user(session, league)
    bystander = make_user(session, league, username="sal")
    player = make_player(session)
    make_listing(session, league, player)
    execute_trade(session, user_id=user.id, player_id=player.id, side="buy", shares=10)
    return user, bystander, player


def add_stat(session, league, player, week, pts, final=True):
    session.add(
        StatWeek(
            season=league.season_year,
            week=week,
            player_id=player.id,
            pts=Decimal(pts),
            is_final=final,
        )
    )
    session.commit()


def test_dividend_pays_pts_times_multiplier_per_share(session, league, holding_setup):
    user, bystander, player = holding_setup
    add_stat(session, league, player, week=5, pts="20.00")
    cash_before = user.cash
    run = post_week_dividends(session, league.id, week=5)
    # 10 shares × 20 pts × $0.75
    assert run.rows_posted == 1
    assert run.total_paid == Decimal("150.00")
    assert user.cash == cash_before + Decimal("150.00")
    assert bystander.cash == Decimal("10000.00")
    row = session.execute(select(Dividend)).scalar_one()
    assert (row.shares_held, row.pts, row.amount) == (10, Decimal("20.00"), Decimal("150.00"))


def test_rerunning_a_week_is_idempotent(session, league, holding_setup):
    user, _, player = holding_setup
    add_stat(session, league, player, week=5, pts="20.00")
    post_week_dividends(session, league.id, week=5)
    cash_after_first = user.cash
    rerun = post_week_dividends(session, league.id, week=5)
    assert rerun.rows_posted == 0
    assert rerun.total_paid == Decimal("0.00")
    assert user.cash == cash_after_first
    assert len(session.execute(select(Dividend)).scalars().all()) == 1


def test_non_final_stats_pay_nothing(session, league, holding_setup):
    user, _, player = holding_setup
    add_stat(session, league, player, week=5, pts="20.00", final=False)
    cash_before = user.cash
    run = post_week_dividends(session, league.id, week=5)
    assert run.rows_posted == 0
    assert user.cash == cash_before


def test_negative_week_clamps_to_zero_dollars(session, league, holding_setup):
    user, _, player = holding_setup
    add_stat(session, league, player, week=5, pts="-1.20")
    cash_before = user.cash
    run = post_week_dividends(session, league.id, week=5)
    assert run.rows_posted == 1  # row written → week marked processed for this holder
    assert run.total_paid == Decimal("0.00")
    assert user.cash == cash_before


def test_wrong_week_or_no_holdings_is_a_noop(session, league, holding_setup):
    _, _, player = holding_setup
    add_stat(session, league, player, week=6, pts="20.00")
    run = post_week_dividends(session, league.id, week=5)
    assert run.rows_posted == 0


def test_dividend_pays_kickoff_snapshot_not_late_buyers(session, league):
    """Record-date: the holder at kickoff earns the dividend; someone who buys the
    player AFTER kickoff (live trading, or the Tue 6:00-6:10 reopen gap) does not.
    This is the guard that makes live in-game trading safe."""
    from app.engine.dividends import snapshot_holdings
    from app.models import HoldingSnapshot

    early = make_user(session, league, username="early")
    late = make_user(session, league, username="late")
    player = make_player(session)
    make_listing(session, league, player)

    # `early` holds 10 at kickoff → snapshot the record date for week 5
    execute_trade(session, user_id=early.id, player_id=player.id, side="buy", shares=10)
    rows = snapshot_holdings(session, league.id, week=5, player_ids=[player.id])
    assert rows == 1

    # After kickoff: early dumps all, late scoops them up (the snipe we're preventing)
    execute_trade(session, user_id=early.id, player_id=player.id, side="sell", shares=10)
    execute_trade(session, user_id=late.id, player_id=player.id, side="buy", shares=10)

    add_stat(session, league, player, week=5, pts="20.00")
    run = post_week_dividends(session, league.id, week=5)

    divs = {
        d.user_id: d
        for d in session.execute(select(Dividend).where(Dividend.week == 5)).scalars()
    }
    assert early.id in divs, "kickoff holder must be paid"
    assert late.id not in divs, "post-kickoff buyer must NOT be paid"
    assert divs[early.id].shares_held == 10
    assert run.rows_posted == 1

    # idempotent: re-running the snapshot at the next poll doesn't overwrite the record
    assert snapshot_holdings(session, league.id, week=5, player_ids=[player.id]) == 0


def test_no_snapshot_falls_back_to_live_holdings(session, league, holding_setup):
    """Backward-compat: weeks with no snapshot (manual runs, no scheduler) pay live
    holdings exactly as before."""
    user, _, player = holding_setup
    add_stat(session, league, player, week=5, pts="20.00")
    run = post_week_dividends(session, league.id, week=5)
    assert run.rows_posted == 1
    assert run.total_paid > 0
