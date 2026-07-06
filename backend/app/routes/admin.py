"""Commissioner tools — everything here requires is_commissioner."""
from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth import current_commissioner, get_session
from app.db import utcnow
from app.engine.dividends import post_week_dividends
from app.models import League, Listing, StatWeek, User
from app.providers.sleeper import SleeperProvider
from app.services import sync as sync_service
from app.services.listings import create_listings

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/sync-players")
def sync_players(user: User = Depends(current_commissioner), session: Session = Depends(get_session)):
    n = sync_service.sync_players(session, SleeperProvider())
    return {"players_synced": n}


class StatsIn(BaseModel):
    week: int = Field(ge=1, le=18)
    final: bool = True


@router.post("/sync-stats")
def sync_stats(body: StatsIn, user: User = Depends(current_commissioner), session: Session = Depends(get_session)):
    league = session.get(League, user.league_id)
    n = sync_service.sync_week_stats(
        session, SleeperProvider(), league.season_year, body.week, final=body.final
    )
    return {"stats_synced": n, "week": body.week, "final": body.final}


class DividendsIn(BaseModel):
    week: int = Field(ge=1, le=18)


@router.post("/dividends")
def run_dividends(body: DividendsIn, user: User = Depends(current_commissioner), session: Session = Depends(get_session)):
    run = post_week_dividends(session, user.league_id, body.week)
    return {"week": run.week, "rows_posted": run.rows_posted, "total_paid": float(run.total_paid)}


class StatFixIn(BaseModel):
    player_id: str
    week: int = Field(ge=1, le=18)
    pts: float


@router.post("/stat-fix")
def stat_fix(body: StatFixIn, user: User = Depends(current_commissioner), session: Session = Depends(get_session)):
    """Correct a stat. NOTE: if the week's dividends already posted, this does NOT
    claw back — post the correction before re-running dividends (the idempotence
    key skips already-paid holders, so a fix only affects unpaid rows)."""
    league = session.get(League, user.league_id)
    row = session.execute(
        select(StatWeek).where(
            StatWeek.season == league.season_year,
            StatWeek.week == body.week,
            StatWeek.player_id == body.player_id,
        )
    ).scalar_one_or_none()
    if row is None:
        row = StatWeek(season=league.season_year, week=body.week, player_id=body.player_id, pts=Decimal("0"))
        session.add(row)
    row.pts = Decimal(str(body.pts))
    row.is_final = True
    session.commit()
    return {"player_id": body.player_id, "week": body.week, "pts": body.pts}


class PauseIn(BaseModel):
    hours: float = Field(gt=0, le=24 * 14)
    player_id: str | None = None  # omit = whole market


@router.post("/pause")
def pause(body: PauseIn, user: User = Depends(current_commissioner), session: Session = Depends(get_session)):
    until = utcnow() + timedelta(hours=body.hours)
    q = update(Listing).where(Listing.league_id == user.league_id)
    if body.player_id:
        q = q.where(Listing.player_id == body.player_id)
    session.execute(q.values(locked_until=until))
    session.commit()
    return {"locked_until": until.isoformat(), "scope": body.player_id or "market"}


@router.post("/resume")
def resume(user: User = Depends(current_commissioner), session: Session = Depends(get_session)):
    session.execute(
        update(Listing).where(Listing.league_id == user.league_id).values(locked_until=None)
    )
    session.commit()
    return {"ok": True}


class OpeningBellIn(BaseModel):
    """Opening Bell (SPEC §3.1): projections snapshot -> listings. Source-agnostic:
    paste {player_id: projected_season_pts}."""

    projections: dict[str, float]


@router.post("/opening-bell")
def opening_bell(body: OpeningBellIn, user: User = Depends(current_commissioner), session: Session = Depends(get_session)):
    if not body.projections:
        raise HTTPException(status_code=400, detail="no projections given")
    league = session.get(League, user.league_id)
    n = create_listings(
        session, league, {pid: Decimal(str(p)) for pid, p in body.projections.items()}
    )
    return {"listings_created": n}
