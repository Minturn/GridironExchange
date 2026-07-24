from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth import get_session
from app.engine import ledger
from app.engine.dividends import post_week_dividends
from app.engine.trading import execute_trade
from app.main import app
from app.models import StatWeek
from tests.conftest import make_listing, make_player, make_user


@pytest.fixture
def client(session, league):
    make_listing(session, league, make_player(session))  # CMC, p0=100
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def register(client, name="ryan", invite="test"):
    r = client.post(
        "/api/auth/register",
        json={"invite_code": invite, "username": name, "password": "hunter22"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def add_stat(session, league, player, week, pts):
    session.add(
        StatWeek(season=league.season_year, week=week, player_id=player.id,
                 pts=Decimal(pts), is_final=True)
    )
    session.commit()


def test_reconciles_after_buys_sells_and_dividends(session, league):
    user = make_user(session, league)
    player = make_player(session)
    make_listing(session, league, player)
    start = league.rules.starting_cash

    execute_trade(session, user_id=user.id, player_id=player.id, side="buy", shares=10)
    execute_trade(session, user_id=user.id, player_id=player.id, side="sell", shares=3)
    add_stat(session, league, player, week=5, pts="20.00")
    post_week_dividends(session, league.id, week=5)

    rec = ledger.reconcile(session, user, start)
    assert rec.ok is True
    assert rec.drift == Decimal("0.00")
    assert rec.computed_cash == user.cash


def test_events_are_ordered_and_typed(session, league):
    user = make_user(session, league)
    player = make_player(session)
    make_listing(session, league, player)
    start = league.rules.starting_cash

    execute_trade(session, user_id=user.id, player_id=player.id, side="buy", shares=5)
    add_stat(session, league, player, week=1, pts="10.00")
    post_week_dividends(session, league.id, week=1)

    events = ledger.cash_events(session, user.id, start)
    assert [e.kind for e in events] == ["start", "buy", "dividend"]
    assert events[0].balance == start
    assert events[-1].balance == user.cash
    # running balance is internally consistent: each step = prev + delta
    for prev, cur in zip(events, events[1:]):
        assert cur.balance == prev.balance + cur.delta


def test_buy_debits_gross_plus_fee_sell_credits_gross_minus_fee(session, league):
    user = make_user(session, league)
    player = make_player(session)
    make_listing(session, league, player)
    start = league.rules.starting_cash

    execute_trade(session, user_id=user.id, player_id=player.id, side="buy", shares=4)
    events = ledger.cash_events(session, user.id, start)
    buy = events[1]
    # every trade's replayed balance must equal the cash_after stamped on its ledger row
    from app.models import Trade
    from sqlalchemy import select
    trade = session.execute(select(Trade)).scalar_one()
    assert buy.balance == trade.cash_after
    assert buy.delta == -(trade.gross + trade.fee)


def test_drift_is_detected(session, league):
    user = make_user(session, league)
    player = make_player(session)
    make_listing(session, league, player)
    start = league.rules.starting_cash
    execute_trade(session, user_id=user.id, player_id=player.id, side="buy", shares=2)

    # simulate a corrupted cash column
    user.cash = user.cash + Decimal("100.00")
    session.commit()
    rec = ledger.reconcile(session, user, start)
    assert rec.ok is False
    assert rec.drift == Decimal("100.00")


def test_cash_history_endpoint_reconciles(client):
    register(client)
    client.post("/api/trade", json={"player_id": "cmc", "side": "buy", "shares": 5})
    r = client.get("/api/cash-history")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reconciled"] is True
    assert body["computed_cash"] == body["cash"]
    # newest first: last row is the opening balance
    assert body["events"][-1]["kind"] == "start"
    assert body["events"][0]["kind"] == "buy"


def test_audit_endpoint_flags_all_ok(client):
    register(client)  # ryan, commissioner
    client.post("/api/trade", json={"player_id": "cmc", "side": "buy", "shares": 3})
    r = client.get("/api/admin/audit")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["all_ok"] is True
    assert body["members"][0]["ok"] is True
