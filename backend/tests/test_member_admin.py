import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import get_session
from app.engine.trading import execute_trade
from app.main import app
from app.models import Holding, Listing, Trade, User
from tests.conftest import make_listing, make_player


@pytest.fixture
def client(session, league):
    make_listing(session, league, make_player(session))  # 'cmc' @ $100
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def register(client, name):
    r = client.post(
        "/api/auth/register",
        json={"invite_code": "test", "username": name, "password": "hunter22"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def login(client, name):  # the shared cookie jar means the last auth call wins
    r = client.post("/api/auth/login", json={"username": name, "password": "hunter22"})
    assert r.status_code == 200, r.text


def test_members_list_shows_footprint(client, session):
    register(client, "ryan")  # first member bootstraps as commissioner
    bob = register(client, "bob")
    execute_trade(session, user_id=bob["user_id"], player_id="cmc", side="buy", shares=3)
    session.commit()
    login(client, "ryan")
    rows = client.get("/api/admin/members").json()["members"]
    by = {m["username"]: m for m in rows}
    assert by["ryan"]["is_commissioner"] and by["ryan"]["is_you"]
    assert by["bob"]["shares"] == 3 and by["bob"]["trades"] == 1
    assert not by["bob"]["is_commissioner"] and not by["bob"]["is_you"]


def test_remove_member_with_no_trades(client, session):
    register(client, "ryan")
    bob = register(client, "bob")
    login(client, "ryan")
    r = client.post("/api/admin/remove-member", json={"user_id": bob["user_id"]})
    assert r.status_code == 200, r.text
    assert r.json() == {"removed": "bob", "liquidated": False, "shares_returned": 0}
    assert session.get(User, bob["user_id"]) is None


def test_remove_member_with_shares_needs_liquidate_then_purges(client, session):
    register(client, "ryan")
    bob = register(client, "bob")
    execute_trade(session, user_id=bob["user_id"], player_id="cmc", side="buy", shares=5)
    session.commit()

    login(client, "ryan")
    # refuses without confirmation, leaves the member untouched
    r = client.post("/api/admin/remove-member", json={"user_id": bob["user_id"]})
    assert r.status_code == 409
    assert session.get(User, bob["user_id"]) is not None

    # confirmed: returns their shares to the float and purges the account
    r = client.post(
        "/api/admin/remove-member", json={"user_id": bob["user_id"], "liquidate": True}
    )
    assert r.status_code == 200, r.text
    assert r.json()["liquidated"] and r.json()["shares_returned"] == 5

    listing = session.scalar(select(Listing).where(Listing.player_id == "cmc"))
    assert listing.shares_outstanding == 0  # invariant: sum(holdings) == shares_outstanding
    assert session.get(User, bob["user_id"]) is None
    assert session.scalars(select(Holding).where(Holding.user_id == bob["user_id"])).all() == []
    assert session.scalars(select(Trade).where(Trade.user_id == bob["user_id"])).all() == []


def test_cannot_remove_self_or_unknown(client):
    ryan = register(client, "ryan")
    assert client.post("/api/admin/remove-member", json={"user_id": ryan["user_id"]}).status_code == 400
    assert client.post("/api/admin/remove-member", json={"user_id": 999999}).status_code == 404
