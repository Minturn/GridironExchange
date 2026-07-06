"""Background jobs (SPEC §6): nightly player sync, game locks, Tuesday dividends.

Enabled with GRIDX_ENABLE_SCHEDULER=1 (off in dev/tests — the commissioner
endpoints can drive everything by hand as a backstop).

Lock rule (SPEC §3.4): a player's trading locks at his game's kickoff and reopens
Tuesday 13:00 UTC (6 AM PT) when stats are final. The lock job runs every 15 min
and locks any listing whose team kicks off within the next 20 minutes (or is in
progress), so the boundary is never more than one poll behind.
"""
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from app.db import SessionLocal, utcnow
from app.engine.dividends import post_week_dividends
from app.models import League, Listing, Player
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
        n = 0
        for l in listings:
            if l.locked_until is None or l.locked_until < until:
                l.locked_until = until
                n += 1
        session.commit()
        log.info("game locks: %d listings locked until %s (%s)", n, until, sorted(teams_locking))


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


def start_scheduler() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(job_sync_players, "cron", hour=9, minute=0)
    sched.add_job(job_price_snapshot, "cron", hour=6, minute=0)
    sched.add_job(job_game_locks, "interval", minutes=15)
    sched.add_job(job_tuesday_settlement, "cron", day_of_week="tue", hour=13, minute=10)
    sched.start()
    log.info("scheduler started")
    return sched
