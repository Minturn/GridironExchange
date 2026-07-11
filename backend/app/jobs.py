"""Background jobs (SPEC §6): nightly player sync, game locks, Tuesday dividends.

Enabled with GRIDX_ENABLE_SCHEDULER=1 (off in dev/tests — the commissioner
endpoints can drive everything by hand as a backstop).

Lock rule (SPEC §3.4): a player's trading locks at his game's kickoff and reopens
Tuesday 13:00 UTC (6 AM PT) when stats are final. The lock job runs every 15 min
and locks any listing whose team kicks off within the next 20 minutes (or is in
progress), so the boundary is never more than one poll behind.
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import func, select

from app.config import settings
from app.db import SessionLocal, utcnow
from app.engine.dividends import post_week_dividends, snapshot_holdings
from app.models import League, Listing, Player, StatWeek
from app.providers.espn import EspnSchedule
from app.providers.sleeper import SleeperProvider
from app.services import sync as sync_service

log = logging.getLogger("gridx.jobs")


def next_tuesday_1300(now: datetime) -> datetime:
    days_ahead = (1 - now.weekday()) % 7  # Tuesday = 1
    candidate = (now + timedelta(days=days_ahead)).replace(
        hour=13, minute=0, second=0, microsecond=0
    )
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def job_sync_players():
    with SessionLocal() as session:
        n = sync_service.sync_players(session, SleeperProvider())
        log.info("player sync: %d", n)


def _current_playing_week(session, season_year: int) -> int:
    """The week whose games are being played now = last final week + 1 (matches
    /api/state's current_week). Used to key the kickoff dividend snapshot."""
    last_final = session.execute(
        select(func.max(StatWeek.week)).where(
            StatWeek.season == season_year, StatWeek.is_final.is_(True)
        )
    ).scalar() or 0
    return min(last_final + 1, 18)


def job_game_locks():
    now = utcnow()
    games = EspnSchedule().current_week_games()
    teams_locking = set()
    for g in games:
        if g["state"] == "in" or (g["state"] == "pre" and g["kickoff"] <= now + timedelta(minutes=20)):
            teams_locking.update(g["teams"])
    if not teams_locking:
        return
    until = next_tuesday_1300(now)
    with SessionLocal() as session:
        listings = session.execute(
            select(Listing).join(Player, Listing.player_id == Player.id).where(
                Player.team.in_(teams_locking)
            )
        ).scalars().all()
        leagues = {lg.id: lg for lg in session.execute(select(League)).scalars()}
        by_league: dict[int, list[str]] = defaultdict(list)
        n = 0
        for l in listings:
            by_league[l.league_id].append(l.player_id)
            live = leagues[l.league_id].rules.in_game_trading == "live"
            if not live and (l.locked_until is None or l.locked_until < until):
                l.locked_until = until  # pilot/"locked": freeze the stock at kickoff
                n += 1
        session.commit()
        # Record-date snapshot at kickoff — ALWAYS, even in live mode, so dividends are
        # settled by kickoff ownership and post-kickoff (or 6:00-6:10) trades can't game them.
        snapped = 0
        for lid, pids in by_league.items():
            week = _current_playing_week(session, leagues[lid].season_year)
            snapped += snapshot_holdings(session, lid, week, pids)
        log.info(
            "game locks: %d locked, %d snapshot rows (teams=%s)", n, snapped, sorted(teams_locking)
        )


def job_tuesday_settlement():
    """Stats final + dividends for the week that just completed."""
    provider = SleeperProvider()
    state = provider.fetch_state()
    if state.get("season_type") != "regular":
        log.info("tuesday: not regular season (%s) — skip", state.get("season_type"))
        return
    week = int(state.get("week", 0)) - 1  # state has advanced to the upcoming week
    if not 1 <= week <= 18:
        return
    with SessionLocal() as session:
        leagues = session.execute(select(League)).scalars().all()
        for league in leagues:
            n = sync_service.sync_week_stats(
                session, provider, league.season_year, week, final=True
            )
            run = post_week_dividends(session, league.id, week)
            log.info(
                "tuesday wk%d league=%s: %d stats, %d dividends, $%s",
                week, league.name, n, run.rows_posted, run.total_paid,
            )


def job_price_snapshot():
    """Daily close for sparklines/charts — one PriceHistory point per listing,
    so charts move even on no-trade days."""
    from app.engine.amm import spot_price
    from app.models import PriceHistory

    now = utcnow()
    with SessionLocal() as session:
        for l in session.execute(select(Listing)).scalars():
            session.add(
                PriceHistory(
                    league_id=l.league_id,
                    player_id=l.player_id,
                    ts=now,
                    price=spot_price(l.p0, l.slope, l.shares_outstanding),
                )
            )
        session.commit()


def job_backup_db():
    """Nightly consistent snapshot of the SQLite DB → <db_dir>/backups, keep the last 14.
    The league data lives only on the host disk, so this is its safety net."""
    import glob
    import os
    import sqlite3

    if not settings.database_url.startswith("sqlite"):
        return
    src = settings.database_url.replace("sqlite:///", "", 1)
    if not os.path.exists(src):
        log.warning("db backup: source %s missing", src)
        return
    backup_dir = os.path.join(os.path.dirname(src) or ".", "backups")
    os.makedirs(backup_dir, exist_ok=True)
    dest = os.path.join(backup_dir, f"gridx-{utcnow():%Y%m%d-%H%M%S}.db")
    with sqlite3.connect(src) as s, sqlite3.connect(dest) as d:
        s.backup(d)  # consistent snapshot even while the app is writing
    for old in sorted(glob.glob(os.path.join(backup_dir, "gridx-*.db")))[:-14]:
        try:
            os.remove(old)
        except OSError:
            pass
    log.info("db backup → %s", dest)


def start_scheduler() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(job_sync_players, "cron", hour=9, minute=0)
    sched.add_job(job_backup_db, "cron", hour=8, minute=30)  # nightly DB backup
    sched.add_job(job_price_snapshot, "cron", hour=6, minute=0)
    sched.add_job(job_game_locks, "interval", minutes=15)
    sched.add_job(job_tuesday_settlement, "cron", day_of_week="tue", hour=13, minute=10)
    sched.start()
    log.info("scheduler started")
    return sched
