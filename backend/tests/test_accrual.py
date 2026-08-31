from decimal import Decimal

import pytest
from sqlalchemy import select

from app.engine import ledger
from app.engine.accrual import accrue_live, accrue_tick, cume_points, provisional_by_user, settle_week
from app.models import AccrualCursor, Dividend, DividendAccrual, Holding
from tests.conftest import make_listing, make_player, make_user

RATE = Decimal("0.75")  # conftest league dividend_multiplier


def hold(session, league, user, player, shares):
    session.add(Holding(league_id=league.id, user_id=user.id, player_id=player.id, shares=shares))
    session.commit()


def set_shares(session, league, user, player, shares):
    h = session.execute(
        select(Holding).where(Holding.user_id == user.id, Holding.player_id == player.id)
    ).scalar_one_or_none()
    if h is None:
        hold(session, league, user, player, shares)
    else:
        h.shares = shares
        session.commit()


@pytest.fixture
def setup(session, league):
    a = make_user(session, league, username="alice")
    b = make_user(session, league, username="bob")
    p = make_player(session)
    make_listing(session, league, p)
    return a, b, p


# ---------- core ----------

def test_tick_credits_current_holders_by_delta(session, league, setup):
    alice, _, p = setup
    hold(session, league, alice, p, 10)
    last = {}
    accrue_tick(session, league.id, 1, {p.id: Decimal("10")}, last, now=None)   # +10 pts
    accrue_tick(session, league.id, 1, {p.id: Decimal("25")}, last, now=None)   # +15 pts
    rows = session.execute(select(DividendAccrual)).scalars().all()
    # 10 shares × 10 × .75 = 75.00 ; then × 15 = 112.50
    assert sorted(r.amount for r in rows) == [Decimal("75.00"), Decimal("112.50")]
    assert provisional_by_user(session, league.id, 1)[alice.id] == Decimal("187.50")


def test_retried_poll_diffs_to_zero(session, league, setup):
    alice, _, p = setup
    hold(session, league, alice, p, 5)
    last = {}
    accrue_tick(session, league.id, 1, {p.id: Decimal("12")}, last)
    n = accrue_tick(session, league.id, 1, {p.id: Decimal("12")}, last)  # same cume
    assert n == 0
    assert len(session.execute(select(DividendAccrual)).scalars().all()) == 1


def test_settlement_pays_floors_and_is_idempotent(session, league, setup):
    alice, _, p = setup
    hold(session, league, alice, p, 4)
    cash0 = alice.cash
    last = {}
    accrue_tick(session, league.id, 1, {p.id: Decimal("20")}, last)   # 4×20×.75 = 60
    run = settle_week(session, league.id, 1)
    assert run.total_paid == Decimal("60.00")
    assert alice.cash == cash0 + Decimal("60.00")
    # a settled Dividend row now exists and drives cash-history
    assert session.execute(select(Dividend)).scalar_one().amount == Decimal("60.00")
    rerun = settle_week(session, league.id, 1)
    assert rerun.total_paid == Decimal("0.00")
    assert alice.cash == cash0 + Decimal("60.00")


def test_negative_week_floors_at_zero_never_claws_back(session, league, setup):
    alice, _, p = setup
    hold(session, league, alice, p, 10)
    cash0 = alice.cash
    accrue_tick(session, league.id, 1, {p.id: Decimal("-5")}, {})   # 2 INTs early: 10×-5×.75 = -37.50
    run = settle_week(session, league.id, 1)
    assert run.total_paid == Decimal("0.00")
    assert alice.cash == cash0                                       # not reduced
    assert session.execute(select(Dividend)).all() == []            # no negative dividend row


# ---------- different angle: ownership-over-time ----------

def test_ownership_over_time_split(session, league, setup):
    """Alice holds through the 1st half, sells to Bob, Bob earns the 2nd half."""
    alice, bob, p = setup
    hold(session, league, alice, p, 10)
    last = {}
    accrue_tick(session, league.id, 1, {p.id: Decimal("8")}, last)     # 1H: +8 → Alice 10×8×.75 = 60
    # trade at half: Alice -> Bob
    set_shares(session, league, alice, p, 0)
    set_shares(session, league, bob, p, 10)
    accrue_tick(session, league.id, 1, {p.id: Decimal("22")}, last)    # 2H: +14 → Bob 10×14×.75 = 105
    settle_week(session, league.id, 1)
    divs = {d.user_id: d.amount for d in session.execute(select(Dividend)).scalars()}
    assert divs[alice.id] == Decimal("60.00")
    assert divs[bob.id] == Decimal("105.00")


def test_front_run_earns_only_future_points(session, league, setup):
    """Bob buys AFTER the TD already scored — he earns nothing from it, only later points."""
    alice, bob, p = setup
    hold(session, league, alice, p, 10)
    last = {}
    accrue_tick(session, league.id, 1, {p.id: Decimal("10")}, last)    # TD happens, Alice holds -> 75
    # Bob front-runs in AFTER the score; Alice out
    set_shares(session, league, alice, p, 0)
    set_shares(session, league, bob, p, 10)
    accrue_tick(session, league.id, 1, {p.id: Decimal("10")}, last)    # no new points -> nobody accrues
    bob_rows = session.execute(
        select(DividendAccrual).where(DividendAccrual.user_id == bob.id)
    ).scalars().all()
    assert bob_rows == []                                             # stole nothing
    accrue_tick(session, league.id, 1, {p.id: Decimal("16")}, last)   # future +6 -> Bob 10×6×.75 = 45
    assert provisional_by_user(session, league.id, 1)[bob.id] == Decimal("45.00")


# ---------- ties back to the money ledger ----------

def test_settled_accrual_reconciles_with_cash_ledger(session, league, setup):
    alice, _, p = setup
    hold(session, league, alice, p, 6)
    start = league.rules.starting_cash
    accrue_tick(session, league.id, 1, {p.id: Decimal("18")}, {})     # 6×18×.75 = 81
    settle_week(session, league.id, 1)
    rec = ledger.reconcile(session, alice, start)
    assert rec.ok and rec.drift == Decimal("0.00")


# ---------- live path: raw stats + persisted, restart-safe cursor ----------

def test_accrue_live_scores_via_rubric_and_persists_cursor(session, league, setup):
    alice, _, p = setup
    hold(session, league, alice, p, 10)
    accrue_live(session, league.id, 1, {p.id: {"rec": 4, "rec_yd": 60, "rec_td": 1}})  # PPR 16
    assert provisional_by_user(session, league.id, 1)[alice.id] == Decimal("120.00")   # 10×16×.75
    assert session.execute(select(AccrualCursor)).scalar_one().cume == Decimal("16.00")


def test_accrue_live_idempotent_and_restart_safe(session, league, setup):
    alice, _, p = setup
    hold(session, league, alice, p, 10)
    raw = {p.id: {"rec": 4, "rec_yd": 60, "rec_td": 1}}  # 16 pts
    accrue_live(session, league.id, 1, raw)
    # a mid-game restart re-reads the cursor from the DB, so a re-poll diffs to zero
    assert accrue_live(session, league.id, 1, raw) == 0
    assert provisional_by_user(session, league.id, 1)[alice.id] == Decimal("120.00")  # NOT doubled
    # later points arrive -> only the new delta accrues
    accrue_live(session, league.id, 1, {p.id: {"rec": 6, "rec_yd": 90, "rec_td": 2}})  # 27, Δ11
    assert provisional_by_user(session, league.id, 1)[alice.id] == Decimal("202.50")  # 120 + 82.50


def test_accrue_live_skips_players_not_in_live_set(session, league, setup):
    alice, _, p = setup
    hold(session, league, alice, p, 10)
    assert accrue_live(session, league.id, 1, {p.id: {"rec": 9}}, only_players=set()) == 0


def test_cume_points_uses_league_rubric():
    # a WR raw line scored full PPR: 6 rec + 80 yds + 1 TD = 6 + 8 + 6 = 20.00
    out = cume_points({"wr1": {"rec": 6, "rec_yd": 80, "rec_td": 1}}, "ppr")
    assert out["wr1"] == Decimal("20.00")
    half = cume_points({"wr1": {"rec": 6, "rec_yd": 80, "rec_td": 1}}, "half_ppr")
    assert half["wr1"] == Decimal("17.00")
