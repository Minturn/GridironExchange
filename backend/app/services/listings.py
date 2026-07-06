"""Opening Bell: create listings from a projections snapshot (SPEC §3.1, §6).

Source-agnostic on purpose — pass {player_id: projected_season_pts} from Sleeper,
a FantasyPros CSV, or the backtest. Projections are snapshotted once; P0 never
re-prices from projections after the market opens.
"""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.amm import default_slope, money
from app.models import League, Listing, Player


def create_listings(
    session: Session, league: League, projections: dict[str, Decimal]
) -> int:
    rules = league.rules
    existing = set(
        session.execute(
            select(Listing.player_id).where(Listing.league_id == league.id)
        ).scalars()
    )
    known_players = set(session.execute(select(Player.id)).scalars())
    created = 0
    for player_id, season_pts in projections.items():
        if player_id in existing or player_id not in known_players:
            continue
        p0 = max(money(rules.p0_factor * season_pts), rules.p0_floor)
        session.add(
            Listing(
                league_id=league.id,
                player_id=player_id,
                p0=p0,
                slope=default_slope(p0, rules.slope_pct, rules.share_cap),
                shares_outstanding=0,
            )
        )
        created += 1
    session.commit()
    return created
