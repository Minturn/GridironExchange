from decimal import Decimal

import pytest

from app.engine import reprice
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
