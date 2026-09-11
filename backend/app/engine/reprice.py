"""Weekly rest-of-season repricing.

Re-anchor each listing's base price (p0) to its projected REMAINING production, so a
player's price tracks his outlook — an injury or a slump drags him down, a breakout
lifts him — instead of sitting frozen at a preseason full-season number.

Normalized on purpose: we rescale so the total base-price pool of the reprojected set
is preserved. That strips out the calendar (everyone having fewer games left doesn't
drain the whole league) and leaves only RELATIVE moves — the thing that should actually
reprice a player. Runs weekly, right after Tuesday's dividend settlement.

Safety: only players with a positive rest-of-season projection are re-anchored; anyone
without a projection (data gap, or out for the year) is left untouched rather than
wrongly floored — the injury badge + normal selling handle those.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.amm import default_slope, money
from app.models import League, Listing, Player


def rest_of_season(provider, season: int, from_week: int, through_week: int = 18) -> dict[str, Decimal]:
    """Sum each player's projected PPR points over the remaining weeks (from_week..18).
    Sleeper zeroes an out player's weekly projection, so this already reflects injuries."""
    totals: dict[str, Decimal] = {}
    for wk in range(from_week, through_week + 1):
        for pid, pts in provider.fetch_week_projections(season, wk).items():
            totals[pid] = totals.get(pid, Decimal("0")) + pts
    return totals


def reproject(session: Session, league: League, ros: dict[str, Decimal], reanchor: bool = True) -> dict:
    """Re-anchor listings to rest-of-season projections AND auto-list any projected
    player who isn't listed yet — both on one normalized price scale.

    Normalization (K = existing base pool ÷ existing ROS pool) holds the total steady, so
    only relative outlook moves prices, not the calendar. New listings are priced ROS × K,
    the same scale as the re-anchored set, and enter at 0 shares (nobody's net worth moves).

    reanchor=True (weekly): also re-price existing listings. reanchor=False (daily): only
    ADD new projected players at the current scale, leaving existing prices alone."""
    rules = league.rules
    listings = session.scalars(
        select(Listing).where(Listing.league_id == league.id)
    ).all()
    listed_ids = {l.player_id for l in listings}
    repriced = [(l, ros[l.player_id]) for l in listings if ros.get(l.player_id, Decimal("0")) > 0]
    if not repriced:
        return {"repriced": 0, "listed": 0, "reason": "no projections"}

    old_sum = sum((l.p0 for l, _ in repriced), Decimal("0"))
    ros_sum = sum((r for _, r in repriced), Decimal("0"))
    if ros_sum <= 0 or old_sum <= 0:
        return {"repriced": 0, "listed": 0, "reason": "zero totals"}

    k = old_sum / ros_sum  # normalization: hold the total base-price pool steady
    n = 0
    if reanchor:
        for l, r in repriced:
            new_p0 = max(rules.p0_floor, money(r * k))
            l.p0 = new_p0
            l.slope = default_slope(new_p0, rules.slope_pct, rules.share_cap)
            n += 1

    # auto-list: any projected player not yet listed (handcuffs, call-ups, breakouts),
    # priced on the same K scale so a later re-anchor doesn't jolt them.
    known = set(session.scalars(select(Player.id)).all())
    created = 0
    for pid, r in ros.items():
        if r > 0 and pid not in listed_ids and pid in known:
            p0 = max(rules.p0_floor, money(r * k))
            session.add(Listing(
                league_id=league.id, player_id=pid, p0=p0,
                slope=default_slope(p0, rules.slope_pct, rules.share_cap),
                shares_outstanding=0,
            ))
            created += 1
    session.commit()
    return {"repriced": n, "listed": created, "k": float(k)}
