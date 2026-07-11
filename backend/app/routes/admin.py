"""Commissioner tools — everything here requires is_commissioner."""
from datetime import datetime, timedelta, timezone
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


class OpenTimeIn(BaseModel):
    # ISO 8601 (may carry a timezone). null / omitted = open the market immediately.
    opens_at: datetime | None = None


@router.post("/open-time")
def set_open_time(body: OpenTimeIn, user: User = Depends(current_commissioner), session: Session = Depends(get_session)):
    """Set THIS league's market-open time — the Week 1 starting gun. Until then every
    listing is locked, so nobody can trade and the whole league starts together (no
    early-bird edge). Stored per league; pass no time to open right now."""
    league = session.get(League, user.league_id)
    settings = dict(league.settings_json or {})
    if body.opens_at is not None:
        opens_at = body.opens_at
        if opens_at.tzinfo is not None:  # normalise to naive UTC (how the engine compares)
            opens_at = opens_at.astimezone(timezone.utc).replace(tzinfo=None)
        settings["market_opens_at"] = opens_at.isoformat()
        league.settings_json = settings
        session.execute(
            update(Listing).where(Listing.league_id == league.id).values(locked_until=opens_at)
        )
        session.commit()
        return {"market_opens_at": opens_at.isoformat() + "Z", "status": "scheduled"}
    settings.pop("market_opens_at", None)
    league.settings_json = settings
    session.execute(
        update(Listing).where(Listing.league_id == league.id).values(locked_until=None)
    )
    session.commit()
    return {"market_opens_at": None, "status": "open"}


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


class ScoringModeIn(BaseModel):
    mode: str = Field(pattern="^(market|relative|lineup)$")


@router.post("/scoring-mode")
def set_scoring_mode(body: ScoringModeIn, user: User = Depends(current_commissioner), session: Session = Depends(get_session)):
    """Pick how dividends are scored for this league — 'market', 'relative', or
    'lineup'. Only affects dividends; never re-prices the market."""
    league = session.get(League, user.league_id)
    settings = dict(league.settings_json or {})
    settings["scoring_mode"] = body.mode
    league.settings_json = settings
    session.commit()
    return {"scoring_mode": body.mode}


class InGameTradingIn(BaseModel):
    mode: str = Field(pattern="^(locked|live)$")


@router.post("/in-game-trading")
def set_in_game_trading(body: InGameTradingIn, user: User = Depends(current_commissioner), session: Session = Depends(get_session)):
    """'locked' — a player's stock freezes at his kickoff (pilot default, no trading on
    live info). 'live' — stays tradeable during games (the product feature). Dividends
    settle by the kickoff snapshot either way, so this is safe to flip. Switching to
    'live' only stops NEW kickoff locks; players already locked this week clear on the
    next Tuesday run (or via Resume)."""
    league = session.get(League, user.league_id)
    settings = dict(league.settings_json or {})
    settings["in_game_trading"] = body.mode
    league.settings_json = settings
    if body.mode == "live":
        # clear any game-locks already applied this week so the switch takes effect now.
        # (Opening-bell / manual pause use the same column; re-set those afterward if needed.)
        session.execute(
            update(Listing).where(Listing.league_id == league.id).values(locked_until=None)
        )
    session.commit()
    return {"in_game_trading": body.mode}


class RulesIn(BaseModel):
    dividend_multiplier: float | None = Field(default=None, gt=0, le=100)
    fee_rate: float | None = Field(default=None, ge=0, le=0.5)
    share_cap: int | None = Field(default=None, ge=1, le=1000)


@router.post("/rules")
def set_rules(body: RulesIn, user: User = Depends(current_commissioner), session: Session = Depends(get_session)):
    """Adjust the league's scoring/economy dials — the dividend rate ($/point/share)
    is the main one. Takes effect on the next dividend run; never re-prices the market."""
    league = session.get(League, user.league_id)
    settings = dict(league.settings_json or {})
    if body.dividend_multiplier is not None:
        settings["dividend_multiplier"] = str(body.dividend_multiplier)
    if body.fee_rate is not None:
        settings["fee_rate"] = str(body.fee_rate)
    if body.share_cap is not None:
        settings["share_cap"] = body.share_cap
    league.settings_json = settings
    session.commit()
    r = league.rules
    return {
        "dividend_multiplier": str(r.dividend_multiplier),
        "fee_rate": str(r.fee_rate),
        "share_cap": r.share_cap,
    }
