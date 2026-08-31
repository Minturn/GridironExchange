"""Live dividend accrual — ownership-over-time (SPEC §14), the "B" money model.

During games, poll each player's cumulative fantasy points (computed from RAW stats
via the league's rubric — app/engine/fantasy_scoring.py), diff against the last poll,
and credit each delta to whoever holds the player AT THAT TICK, at their share count.
So the weekly dividend follows ownership through the game: buy the hot hand and you
earn his rest-of-game; sell and you keep only what he banked while you held him.

Forward-only by construction — a delta is credited to *current* holders, never
retroactively — so you can't buy in after a play to steal points already accrued to
the previous holder. (The only residual edge is feed lag; that's a data-speed problem,
not a logic one — see the module docstring in scripts/probe_live_stats.py.)

Tuesday, `settle_week` sums each user's accruals per player, floors each at $0
(a bad game can't make you pay in), crystallizes them into the canonical `dividends`
ledger (so cash-history / reconciliation / the feed all keep working unchanged), and
flips `settled` so a re-run can't double-pay.
"""
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.engine import fantasy_scoring
from app.engine.amm import money
from app.models import AccrualCursor, Dividend, DividendAccrual, Holding, League, User

_ZERO = Decimal("0.00")


def cume_points(raw_by_player: dict[str, dict], scoring_format: str) -> dict[str, Decimal]:
    """Cumulative fantasy points per player from raw cumulative stats + the league's
    rubric. Feed this the live box score each poll; diff drives accrual."""
    rubric = fantasy_scoring.rubric_for(scoring_format)
    return {pid: fantasy_scoring.score(raw, rubric) for pid, raw in raw_by_player.items()}


def accrue_tick(
    session: Session,
    league_id: int,
    week: int,
    cume: dict[str, Decimal],
    last_cume: dict[str, Decimal],
    now=None,
) -> int:
    """One poll tick. For every player whose cumulative points moved since `last_cume`,
    credit `delta × shares × rate` to each current holder. Mutates `last_cume` in place,
    so a retried poll with the same numbers diffs to zero (idempotent). Returns rows
    written. Caller owns `last_cume` across ticks (e.g. the poll job keeps it per week)."""
    league = session.get(League, league_id)
    rate = league.rules.dividend_multiplier
    now = now or utcnow()
    written = 0
    for pid, raw_cume in cume.items():
        c = Decimal(str(raw_cume))
        delta = c - Decimal(str(last_cume.get(pid, 0)))
        if delta == 0:
            continue
        base = delta * rate
        for h in session.execute(
            select(Holding).where(
                Holding.league_id == league_id,
                Holding.player_id == pid,
                Holding.shares > 0,
            )
        ).scalars():
            session.add(
                DividendAccrual(
                    league_id=league_id, week=week, player_id=pid, user_id=h.user_id,
                    ts=now, shares_held=h.shares, points_delta=delta,
                    amount=money(h.shares * base),
                )
            )
            written += 1
        last_cume[pid] = c
    session.commit()
    return written


def accrue_live(
    session: Session,
    league_id: int,
    week: int,
    raw_lines: dict[str, dict],
    only_players: set[str] | None = None,
    now=None,
) -> int:
    """Production live-poll step (and Tuesday true-up). Scores each player's RAW line in
    the league's format, diffs against the persisted cursor, credits the delta to current
    holders, and advances the cursor — all in ONE commit, so a crash can't leave accruals
    and the cursor out of sync (which would double- or under-count). `only_players` limits
    to players whose games are live. Idempotent: a re-poll with the same numbers diffs to 0."""
    league = session.get(League, league_id)
    rate = league.rules.dividend_multiplier
    rubric = fantasy_scoring.resolve_rubric(league.rules.scoring_format, league.rules.scoring_rubric)
    now = now or utcnow()
    cursor = {
        c.player_id: c
        for c in session.execute(
            select(AccrualCursor).where(
                AccrualCursor.league_id == league_id, AccrualCursor.week == week
            )
        ).scalars()
    }
    written = 0
    for pid, raw in raw_lines.items():
        if only_players is not None and pid not in only_players:
            continue
        cume = fantasy_scoring.score(raw, rubric)
        prev = cursor[pid].cume if pid in cursor else Decimal("0")
        delta = cume - prev
        if delta == 0:
            continue
        base = delta * rate
        for h in session.execute(
            select(Holding).where(
                Holding.league_id == league_id, Holding.player_id == pid, Holding.shares > 0
            )
        ).scalars():
            session.add(
                DividendAccrual(
                    league_id=league_id, week=week, player_id=pid, user_id=h.user_id,
                    ts=now, shares_held=h.shares, points_delta=delta,
                    amount=money(h.shares * base),
                )
            )
            written += 1
        if pid in cursor:
            cursor[pid].cume = cume
        else:
            row = AccrualCursor(league_id=league_id, week=week, player_id=pid, cume=cume)
            session.add(row)
            cursor[pid] = row
    session.commit()
    return written


def provisional_by_user(session: Session, league_id: int, week: int) -> dict[int, Decimal]:
    """Live 'paycheck so far this week' per user — the number the scoreboard shows.
    Sum of un-settled accruals, floored at $0 (mirrors how settlement pays)."""
    totals: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    for a in session.execute(
        select(DividendAccrual).where(
            DividendAccrual.league_id == league_id,
            DividendAccrual.week == week,
            DividendAccrual.settled.is_(False),
        )
    ).scalars():
        totals[a.user_id] += a.amount
    return {uid: max(money(t), _ZERO) for uid, t in totals.items()}


@dataclass(frozen=True)
class Settlement:
    league_id: int
    week: int
    users_paid: int
    rows_posted: int
    total_paid: Decimal


def settle_week(session: Session, league_id: int, week: int) -> Settlement:
    """Tuesday reconciliation for an accrual-mode league. Sum un-settled accruals per
    (player, user), floor each at $0, write a canonical Dividend row + pay cash, and
    mark the accruals settled. Idempotent twice over: `settled` guards re-summing, and
    the dividends unique key (league,week,player,user) guards re-posting."""
    rows = session.execute(
        select(DividendAccrual).where(
            DividendAccrual.league_id == league_id,
            DividendAccrual.week == week,
            DividendAccrual.settled.is_(False),
        )
    ).scalars().all()

    amount: dict[tuple[str, int], Decimal] = defaultdict(lambda: Decimal("0"))
    points: dict[tuple[str, int], Decimal] = defaultdict(lambda: Decimal("0"))
    last_shares: dict[tuple[str, int], int] = {}
    for a in rows:
        key = (a.player_id, a.user_id)
        amount[key] += a.amount
        points[key] += a.points_delta
        last_shares[key] = a.shares_held  # representative shares for per-share display

    already = {
        (d.player_id, d.user_id)
        for d in session.execute(
            select(Dividend).where(Dividend.league_id == league_id, Dividend.week == week)
        ).scalars()
    }
    users_paid: set[int] = set()
    posted = 0
    total = _ZERO
    for (pid, uid), amt in amount.items():
        if (pid, uid) in already:
            continue
        pay = max(money(amt), _ZERO)
        if pay <= 0:
            continue  # a net-negative player pays nothing (never claws back)
        session.add(
            Dividend(
                league_id=league_id, week=week, player_id=pid, user_id=uid,
                shares_held=last_shares[(pid, uid)] or 1,
                pts=points[(pid, uid)], amount=pay,
            )
        )
        user = session.get(User, uid)
        user.cash = money(user.cash + pay)
        users_paid.add(uid)
        posted += 1
        total += pay

    for a in rows:
        a.settled = True
    session.commit()
    return Settlement(league_id, week, len(users_paid), posted, money(total))
