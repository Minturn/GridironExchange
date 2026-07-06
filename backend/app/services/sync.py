"""Provider → DB sync jobs. Scheduled by APScheduler in Phase 5; runnable by hand now."""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Player, StatWeek
from app.providers import StatsProvider


def sync_players(session: Session, provider: StatsProvider) -> int:
    """Upsert the fantasy-relevant player universe. Returns rows touched."""
    count = 0
    for rec in provider.fetch_players():
        player = session.get(Player, rec["id"])
        if player is None:
            player = Player(id=rec["id"])
            session.add(player)
        player.name = rec["name"]
        player.team = rec["team"]
        player.pos = rec["pos"]
        player.status = rec["status"]
        count += 1
    session.commit()
    return count


def sync_week_stats(
    session: Session,
    provider: StatsProvider,
    season: int,
    week: int,
    *,
    final: bool,
) -> int:
    """Upsert one week's fantasy points. Call with final=True Tuesday AM before the
    dividend run — dividends only read is_final rows. Only players already in the
    players table are recorded (stats feed covers the whole NFL)."""
    stats = provider.fetch_week_stats(season, week)
    known = set(session.execute(select(Player.id)).scalars())
    count = 0
    for pid, pts in stats.items():
        if pid not in known:
            continue
        row = (
            session.query(StatWeek)
            .filter_by(season=season, week=week, player_id=pid)
            .one_or_none()
        )
        if row is None:
            row = StatWeek(season=season, week=week, player_id=pid, pts=Decimal("0"))
            session.add(row)
        row.pts = pts
        row.is_final = final
        count += 1
    session.commit()
    return count
