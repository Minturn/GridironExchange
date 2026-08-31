from decimal import Decimal

from app.engine.dividends import post_week_dividends
from app.engine.fantasy_scoring import PRESETS, resolve_rubric, sleeper_to_rubric
from app.engine.trading import execute_trade
from app.models import StatWeek
from tests.conftest import make_listing, make_player, make_user

# conftest league: dividend_multiplier 0.75, default scoring_format = ppr


def _holder(session, league):
    u = make_user(session, league)
    p = make_player(session)
    make_listing(session, league, p)
    execute_trade(session, user_id=u.id, player_id=p.id, side="buy", shares=10)
    return u, p


def _final(session, league, p, week, raw=None, pts=Decimal("0")):
    session.add(StatWeek(season=league.season_year, week=week, player_id=p.id,
                         pts=pts, raw=raw, is_final=True))
    session.commit()


def test_dividends_score_ppr_from_raw(session, league):
    _u, p = _holder(session, league)
    # 5 rec + 50 yds + 1 TD -> PPR 5 + 5 + 6 = 16
    _final(session, league, p, 3, raw={"rec": 5, "rec_yd": 50, "rec_td": 1})
    run = post_week_dividends(session, league.id, 3)
    assert run.total_paid == Decimal("120.00")  # 10 × 16 × 0.75


def test_std_format_pays_less_than_ppr_on_same_stats(session, league):
    _u, p = _holder(session, league)
    league.settings_json = {**(league.settings_json or {}), "scoring_format": "std"}
    session.commit()
    _final(session, league, p, 4, raw={"rec": 5, "rec_yd": 50, "rec_td": 1})  # STD 11
    run = post_week_dividends(session, league.id, 4)
    assert run.total_paid == Decimal("82.50")  # 10 × 11 × 0.75


def test_rows_without_raw_fall_back_to_stored_pts(session, league):
    # manual stat-fix / pre-0005 data has no raw line
    _u, p = _holder(session, league)
    _final(session, league, p, 5, raw=None, pts=Decimal("20"))
    run = post_week_dividends(session, league.id, 5)
    assert run.total_paid == Decimal("150.00")  # 10 × 20 × 0.75


# ---------- imported custom rubric (Sleeper league onboarding) ----------

def test_sleeper_to_rubric_coerces_and_drops_zeros():
    ss = {"pass_td": 6, "rec": 1, "pass_yd": 0.04, "bonus_pass_yd_400": 0, "league_name": "x"}
    assert sleeper_to_rubric(ss) == {
        "pass_td": Decimal("6"), "rec": Decimal("1"), "pass_yd": Decimal("0.04"),
    }


def test_resolve_rubric_custom_beats_preset():
    assert resolve_rubric("ppr", {"pass_td": "6"}) == {"pass_td": Decimal("6")}
    assert resolve_rubric("ppr", None) is PRESETS["ppr"]


def test_imported_custom_rubric_drives_dividends(session, league):
    _u, p = _holder(session, league)
    # a Superflex-style import: 6-point passing TDs
    league.settings_json = {
        **(league.settings_json or {}),
        "scoring_format": "custom",
        "scoring_rubric": {"pass_yd": "0.04", "pass_td": "6"},
    }
    session.commit()
    _final(session, league, p, 6, raw={"pass_yd": 300, "pass_td": 3})  # 12 + 18 = 30
    run = post_week_dividends(session, league.id, 6)
    assert run.total_paid == Decimal("225.00")  # 10 × 30 × 0.75
