"""Per-user cash reconciliation from the immutable ledgers (SPEC §6.1).

After the opening balance, cash moves in exactly two ways: a trade (buy debits
gross+fee, sell credits gross−fee — see app/engine/trading.py) and a dividend
(a credit — app/engine/dividends.py). Replaying those two ledgers in time order
reproduces `users.cash` to the cent, because gross/fee/amount are all stored
cent-rounded. So the same walk that powers the personal cash-history view is also
the audit that proves the mutable `cash` column never drifted from the ledgers.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.amm import money
from app.models import Dividend, Trade, User


@dataclass(frozen=True)
class CashEvent:
    ts: datetime | None       # None only for the synthetic opening balance
    kind: str                 # "start" | "buy" | "sell" | "dividend"
    delta: Decimal            # signed change to cash
    balance: Decimal          # running cash immediately after this event
    player_id: str | None = None
    shares: int | None = None
    week: int | None = None
    gross: Decimal | None = None
    fee: Decimal | None = None


def cash_events(session: Session, user_id: int, starting_cash: Decimal) -> list[CashEvent]:
    """Every cash-affecting event for one user, oldest → newest, with a running
    balance. Element 0 is always the opening balance; the final element's
    `balance` equals the user's stored cash iff the ledgers reconcile."""
    rows: list[tuple] = []
    for t in session.execute(select(Trade).where(Trade.user_id == user_id)).scalars():
        delta = -(t.gross + t.fee) if t.side == "buy" else (t.gross - t.fee)
        rows.append((t.ts, t.id, t.side, delta, t.player_id, t.shares, None, t.gross, t.fee))
    for d in session.execute(select(Dividend).where(Dividend.user_id == user_id)).scalars():
        rows.append((d.ts, d.id, "dividend", d.amount, d.player_id, d.shares_held, d.week, None, None))
    # (ts, id): id breaks ties so same-timestamp events keep insertion order
    rows.sort(key=lambda r: (r[0], r[1]))

    bal = money(starting_cash)
    events = [CashEvent(ts=None, kind="start", delta=bal, balance=bal)]
    for ts, _id, kind, delta, pid, shares, week, gross, fee in rows:
        bal = money(bal + delta)
        events.append(
            CashEvent(
                ts=ts, kind=kind, delta=delta, balance=bal,
                player_id=pid, shares=shares, week=week, gross=gross, fee=fee,
            )
        )
    return events


@dataclass(frozen=True)
class Reconciliation:
    computed_cash: Decimal  # cash implied by replaying the ledgers
    stored_cash: Decimal    # the mutable users.cash column
    drift: Decimal          # stored − computed; $0.00 when they agree
    ok: bool


def reconcile(session: Session, user: User, starting_cash: Decimal) -> Reconciliation:
    """Replay a user's ledgers and compare against the stored cash column."""
    events = cash_events(session, user.id, starting_cash)
    computed = events[-1].balance
    drift = money(user.cash - computed)
    return Reconciliation(computed, money(user.cash), drift, drift == Decimal("0.00"))
