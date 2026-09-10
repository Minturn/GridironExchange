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
from app.models import League, Listing


def rest_of_season(provider, season: int, from_week: int, through_week: int = 18) -> dict[str, Decimal]:
    """Sum each player's projected PPR points over the remaining weeks (from_week..18).
    Sleeper zeroes an out player's weekly projection, so this already reflects injuries."""
    totals: dict[str, Decimal] = {}
    for wk in range(from_week, through_week + 1):
        for pid, pts in provider.fetch_week_projections(season, wk).items():
            totals[pid] = totals.get(pid, Decimal("0")) + pts
    return totals


def reproject(session: Session, league: League, ros: dict[str, Decimal]) -> dict:
    """Re-anchor listings to rest-of-season projections, normalized to preserve the
    reprojected set's total base price. Mutates listing.p0 (the live base) and rescales
    slope to match. Only positive-ROS listings move; the rest are left as-is."""
    rules = league.rules
    listings = session.scalars(
        select(Listing).where(Listing.league_id == league.id)
    ).all()
    repriced = [(l, ros[l.player_id]) for l in listings if ros.get(l.player_id, Decimal("0")) > 0]
    if not repriced:
        return {"repriced": 0, "reason": "no projections"}

    old_sum = sum((l.p0 for l, _ in repriced), Decimal("0"))
    ros_sum = sum((r for _, r in repriced), Decimal("0"))
    if ros_sum <= 0 or old_sum <= 0:
        return {"repriced": 0, "reason": "zero totals"}

    k = old_sum / ros_sum  # normalization: hold the total base-price pool steady
    n = 0
    for l, r in repriced:
        new_p0 = max(rules.p0_floor, money(r * k))
        l.p0 = new_p0
        l.slope = default_slope(new_p0, rules.slope_pct, rules.share_cap)
        n += 1
    session.commit()
    return {"repriced": n, "k": float(k)}
