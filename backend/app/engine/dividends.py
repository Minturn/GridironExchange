"""The Tuesday dividend run (SPEC §3.3, §6.1), scoring-mode aware.

Idempotent by construction: the (league, week, player, user) unique key on the
dividends ledger is the guard — rows already posted are skipped, so re-running a
week is always safe. Negative weekly points clamp to $0.

Mode (a per-league setting, app/engine/scoring.py):
  market   — every held share pays raw points × multiplier (baseline).
  relative — points scaled by a per-position factor, so positions are balanced.
  lineup   — only shares of a manager's starting-lineup players pay (raw points);
             one QB slot caps QB dividends. Uses the saved lineup, else auto-best.
Set lineups BEFORE the Tuesday run (like a real lineup lock).
"""
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine import scoring
from app.engine.amm import money
from app.models import Dividend, Holding, HoldingSnapshot, League, Listing, Player, StatWeek, User


@dataclass(frozen=True)
class DividendRun:
    league_id: int
    week: int
    rows_posted: int
    total_paid: Decimal


def snapshot_holdings(session: Session, league_id: int, week: int, player_ids) -> int:
    """Record who holds each given player *right now* as the dividend record-date for
    `week` — called at each player's kickoff. Idempotent per (league, week, player): a
    player already snapshotted this week is left untouched (kickoff holdings are frozen),
    so re-running the lock job never overwrites the record. Returns rows written."""
    written = 0
    for pid in player_ids:
        already = session.execute(
            select(HoldingSnapshot.id)
            .where(
                HoldingSnapshot.league_id == league_id,
                HoldingSnapshot.week == week,
                HoldingSnapshot.player_id == pid,
            )
            .limit(1)
        ).first()
        if already:
            continue
        for h in session.execute(
            select(Holding).where(
                Holding.league_id == league_id,
                Holding.player_id == pid,
                Holding.shares > 0,
            )
        ).scalars():
            session.add(
                HoldingSnapshot(
                    league_id=league_id, week=week, player_id=pid,
                    user_id=h.user_id, shares=h.shares,
                )
            )
            written += 1
    session.commit()
    return written


def _starters_by_user(session: Session, league_id: int, rules, holdings, pos_map, p0_map) -> dict:
    held_by_user: dict[int, list] = defaultdict(list)
    for h in holdings:
        held_by_user[h.user_id].append(
            {
                "id": h.player_id,
                "pos": pos_map.get(h.player_id, ""),
                "weight": float(p0_map.get(h.player_id, 0)),
            }
        )
    users = {
        u.id: u
        for u in session.execute(select(User).where(User.league_id == league_id)).scalars()
    }
    return {
        uid: scoring.effective_starters(held, rules.lineup_slots, getattr(users.get(uid), "lineup_json", None))
        for uid, held in held_by_user.items()
    }


def post_week_dividends(session: Session, league_id: int, week: int) -> DividendRun:
    league = session.get(League, league_id)
    rules = league.rules
    mode = rules.scoring_mode

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
    # Pay off the kickoff record-date snapshot when it exists; otherwise fall back to
    # live holdings (manual commissioner runs, or weeks the scheduler didn't snapshot).
    # Snapshot rows and Holding rows share .player_id/.user_id/.shares, so the loop below
    # is identical for both.
    holdings = session.execute(
        select(HoldingSnapshot).where(
            HoldingSnapshot.league_id == league_id, HoldingSnapshot.week == week
        )
    ).scalars().all()
    if not holdings:
        holdings = session.execute(
            select(Holding).where(Holding.league_id == league_id, Holding.shares > 0)
        ).scalars().all()

    pos_map = {p.id: p.pos for p in session.execute(select(Player)).scalars()}
    p0_map = {
        l.player_id: l.p0
        for l in session.execute(select(Listing).where(Listing.league_id == league_id)).scalars()
    }

    starters = (
        _starters_by_user(session, league_id, rules, holdings, pos_map, p0_map)
        if mode == scoring.LINEUP
        else {}
    )

    posted = 0
    total = Decimal("0.00")
    for h in holdings:
        pts = stats.get(h.player_id)
        if pts is None or (h.player_id, h.user_id) in already:
            continue
        if mode == scoring.LINEUP and h.player_id not in starters.get(h.user_id, set()):
            continue  # benched — no dividend this week
        base = max(pts, Decimal("0")) * rules.dividend_multiplier
        if mode == scoring.RELATIVE:
            base = base * scoring.position_factor(pos_map.get(h.player_id, ""))
        amount = money(h.shares * base)
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
