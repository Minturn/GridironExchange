from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import current_user, get_session
from app.config import APP_VERSION
from app.db import utcnow
from app.engine import amm, ledger, scoring
from app.engine.trading import TradeError, execute_trade
from app.models import Dividend, Holding, League, Listing, Player, PriceHistory, StatWeek, Trade, User

router = APIRouter(prefix="/api", tags=["market"])


def _spot(listing: Listing) -> Decimal:
    return amm.spot_price(listing.p0, listing.slope, listing.shares_outstanding)


@router.get("/market")
def market(user: User = Depends(current_user), session: Session = Depends(get_session)):
    rows = session.execute(
        select(Listing, Player)
        .join(Player, Listing.player_id == Player.id)
        .where(Listing.league_id == user.league_id)
    ).all()
    now = utcnow()

    # sparkline + week delta from price history (last 28 days, downsampled)
    since = now - timedelta(days=28)
    history: dict[str, list[tuple]] = defaultdict(list)
    for ph in session.execute(
        select(PriceHistory)
        .where(PriceHistory.league_id == user.league_id, PriceHistory.ts >= since)
        .order_by(PriceHistory.ts)
    ).scalars():
        history[ph.player_id].append(float(ph.price))

    mine = {
        h.player_id: h.shares
        for h in session.execute(
            select(Holding).where(Holding.user_id == user.id, Holding.shares > 0)
        ).scalars()
    }
    # last-final-week points → yield column
    latest_week = session.execute(
        select(func.max(StatWeek.week)).where(StatWeek.is_final.is_(True))
    ).scalar()
    last_pts = {}
    if latest_week:
        last_pts = {
            s.player_id: float(s.pts)
            for s in session.execute(
                select(StatWeek).where(StatWeek.week == latest_week, StatWeek.is_final.is_(True))
            ).scalars()
        }

    out = []
    for l, p in rows:
        price = float(_spot(l))
        series = history.get(p.id, [])
        if len(series) > 12:  # downsample for the row sparkline
            step = len(series) / 12
            series = [series[int(i * step)] for i in range(12)]
        base = series[0] if series else float(l.p0)
        out.append(
            {
                "player_id": p.id,
                "name": p.name,
                "team": p.team,
                "pos": p.pos,
                "price": price,
                "p0": float(l.p0),
                "delta_pct": (price - base) / base if base else 0.0,
                "spark": series or [float(l.p0), price],
                "last_wk_pts": last_pts.get(p.id, 0.0),
                "shares_outstanding": l.shares_outstanding,
                "your_shares": mine.get(p.id, 0),
                "locked": l.locked_until is not None and l.locked_until > now,
            }
        )
    out.sort(key=lambda r: -r["price"])
    return out


@router.get("/players/{player_id}")
def player_detail(
    player_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    listing = session.execute(
        select(Listing).where(
            Listing.league_id == user.league_id, Listing.player_id == player_id
        )
    ).scalar_one_or_none()
    player = session.get(Player, player_id)
    if listing is None or player is None:
        raise HTTPException(status_code=404, detail="not listed")
    now = utcnow()

    series = [
        {"ts": ph.ts.isoformat(), "price": float(ph.price)}
        for ph in session.execute(
            select(PriceHistory)
            .where(PriceHistory.league_id == user.league_id, PriceHistory.player_id == player_id)
            .order_by(PriceHistory.ts)
        ).scalars()
    ]
    if len(series) > 200:
        step = len(series) / 200
        series = [series[int(i * step)] for i in range(200)]

    holders = [
        {"username": u.username, "shares": h.shares}
        for h, u in session.execute(
            select(Holding, User)
            .join(User, Holding.user_id == User.id)
            .where(
                Holding.league_id == user.league_id,
                Holding.player_id == player_id,
                Holding.shares > 0,
            )
            .order_by(Holding.shares.desc())
        ).all()
    ]
    divs = [
        {"week": w, "per_share": float(amount)}
        for w, amount in session.execute(
            select(Dividend.week, func.max(Dividend.amount / Dividend.shares_held))
            .where(Dividend.league_id == user.league_id, Dividend.player_id == player_id)
            .group_by(Dividend.week)
            .order_by(Dividend.week)
        ).all()
    ]
    league = session.get(League, user.league_id)
    weeks = {
        s.week: float(s.pts)
        for s in session.execute(
            select(StatWeek).where(
                StatWeek.player_id == player_id,
                StatWeek.season == league.season_year,
                StatWeek.is_final.is_(True),
            )
        ).scalars()
    }
    mine = session.execute(
        select(Holding).where(Holding.user_id == user.id, Holding.player_id == player_id)
    ).scalar_one_or_none()
    return {
        "player_id": player.id,
        "name": player.name,
        "team": player.team,
        "pos": player.pos,
        "status": player.status,
        "price": float(_spot(listing)),
        "p0": float(listing.p0),
        "shares_outstanding": listing.shares_outstanding,
        "locked_until": listing.locked_until.isoformat() if listing.locked_until and listing.locked_until > now else None,
        "your_shares": mine.shares if mine else 0,
        "series": series,
        "holders": holders,
        "dividends": divs,
        "weekly_pts": weeks,
    }


@router.get("/quote")
def quote(
    player_id: str,
    side: str = Query(pattern="^(buy|sell)$"),
    shares: int = Query(gt=0, le=1000),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    listing = session.execute(
        select(Listing).where(
            Listing.league_id == user.league_id, Listing.player_id == player_id
        )
    ).scalar_one_or_none()
    if listing is None:
        raise HTTPException(status_code=404, detail="not listed")
    league = session.get(League, user.league_id)
    rules = league.rules
    fn = amm.quote_buy if side == "buy" else amm.quote_sell
    q = fn(listing.p0, listing.slope, listing.shares_outstanding, shares, rules.fee_rate)
    holding = session.execute(
        select(Holding).where(Holding.user_id == user.id, Holding.player_id == player_id)
    ).scalar_one_or_none()
    held = holding.shares if holding else 0
    ok, reason = True, None
    if side == "buy" and held + shares > rules.share_cap:
        ok, reason = False, f"cap is {rules.share_cap} shares/player (you hold {held})"
    elif side == "buy" and user.cash < q.total:
        ok, reason = False, f"costs ${q.total} — you have ${user.cash}"
    elif side == "sell" and held < shares:
        ok, reason = False, f"you hold {held} shares"
    return {
        "side": side,
        "shares": shares,
        "gross": float(q.gross),
        "fee": float(q.fee),
        "total": float(q.total),
        "price_avg": float(q.price_avg),
        "price_after": float(q.price_after),
        "ok": ok,
        "reason": reason,
    }


class TradeIn(BaseModel):
    player_id: str
    side: str = Field(pattern="^(buy|sell)$")
    shares: int = Field(gt=0, le=1000)


@router.post("/trade")
def trade(order: TradeIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    try:
        r = execute_trade(
            session,
            user_id=user.id,
            player_id=order.player_id,
            side=order.side,
            shares=order.shares,
        )
    except TradeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "trade_id": r.trade_id,
        "side": r.side,
        "shares": r.shares,
        "price_avg": float(r.price_avg),
        "fee": float(r.fee),
        "total": float(r.total),
        "cash_after": float(r.cash_after),
        "price_after": float(r.price_after),
    }


def _avg_cost_basis(session: Session, user_id: int) -> dict[str, Decimal]:
    """Average-cost basis per player from the immutable trade ledger."""
    basis: dict[str, tuple[int, Decimal]] = {}  # pid -> (qty, avg_cost)
    for t in session.execute(
        select(Trade).where(Trade.user_id == user_id).order_by(Trade.id)
    ).scalars():
        qty, avg = basis.get(t.player_id, (0, Decimal("0")))
        if t.side == "buy":
            new_qty = qty + t.shares
            avg = ((avg * qty) + t.gross + t.fee) / new_qty
            basis[t.player_id] = (new_qty, avg)
        else:
            basis[t.player_id] = (qty - t.shares, avg)
    return {pid: avg for pid, (qty, avg) in basis.items() if qty > 0}


@router.get("/portfolio")
def portfolio(user: User = Depends(current_user), session: Session = Depends(get_session)):
    rows = session.execute(
        select(Holding, Listing, Player)
        .join(
            Listing,
            (Listing.player_id == Holding.player_id)
            & (Listing.league_id == Holding.league_id),
        )
        .join(Player, Player.id == Holding.player_id)
        .where(Holding.user_id == user.id, Holding.shares > 0)
    ).all()
    basis = _avg_cost_basis(session, user.id)
    div_total = {
        pid: float(total)
        for pid, total in session.execute(
            select(Dividend.player_id, func.sum(Dividend.amount))
            .where(Dividend.user_id == user.id)
            .group_by(Dividend.player_id)
        ).all()
    }
    holdings = []
    mark_total = Decimal("0.00")
    for h, l, p in rows:
        mark = amm.sell_gross(l.p0, l.slope, l.shares_outstanding, h.shares)
        mark_total += mark
        avg = basis.get(p.id)
        holdings.append(
            {
                "player_id": p.id,
                "name": p.name,
                "team": p.team,
                "pos": p.pos,
                "shares": h.shares,
                "spot": float(_spot(l)),
                "mark_value": float(mark),
                "avg_cost": float(amm.money(avg)) if avg else None,
                "pnl": float(amm.money(mark - avg * h.shares)) if avg else None,
                "dividends_earned": div_total.get(p.id, 0.0),
            }
        )
    holdings.sort(key=lambda r: -r["mark_value"])
    return {
        "username": user.username,
        "cash": float(user.cash),
        "holdings": holdings,
        "net_worth": float(amm.money(user.cash + mark_total)),
    }


@router.get("/cash-history")
def cash_history(user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Your money, event by event: opening balance, every buy/sell, every dividend,
    with the running cash after each. `reconciled` is False if replaying the ledgers
    doesn't reproduce your stored cash — the personal-scope version of the audit."""
    league = session.get(League, user.league_id)
    starting = league.rules.starting_cash
    events = ledger.cash_events(session, user.id, starting)
    computed = events[-1].balance
    names = {p.id: p.name for p in session.execute(select(Player)).scalars()}
    out = [
        {
            "ts": e.ts.isoformat() if e.ts else None,
            "kind": e.kind,
            "delta": float(e.delta),
            "balance": float(e.balance),
            "player_id": e.player_id,
            "player_name": names.get(e.player_id) if e.player_id else None,
            "shares": e.shares,
            "week": e.week,
            "fee": float(e.fee) if e.fee is not None else None,
        }
        for e in events
    ]
    out.reverse()  # newest first for display
    return {
        "username": user.username,
        "starting_cash": float(starting),
        "cash": float(user.cash),
        "computed_cash": float(computed),
        "reconciled": amm.money(user.cash - computed) == Decimal("0.00"),
        "events": out,
    }


@router.get("/manager/{username}")
def manager(username: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Any manager's roster, visible to everyone in the same league (rosters are
    public — that's the whole point of a league). Read-only view of their holdings."""
    target = session.execute(
        select(User).where(User.league_id == user.league_id, User.username == username)
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="no such manager in your league")
    rows = session.execute(
        select(Holding, Listing, Player)
        .join(
            Listing,
            (Listing.player_id == Holding.player_id) & (Listing.league_id == Holding.league_id),
        )
        .join(Player, Player.id == Holding.player_id)
        .where(Holding.user_id == target.id, Holding.shares > 0)
    ).all()
    holdings = []
    mark_total = Decimal("0.00")
    for h, l, p in rows:
        mark = amm.sell_gross(l.p0, l.slope, l.shares_outstanding, h.shares)
        mark_total += mark
        holdings.append(
            {
                "player_id": p.id,
                "name": p.name,
                "team": p.team,
                "pos": p.pos,
                "shares": h.shares,
                "spot": float(amm.spot_price(l.p0, l.slope, l.shares_outstanding)),
                "mark_value": float(mark),
            }
        )
    holdings.sort(key=lambda r: -r["mark_value"])
    league = session.get(League, user.league_id)
    rules = league.rules
    starters: list[str] = []
    if rules.scoring_mode == scoring.LINEUP:
        held = [{"id": p.id, "pos": p.pos, "weight": float(l.p0)} for h, l, p in rows]
        starters = sorted(scoring.effective_starters(held, rules.lineup_slots, target.lineup_json))
    return {
        "username": target.username,
        "is_you": target.id == user.id,
        "cash": float(target.cash),
        "scoring_mode": rules.scoring_mode,
        "starters": starters,
        "holdings": holdings,
        "net_worth": float(amm.money(target.cash + mark_total)),
    }


@router.get("/leaderboard")
def leaderboard(user: User = Depends(current_user), session: Session = Depends(get_session)):
    users = session.execute(select(User).where(User.league_id == user.league_id)).scalars().all()
    listings = {
        l.player_id: l
        for l in session.execute(
            select(Listing).where(Listing.league_id == user.league_id)
        ).scalars()
    }
    holdings = session.execute(
        select(Holding).where(Holding.league_id == user.league_id, Holding.shares > 0)
    ).scalars().all()
    by_user: dict[int, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for h in holdings:
        l = listings.get(h.player_id)
        if l:
            by_user[h.user_id] += amm.sell_gross(l.p0, l.slope, l.shares_outstanding, h.shares)
    board = [
        {
            "username": u.username,
            "cash": float(u.cash),
            "net_worth": float(amm.money(u.cash + by_user[u.id])),
            "is_you": u.id == user.id,
        }
        for u in users
    ]
    board.sort(key=lambda r: -r["net_worth"])
    for i, row in enumerate(board):
        row["rank"] = i + 1
    return board


@router.get("/feed")
def feed(
    limit: int = Query(default=50, le=200),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    events = []
    trades = session.execute(
        select(Trade, User.username, Player.name)
        .join(User, Trade.user_id == User.id)
        .join(Player, Trade.player_id == Player.id)
        .where(Trade.league_id == user.league_id)
        .order_by(Trade.id.desc())
        .limit(limit)
    ).all()
    for t, username, player_name in trades:
        events.append(
            {
                "type": "trade",
                "ts": t.ts.isoformat(),
                "username": username,
                "player_id": t.player_id,
                "player_name": player_name,
                "side": t.side,
                "shares": t.shares,
                "price_avg": float(t.price_avg),
            }
        )
    div_weeks = session.execute(
        select(Dividend.week, func.sum(Dividend.amount), func.max(Dividend.ts))
        .where(Dividend.league_id == user.league_id)
        .group_by(Dividend.week)
        .order_by(Dividend.week.desc())
        .limit(8)
    ).all()
    for week, total, ts in div_weeks:
        events.append(
            {
                "type": "dividends",
                "ts": ts.isoformat(),
                "week": week,
                "total": float(total),
            }
        )
    events.sort(key=lambda e: e["ts"], reverse=True)
    return events[:limit]


def _held_with_pos(session: Session, user: User):
    """(Holding, Listing, Player) rows for a user's live positions."""
    return session.execute(
        select(Holding, Listing, Player)
        .join(
            Listing,
            (Listing.player_id == Holding.player_id) & (Listing.league_id == Holding.league_id),
        )
        .join(Player, Player.id == Holding.player_id)
        .where(Holding.user_id == user.id, Holding.shares > 0)
    ).all()


@router.get("/lineup")
def get_lineup(user: User = Depends(current_user), session: Session = Depends(get_session)):
    league = session.get(League, user.league_id)
    rules = league.rules
    rows = _held_with_pos(session, user)
    held = [
        {"player_id": p.id, "name": p.name, "pos": p.pos, "team": p.team, "shares": h.shares}
        for h, l, p in rows
    ]
    calc = [{"id": p.id, "pos": p.pos, "weight": float(l.p0)} for h, l, p in rows]
    current = scoring.effective_starters(calc, rules.lineup_slots, user.lineup_json)
    return {
        "mode": rules.scoring_mode,
        "slots": rules.lineup_slots,
        "slot_keys": scoring.slot_keys(rules.lineup_slots),
        "flex_positions": sorted(scoring.FLEX_POSITIONS),
        "held": held,
        "saved": user.lineup_json,
        "current": sorted(current),
    }


class LineupIn(BaseModel):
    player_ids: list[str]


@router.post("/lineup")
def set_lineup(body: LineupIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    league = session.get(League, user.league_id)
    rules = league.rules
    pos_map = {p.id: p.pos for h, l, p in _held_with_pos(session, user)}
    if any(pid not in pos_map for pid in body.player_ids):
        raise HTTPException(status_code=400, detail="you can only start players you hold")
    chosen = [{"id": pid, "pos": pos_map[pid]} for pid in body.player_ids]
    if not scoring.lineup_is_valid(chosen, rules.lineup_slots):
        raise HTTPException(status_code=400, detail="that lineup doesn’t fit the slots")
    user.lineup_json = list(body.player_ids)
    session.commit()
    return {"saved": user.lineup_json}


@router.get("/state")
def state(user: User = Depends(current_user), session: Session = Depends(get_session)):
    league = session.get(League, user.league_id)
    rules = league.rules
    last_final = session.execute(
        select(func.max(StatWeek.week)).where(
            StatWeek.season == league.season_year, StatWeek.is_final.is_(True)
        )
    ).scalar()
    opens_at_raw = (league.settings_json or {}).get("market_opens_at")
    market_open = True
    opens_at_out = None
    if opens_at_raw:
        market_open = datetime.fromisoformat(opens_at_raw) <= utcnow()
        if not market_open:
            opens_at_out = opens_at_raw + "Z"  # stored naive UTC → mark it UTC for JS
    return {
        "season": league.season_year,
        "league_name": league.name,
        "last_final_week": last_final or 0,
        "current_week": min((last_final or 0) + 1, 18),
        "market_open": market_open,
        "market_opens_at": opens_at_out,
        "scoring_mode": rules.scoring_mode,
        "dividend_multiplier": float(rules.dividend_multiplier),
        "in_game_trading": rules.in_game_trading,
        "lineup_slots": rules.lineup_slots,
        "version": APP_VERSION,
    }
