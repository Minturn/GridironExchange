"""Minimal API surface for the engine phase — enough to poke the market locally.

No auth yet (SPEC: invite-code auth lands Phase 5) — user_id rides in the request
body. Local dev only until then. Run:  uvicorn app.main:app --port 8200
"""
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import APP_VERSION
from app.db import SessionLocal, utcnow
from app.engine import amm
from app.engine.trading import TradeError, execute_trade
from app.models import Holding, Listing, Player, User

app = FastAPI(title="Gridiron Exchange", version=APP_VERSION)


def get_session():
    with SessionLocal() as session:
        yield session


@app.get("/health")
def health():
    return {"ok": True, "version": APP_VERSION}


@app.get("/market")
def market(league_id: int, session: Session = Depends(get_session)):
    rows = session.execute(
        select(Listing, Player)
        .join(Player, Listing.player_id == Player.id)
        .where(Listing.league_id == league_id)
    ).all()
    now = utcnow()
    return [
        {
            "player_id": p.id,
            "name": p.name,
            "team": p.team,
            "pos": p.pos,
            "price": float(amm.spot_price(l.p0, l.slope, l.shares_outstanding)),
            "p0": float(l.p0),
            "shares_outstanding": l.shares_outstanding,
            "locked": l.locked_until is not None and l.locked_until > now,
        }
        for l, p in rows
    ]


class TradeIn(BaseModel):
    user_id: int
    player_id: str
    side: str = Field(pattern="^(buy|sell)$")
    shares: int = Field(gt=0)


@app.post("/trade")
def trade(order: TradeIn, session: Session = Depends(get_session)):
    try:
        result = execute_trade(
            session,
            user_id=order.user_id,
            player_id=order.player_id,
            side=order.side,
            shares=order.shares,
        )
    except TradeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "trade_id": result.trade_id,
        "side": result.side,
        "shares": result.shares,
        "price_avg": float(result.price_avg),
        "fee": float(result.fee),
        "total": float(result.total),
        "cash_after": float(result.cash_after),
        "price_after": float(result.price_after),
    }


@app.get("/portfolio/{user_id}")
def portfolio(user_id: int, session: Session = Depends(get_session)):
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="unknown user")
    rows = session.execute(
        select(Holding, Listing, Player)
        .join(Listing, (Listing.player_id == Holding.player_id) & (Listing.league_id == Holding.league_id))
        .join(Player, Player.id == Holding.player_id)
        .where(Holding.user_id == user_id, Holding.shares > 0)
    ).all()
    holdings = []
    mark_total = Decimal("0.00")
    for h, l, p in rows:
        # mark-to-curve: what selling the whole position would gross (pre-fee)
        mark = amm.sell_gross(l.p0, l.slope, l.shares_outstanding, h.shares)
        mark_total += mark
        holdings.append(
            {
                "player_id": p.id,
                "name": p.name,
                "pos": p.pos,
                "shares": h.shares,
                "spot": float(amm.spot_price(l.p0, l.slope, l.shares_outstanding)),
                "mark_value": float(mark),
            }
        )
    return {
        "user_id": user.id,
        "username": user.username,
        "cash": float(user.cash),
        "holdings": holdings,
        "net_worth": float(amm.money(user.cash + mark_total)),
    }
