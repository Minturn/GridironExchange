from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth import get_session
from app.main import app
from tests.conftest import make_listing, make_player


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


def test_register_login_me_flow(client):
    me = register(client)
    assert me["username"] == "ryan"
    assert me["is_commissioner"] is True  # first member bootstraps as commissioner
    assert me["cash"] == 10000.0
    assert client.get("/api/auth/me").json()["username"] == "ryan"
    client.post("/api/auth/logout")
    # cookie cleared -> 401
    client.cookies.clear()
    assert client.get("/api/auth/me").status_code == 401
    r = client.post("/api/auth/login", json={"username": "ryan", "password": "hunter22"})
    assert r.status_code == 200
    assert client.get("/api/auth/me").json()["username"] == "ryan"


def test_bad_invite_and_wrong_password(client):
    assert (
        client.post(
            "/api/auth/register",
            json={"invite_code": "nope", "username": "x1", "password": "hunter22"},
        ).status_code
        == 400
    )
    register(client)
    client.cookies.clear()
    assert (
        client.post("/api/auth/login", json={"username": "ryan", "password": "wrong"}).status_code
        == 401
    )


def test_endpoints_require_auth(client):
    for path in ("/api/market", "/api/portfolio", "/api/leaderboard", "/api/feed"):
        assert client.get(path).status_code == 401


def test_quote_then_trade_matches(client):
    register(client)
    q = client.get("/api/quote", params={"player_id": "cmc", "side": "buy", "shares": 10}).json()
    assert q["ok"] is True
    assert q["gross"] == 1016.0 and q["fee"] == 10.16
    t = client.post("/api/trade", json={"player_id": "cmc", "side": "buy", "shares": 10}).json()
    assert t["total"] == q["total"]
    assert t["cash_after"] == 10000.0 - q["total"]
    market = client.get("/api/market").json()
    row = next(r for r in market if r["player_id"] == "cmc")
    assert row["your_shares"] == 10
    assert row["price"] == 103.2


def test_quote_flags_cap_and_cash(client):
    register(client)
    q = client.get("/api/quote", params={"player_id": "cmc", "side": "buy", "shares": 26}).json()
    assert q["ok"] is False and "cap" in q["reason"]
    q = client.get("/api/quote", params={"player_id": "cmc", "side": "sell", "shares": 1}).json()
    assert q["ok"] is False


def test_trade_rejection_maps_to_400(client):
    register(client)
    r = client.post("/api/trade", json={"player_id": "cmc", "side": "sell", "shares": 5})
    assert r.status_code == 400
    assert "hold" in r.json()["detail"]


def test_portfolio_pnl_and_leaderboard(client, session):
    register(client)
    client.post("/api/trade", json={"player_id": "cmc", "side": "buy", "shares": 10})
    p = client.get("/api/portfolio").json()
    h = p["holdings"][0]
    assert h["shares"] == 10
    assert h["avg_cost"] == pytest.approx(102.62)  # (1016 + 10.16) / 10
    assert p["net_worth"] == pytest.approx(p["cash"] + h["mark_value"])
    board = client.get("/api/leaderboard").json()
    assert board[0]["is_you"] is True and board[0]["rank"] == 1


def test_feed_shows_trades(client):
    register(client)
    client.post("/api/trade", json={"player_id": "cmc", "side": "buy", "shares": 3})
    feed = client.get("/api/feed").json()
    assert feed[0]["type"] == "trade"
    assert feed[0]["username"] == "ryan" and feed[0]["shares"] == 3


def test_admin_requires_commissioner(client):
    register(client)  # commissioner
    register(client, name="sal")  # session cookie now sal (not commissioner)
    r = client.post("/api/admin/dividends", json={"week": 1})
    assert r.status_code == 403


def test_admin_pause_blocks_trading_and_resume_unblocks(client):
    register(client)
    assert client.post("/api/admin/pause", json={"hours": 2}).status_code == 200
    r = client.post("/api/trade", json={"player_id": "cmc", "side": "buy", "shares": 1})
    assert r.status_code == 400 and "locked" in r.json()["detail"]
    client.post("/api/admin/resume")
    assert client.post("/api/trade", json={"player_id": "cmc", "side": "buy", "shares": 1}).status_code == 200


def test_admin_stat_fix_and_dividends(client, session):
    register(client)
    client.post("/api/trade", json={"player_id": "cmc", "side": "buy", "shares": 10})
    client.post("/api/admin/stat-fix", json={"player_id": "cmc", "week": 1, "pts": 20.0})
    r = client.post("/api/admin/dividends", json={"week": 1}).json()
    assert r["rows_posted"] == 1
    assert r["total_paid"] == 150.0  # 10 sh × 20 pts × 0.75 (pinned test knobs)
    p = client.get("/api/portfolio").json()
    assert p["holdings"][0]["dividends_earned"] == 150.0
