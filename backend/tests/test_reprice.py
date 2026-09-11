from decimal import Decimal

import pytest
from sqlalchemy import select

from app.engine import reprice
from app.models import Listing
from tests.conftest import make_listing, make_player


class FakeProv:
    def __init__(self, weeks):
        self.weeks = weeks  # {week: {pid: Decimal}}

    def fetch_week_projections(self, season, week):
        return self.weeks.get(week, {})


def test_rest_of_season_sums_remaining_weeks():
    prov = FakeProv({2: {"a": Decimal("10"), "b": Decimal("5")}, 3: {"a": Decimal("8")}})
    ros = reprice.rest_of_season(prov, 2026, 2, through_week=3)
    assert ros == {"a": Decimal("18"), "b": Decimal("5")}


def test_reproject_normalizes_and_shifts_relative(session, league):
    la = make_listing(session, league, make_player(session, pid="a", name="A"), p0="100")
    lb = make_listing(session, league, make_player(session, pid="b", name="B"), p0="100")
    # pool = 200; A's outlook collapses to 1/4 of the pool, B rises to 3/4
    reprice.reproject(session, league, {"a": Decimal("50"), "b": Decimal("150")})
    session.refresh(la)
    session.refresh(lb)
    assert float(la.p0) + float(lb.p0) == pytest.approx(200.0, abs=0.02)  # pool preserved (no calendar decay)
    assert float(la.p0) == pytest.approx(50.0)   # busting player down
    assert float(lb.p0) == pytest.approx(150.0)  # healthy player up
    assert la.slope > 0 and lb.slope > la.slope  # slope rescaled with the new base


def test_reproject_leaves_unprojected_untouched(session, league):
    la = make_listing(session, league, make_player(session, pid="a", name="A"), p0="100")
    lb = make_listing(session, league, make_player(session, pid="b", name="B"), p0="80")
    reprice.reproject(session, league, {"a": Decimal("120")})  # b has no projection
    session.refresh(lb)
    assert float(lb.p0) == 80.0  # untouched, never wrongly floored


def _listing(session, league, pid):
    return session.scalar(
        select(Listing).where(Listing.league_id == league.id, Listing.player_id == pid)
    )


def test_reproject_auto_lists_projected_unlisted_player(session, league):
    make_listing(session, league, make_player(session, pid="a", name="A"), p0="100")
    make_player(session, pid="c", name="Handcuff")  # known player, NOT listed
    res = reprice.reproject(session, league, {"a": Decimal("100"), "c": Decimal("50")})
    assert res["listed"] == 1
    lc = _listing(session, league, "c")
    assert lc is not None and float(lc.p0) == pytest.approx(50.0)  # priced on the same K (=1.0) scale
    assert lc.shares_outstanding == 0


def test_daily_autolist_adds_without_reanchoring(session, league):
    la = make_listing(session, league, make_player(session, pid="a", name="A"), p0="100")
    make_player(session, pid="c", name="Handcuff")
    # a's ROS says 200 but reanchor=False must leave a's price at 100; c still gets listed
    res = reprice.reproject(session, league, {"a": Decimal("200"), "c": Decimal("50")}, reanchor=False)
    session.refresh(la)
    assert float(la.p0) == 100.0  # existing price untouched (K=0.5, but no reanchor)
    assert res["repriced"] == 0 and res["listed"] == 1
    assert float(_listing(session, league, "c").p0) == pytest.approx(25.0)  # 50 × K(0.5)
