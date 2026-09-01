"""Commissioner tools — everything here requires is_commissioner."""
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.auth import current_commissioner, get_session, hash_password
from app.db import utcnow
from app.engine import fantasy_scoring, ledger
from app.engine.dividends import post_week_dividends
from app.models import (
    Dividend,
    DividendAccrual,
    Holding,
    HoldingSnapshot,
    League,
    Listing,
    StatWeek,
    Trade,
    User,
)
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


@router.get("/audit")
def audit(user: User = Depends(current_commissioner), session: Session = Depends(get_session)):
    """Replay every member's immutable ledgers and compare to their stored cash.
    `all_ok` False means a `cash` column has drifted from the trade+dividend history
    — a bug or a hand-edit — with the exact per-member drift to chase down."""
    league = session.get(League, user.league_id)
    starting = league.rules.starting_cash
    members = session.execute(
        select(User).where(User.league_id == league.id)
    ).scalars().all()
    rows = []
    for m in members:
        rec = ledger.reconcile(session, m, starting)
        rows.append(
            {
                "username": m.username,
                "cash": float(rec.stored_cash),
                "computed_cash": float(rec.computed_cash),
                "drift": float(rec.drift),
                "ok": rec.ok,
            }
        )
    rows.sort(key=lambda r: (r["ok"], r["username"]))  # mismatches first
    return {
        "league": league.name,
        "starting_cash": float(starting),
        "all_ok": all(r["ok"] for r in rows),
        "members": rows,
    }


class ScoringFormatIn(BaseModel):
    fmt: str = Field(pattern="^(ppr|half_ppr|std)$")


@router.post("/scoring-format")
def set_scoring_format(body: ScoringFormatIn, user: User = Depends(current_commissioner), session: Session = Depends(get_session)):
    """Fantasy scoring format — how raw stats become points (full PPR / half / standard).
    Applies to the NEXT dividend run; never re-prices the market."""
    league = session.get(League, user.league_id)
    settings = dict(league.settings_json or {})
    settings["scoring_format"] = body.fmt
    league.settings_json = settings
    session.commit()
    return {"scoring_format": league.rules.scoring_format}


class ImportScoringIn(BaseModel):
    sleeper_league_id: str = Field(min_length=3, max_length=40)


@router.post("/import-scoring")
def import_scoring(body: ImportScoringIn, user: User = Depends(current_commissioner), session: Session = Depends(get_session)):
    """Mirror a real Sleeper league's exact scoring: pull its scoring_settings, store it
    as this league's custom rubric, and flip scoring_format to 'custom'. Onboarding in one
    step. Applies to the next dividend run; never re-prices the market."""
    settings_raw = SleeperProvider().fetch_league_scoring(body.sleeper_league_id)
    if not settings_raw:
        raise HTTPException(status_code=400, detail="no scoring settings found for that Sleeper league id")
    rubric = fantasy_scoring.sleeper_to_rubric(settings_raw)
    if not rubric:
        raise HTTPException(status_code=400, detail="that league's scoring didn't map to any rules")
    league = session.get(League, user.league_id)
    settings = dict(league.settings_json or {})
    settings["scoring_rubric"] = {k: str(v) for k, v in rubric.items()}  # strings → JSON/Decimal-safe
    settings["scoring_format"] = "custom"
    league.settings_json = settings
    session.commit()
    return {"scoring_format": "custom", "rules_imported": len(rubric)}


class DividendModeIn(BaseModel):
    mode: str = Field(pattern="^(snapshot|accrual)$")


@router.post("/dividend-mode")
def set_dividend_mode(body: DividendModeIn, user: User = Depends(current_commissioner), session: Session = Depends(get_session)):
    """snapshot = own-at-kickoff (whole week to the kickoff holder). accrual = live
    ownership-over-time (SPEC §14): the dividend follows who held the player as he scored."""
    league = session.get(League, user.league_id)
    settings = dict(league.settings_json or {})
    settings["dividend_mode"] = body.mode
    league.settings_json = settings
    session.commit()
    return {"dividend_mode": league.rules.dividend_mode}


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


@router.get("/members")
def list_members(user: User = Depends(current_commissioner), session: Session = Depends(get_session)):
    """Every manager in the league, with the context the Remove-member card needs: who
    they are, whether they're you or a commissioner (both un-removable), and their live
    market footprint (shares held, trades made) so removal warns before it moves prices."""
    members = session.scalars(
        select(User).where(User.league_id == user.league_id).order_by(User.username)
    ).all()
    rows = []
    for m in members:
        shares = session.scalar(
            select(func.coalesce(func.sum(Holding.shares), 0)).where(Holding.user_id == m.id)
        )
        trades = session.scalar(select(func.count(Trade.id)).where(Trade.user_id == m.id))
        rows.append({
            "user_id": m.id,
            "username": m.username,
            "is_commissioner": bool(m.is_commissioner),
            "is_you": m.id == user.id,
            "cash": float(m.cash),
            "shares": int(shares or 0),
            "trades": int(trades or 0),
        })
    return {"members": rows}


class RemoveMemberIn(BaseModel):
    user_id: int
    liquidate: bool = False


@router.post("/remove-member")
def remove_member(body: RemoveMemberIn, user: User = Depends(current_commissioner), session: Session = Depends(get_session)):
    """Remove a manager and purge their account. Refuses to remove you or another
    commissioner. A member holding shares needs `liquidate=true`: their book is returned
    to the market (each player's supply drops, so the price curve eases back down), which
    keeps sum(holdings) == shares_outstanding, then the account and all its ledger rows
    are deleted. Deletes are manual because SQLite foreign keys don't cascade."""
    target = session.get(User, body.user_id)
    if target is None or target.league_id != user.league_id:
        raise HTTPException(status_code=404, detail="no such member in your league")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="you can't remove yourself")
    if target.is_commissioner:
        raise HTTPException(status_code=400, detail="can't remove a commissioner — hand off the role first")

    holdings = session.scalars(
        select(Holding).where(Holding.user_id == target.id, Holding.shares != 0)
    ).all()
    shares_out = sum(h.shares for h in holdings)
    if shares_out > 0 and not body.liquidate:
        raise HTTPException(
            status_code=409,
            detail=(f"{target.username} holds {shares_out} shares across {len(holdings)} "
                    "players — confirm to sell their book back to the market first"),
        )

    # Return their shares to each player's float. The price curve reads shares_outstanding,
    # so supply coming back eases the price down — same effect as if they'd sold out.
    for h in holdings:
        listing = session.scalar(
            select(Listing).where(
                Listing.league_id == target.league_id, Listing.player_id == h.player_id
            )
        )
        if listing is not None:
            listing.shares_outstanding = max(0, listing.shares_outstanding - h.shares)

    for model in (Holding, Trade, Dividend, DividendAccrual, HoldingSnapshot):
        session.execute(delete(model).where(model.user_id == target.id))
    username = target.username
    session.delete(target)
    session.commit()
    return {"removed": username, "liquidated": shares_out > 0, "shares_returned": shares_out}


class RegistrationIn(BaseModel):
    open: bool


@router.post("/registration")
def set_registration(body: RegistrationIn, user: User = Depends(current_commissioner), session: Session = Depends(get_session)):
    """Open or close the league to new members. Closed = the invite code stops working for
    new sign-ups (existing members are unaffected). Close it once everyone's in so a leaked
    code can't add strangers."""
    league = session.get(League, user.league_id)
    settings = dict(league.settings_json or {})
    settings["registration_closed"] = not body.open
    league.settings_json = settings
    session.commit()
    return {"registration_open": body.open}


# unambiguous alphabet — no 0/O/1/l/I, so a texted temp password is easy to read and type
_TEMP_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


class ResetPasswordIn(BaseModel):
    user_id: int


@router.post("/reset-password")
def reset_password(body: ResetPasswordIn, user: User = Depends(current_commissioner), session: Session = Depends(get_session)):
    """Set a member's password to a fresh temporary one and return it, so a locked-out
    manager can get back in. The commissioner reads the temp password to them (this league
    has no email on file by design); they log in with it. Works on any member in the league."""
    target = session.get(User, body.user_id)
    if target is None or target.league_id != user.league_id:
        raise HTTPException(status_code=404, detail="no such member in your league")
    temp = "".join(secrets.choice(_TEMP_ALPHABET) for _ in range(8))
    target.pw_hash = hash_password(temp)
    session.commit()
    return {"username": target.username, "temp_password": temp}
