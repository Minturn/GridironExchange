from decimal import Decimal

from app.engine import scoring
from app.engine.dividends import post_week_dividends
from app.engine.trading import execute_trade
from app.models import StatWeek
from tests.conftest import make_listing, make_player, make_user


# ---------- pure scoring helpers ----------
def test_position_factor_scales_qb_down_te_up():
    assert scoring.position_factor("QB") < 1
    assert scoring.position_factor("TE") > 1
    assert scoring.position_factor("K") == Decimal("1.00")


def test_lineup_valid_rejects_too_many_qbs():
    slots = {"QB": 1, "RB": 2, "WR": 2, "FLEX": 1}
    assert scoring.lineup_is_valid([{"id": "a", "pos": "QB"}], slots)
    assert not scoring.lineup_is_valid(
        [{"id": "a", "pos": "QB"}, {"id": "b", "pos": "QB"}], slots
    )


def test_flex_absorbs_one_extra_rb():
    slots = {"QB": 1, "RB": 2, "WR": 2, "FLEX": 1}
    assert scoring.lineup_is_valid([{"id": f"r{i}", "pos": "RB"} for i in range(3)], slots)
    assert not scoring.lineup_is_valid([{"id": f"r{i}", "pos": "RB"} for i in range(4)], slots)


def test_autofill_picks_best_by_weight():
    slots = {"QB": 1, "RB": 1, "FLEX": 1}
    held = [
        {"id": "qb1", "pos": "QB", "weight": 300},
        {"id": "rb1", "pos": "RB", "weight": 200},
        {"id": "rb2", "pos": "RB", "weight": 150},  # → FLEX
        {"id": "rb3", "pos": "RB", "weight": 100},  # benched
    ]
    assert scoring.autofill(held, slots) == {"qb1", "rb1", "rb2"}


# ---------- dividend engine per mode ----------
def _mode(session, league, mode, slots=None):
    s = dict(league.settings_json or {})
    s["scoring_mode"] = mode
    if slots:
        s["lineup_slots"] = slots
    league.settings_json = s
    session.commit()


def _stat(session, league, pid, week, pts):
    session.add(
        StatWeek(season=league.season_year, week=week, player_id=pid, pts=Decimal(pts), is_final=True)
    )
    session.commit()


def test_relative_mode_scales_qb_dividend(session, league):
    _mode(session, league, "relative")
    user = make_user(session, league)
    qb = make_player(session, pid="allen", name="Josh Allen", pos="QB", team="BUF")
    make_listing(session, league, qb, p0="300.00")
    execute_trade(session, user_id=user.id, player_id="allen", side="buy", shares=5)
    _stat(session, league, "allen", 1, "20.00")
    run = post_week_dividends(session, league.id, 1)
    # 5 sh × 20 pts × 0.75 mult × 0.80 QB factor = 60.00 (vs 75.00 in market mode)
    assert run.total_paid == Decimal("60.00")


def test_lineup_mode_benches_the_second_qb(session, league):
    _mode(session, league, "lineup", {"QB": 1, "RB": 1})
    user = make_user(session, league)
    for pid, pos in (("allen", "QB"), ("burrow", "QB"), ("cmc", "RB")):
        make_listing(session, league, make_player(session, pid=pid, name=pid, pos=pos), p0="100.00")
        execute_trade(session, user_id=user.id, player_id=pid, side="buy", shares=5)
        _stat(session, league, pid, 1, "20.00")
    run = post_week_dividends(session, league.id, 1)
    # only 1 QB + 1 RB start → 2 players pay; the 2nd QB is benched
    assert run.rows_posted == 2
    assert run.total_paid == Decimal("150.00")  # 2 × 5 × 20 × 0.75


def test_lineup_respects_a_saved_choice(session, league):
    _mode(session, league, "lineup", {"QB": 1})
    user = make_user(session, league)
    make_listing(session, league, make_player(session, pid="allen", name="Allen", pos="QB"), p0="300.00")
    make_listing(session, league, make_player(session, pid="burrow", name="Burrow", pos="QB"), p0="100.00")
    execute_trade(session, user_id=user.id, player_id="allen", side="buy", shares=5)
    execute_trade(session, user_id=user.id, player_id="burrow", side="buy", shares=5)
    # auto would start Allen (higher p0); manager overrides to Burrow
    user.lineup_json = ["burrow"]
    session.commit()
    _stat(session, league, "allen", 1, "30.00")
    _stat(session, league, "burrow", 1, "10.00")
    run = post_week_dividends(session, league.id, 1)
    assert run.rows_posted == 1
    assert run.total_paid == Decimal("37.50")  # only Burrow: 5 × 10 × 0.75
