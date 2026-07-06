"""The Tuesday dividend run (SPEC §3.3, §6.1).

Idempotent by construction: the (league, week, player, user) unique key on the
dividends ledger is the guard — rows already posted are skipped, so re-running a
week is always safe. Negative weekly points clamp to $0 (a bad game costs you
price, not cash).
"""
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.amm import money
from app.models import Dividend, Holding, League, StatWeek, User


@dataclass(frozen=True)
class DividendRun:
    league_id: int
    week: int
    rows_posted: int
    total_paid: Decimal


def post_week_dividends(session: Session, league_id: int, week: int) -> DividendRun:
    league = session.get(League, league_id)
    rules = league.rules

    stats = {
        row.player_id: row.pts
        for row in session.execute(
            select(StatWeek).where(
                StatWeek.season == league.season_year,
                StatWeek.week == week,
                StatWeek.is_final.is_(True),
            )
        ).scalars()
    }
    already = {
        (d.player_id, d.user_id)
        for d in session.execute(
            select(Dividend).where(Dividend.league_id == league_id, Dividend.week == week)
        ).scalars()
    }
    holdings = session.execute(
        select(Holding).where(Holding.league_id == league_id, Holding.shares > 0)
    ).scalars().all()

    posted = 0
    total = Decimal("0.00")
    for h in holdings:
        pts = stats.get(h.player_id)
        if pts is None or (h.player_id, h.user_id) in already:
            continue
        amount = money(h.shares * max(pts, Decimal("0")) * rules.dividend_multiplier)
        session.add(
            Dividend(
                league_id=league_id,
                week=week,
                player_id=h.player_id,
                user_id=h.user_id,
                shares_held=h.shares,
                pts=pts,
                amount=amount,
            )
        )
        user = session.get(User, h.user_id)
        user.cash = money(user.cash + amount)
        posted += 1
        total += amount

    session.commit()
    return DividendRun(league_id=league_id, week=week, rows_posted=posted, total_paid=money(total))
