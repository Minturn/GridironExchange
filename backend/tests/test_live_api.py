import pytest
from fastapi.testclient import TestClient

from app.auth import get_session
from app.main import app
from tests.conftest import make_listing, make_player


@pytest.fixture
def client(session, league):
    make_listing(session, league, make_player(session))
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


def test_state_exposes_scoring_format_and_dividend_mode(client):
    register(client)
    s = client.get("/api/state").json()
    assert s["scoring_format"] == "ppr"
    assert s["dividend_mode"] == "snapshot"


def test_commissioner_sets_format_and_mode(client):
    register(client)  # first member bootstraps as commissioner
    assert client.post("/api/admin/scoring-format", json={"fmt": "half_ppr"}).json()["scoring_format"] == "half_ppr"
    assert client.post("/api/admin/dividend-mode", json={"mode": "accrual"}).json()["dividend_mode"] == "accrual"
    s = client.get("/api/state").json()
    assert s["scoring_format"] == "half_ppr" and s["dividend_mode"] == "accrual"


def test_bad_value_422_and_non_commissioner_403(client):
    register(client, name="ryan")  # commissioner
    assert client.post("/api/admin/scoring-format", json={"fmt": "bogus"}).status_code == 422
    client.post("/api/auth/logout")
    client.cookies.clear()
    register(client, name="sal")  # second member — not commissioner
    assert client.post("/api/admin/dividend-mode", json={"mode": "accrual"}).status_code == 403


def test_live_endpoint_shape_with_no_games(client):
    register(client)
    live = client.get("/api/live").json()
    assert live["dividend_mode"] == "snapshot"
    assert live["your_paycheck"] == 0.0
    assert live["holdings"] == []
    assert any(r["is_you"] for r in live["board"])
