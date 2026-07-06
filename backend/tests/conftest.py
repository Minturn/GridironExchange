from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.engine.amm import default_slope
from app.models import League, Listing, Player, User


@pytest.fixture
def session():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as s:
        yield s


@pytest.fixture
def league(session):
    # knobs pinned explicitly: engine tests assert exact arithmetic and must not
    # drift when the balance defaults (DEFAULT_RULES) get re-tuned
    lg = League(
        name="Test League",
        invite_code="test",
        season_year=2026,
        settings_json={
            "p0_factor": "0.50",
            "dividend_multiplier": "0.75",
            "fee_rate": "0.01",
            "share_cap": 25,
            "slope_pct": "0.08",
        },
    )
    session.add(lg)
    session.commit()
    return lg


def make_user(session, league, username="ryan", cash="10000.00", **kw):
    u = User(league_id=league.id, username=username, cash=Decimal(cash), **kw)
    session.add(u)
    session.commit()
    return u


def make_player(session, pid="cmc", name="Christian McCaffrey", pos="RB", team="SF"):
    p = Player(id=pid, name=name, pos=pos, team=team, status="Active")
    session.add(p)
    session.commit()
    return p


def make_listing(session, league, player, p0="100.00"):
    rules = league.rules
    p0 = Decimal(p0)
    l = Listing(
        league_id=league.id,
        player_id=player.id,
        p0=p0,
        slope=default_slope(p0, rules.slope_pct, rules.share_cap),
        shares_outstanding=0,
    )
    session.add(l)
    session.commit()
    return l
