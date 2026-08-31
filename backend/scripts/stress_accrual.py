"""Break-it stress for LIVE ACCRUAL under concurrency (SPEC §14 money path).

Simulates a live game on the serialized engine: ONE poll loop accrues points as
cumulative scores climb, while a swarm of trader threads buy/sell the very same
players at the same time (ownership churning under the accrual). Then Tuesday
settles. We then assert nothing broke:

  1. shares_outstanding == Σ holdings           (concurrency canary)
  2. no negative cash
  3. every user's cash reconciles with the trade+dividend ledger
  4. GLOBAL money conservation — settlement created no money beyond the accruals
     that actually happened (cash == N·start + sells − buys − fees + dividends)
  5. accrual→settlement is exact: Σ settled dividends == Σ over (player,user) of
     max(0, Σ that pair's accruals)   — the floor, nothing more, nothing less

Usage (from backend/):  python scripts/stress_accrual.py
"""
import os
import random
import sys
import tempfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from threading import Lock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.auth import hash_password
from app.db import Base
from app.engine import ledger
from app.engine.accrual import accrue_tick, settle_week
from app.engine.amm import money
from app.engine.trading import TradeError, execute_trade
from app.models import Dividend, DividendAccrual, Holding, League, Listing, Player, Trade, User

SEED = 90909
N_USERS = 60
N_PLAYERS = 12
TICKS = 25
TRADERS = 40
START = Decimal("10000.00")
RATE = Decimal("0.30")


def make_engine():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    eng = create_engine(f"sqlite:///{path}", future=True, pool_size=64, max_overflow=32,
                        connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(eng, "connect")
    def _p(dbapi, _r):
        dbapi.isolation_level = None
        cur = dbapi.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.close()

    @event.listens_for(eng, "begin")
    def _b(conn):
        conn.exec_driver_sql("BEGIN IMMEDIATE")

    return eng, path


def seed(SL):
    rng = random.Random(SEED)
    with SL() as s:
        lg = League(name="Accr", invite_code="ac", season_year=2026,
                    settings_json={"scoring_mode": "market", "in_game_trading": "live",
                                   "dividend_mode": "accrual", "starting_cash": str(START),
                                   "share_cap": 25, "fee_rate": "0.01",
                                   "dividend_multiplier": str(RATE)})
        s.add(lg); s.flush()
        for i in range(N_USERS):
            s.add(User(league_id=lg.id, username=f"u{i:02d}", pw_hash=hash_password("x"), cash=START))
        players = [f"g{i:02d}" for i in range(N_PLAYERS)]
        from app.services.listings import create_listings
        for pid in players:
            s.add(Player(id=pid, name=pid, pos="WR", team="G", status="Active"))
        s.commit()
        create_listings(s, lg, {pid: Decimal(rng.randint(80, 260)) for pid in players})
        lid = lg.id
        uids = [r[0] for r in s.execute(select(User.id))]
    # outer setup session is now CLOSED (its read-lock released) before we open
    # per-trade sessions — otherwise BEGIN IMMEDIATE on those would starve on it.
    for uid in uids:
        for pid in rng.sample(players, 4):
            s2 = SL()
            try:
                execute_trade(s2, user_id=uid, player_id=pid, side="buy", shares=rng.randint(1, 4))
            except TradeError:
                pass
            except OperationalError:
                s2.rollback()
            finally:
                s2.close()
    return lid, players, uids


def poll_loop(SL, lid, players, stop_flag):
    """The single live-poll thread: cumulative points climb; accrue each tick."""
    rng = random.Random(1)
    cume = {p: Decimal("0") for p in players}
    last = {}
    for _ in range(TICKS):
        for p in players:
            cume[p] += Decimal(str(rng.choice([0, 0, 1, 2, 3, -1, 6])))  # yards, TDs, the odd INT
        s = SL()
        try:
            accrue_tick(s, lid, 1, dict(cume), last)
        except OperationalError:
            s.rollback()
        finally:
            s.close()


def trader(SL, uid, players, tally, clk):
    rng = random.Random(SEED ^ uid)
    for _ in range(6):
        s = SL()
        try:
            execute_trade(s, user_id=uid, player_id=rng.choice(players),
                          side=rng.choice(["buy", "buy", "sell"]), shares=rng.randint(1, 4))
            with clk:
                tally["ok"] += 1
        except TradeError:
            with clk:
                tally["rej"] += 1
        except OperationalError:
            s.rollback()
            with clk:
                tally["locked"] += 1
        finally:
            s.close()


def check(SL, lid):
    problems = []
    with SL() as s:
        held = defaultdict(int)
        for h in s.execute(select(Holding)).scalars():
            held[h.player_id] += h.shares
            if h.shares < 0:
                problems.append(f"neg holding {h.player_id}")
        for l in s.execute(select(Listing)).scalars():
            if l.shares_outstanding != held.get(l.player_id, 0):
                problems.append(f"SHARE DIVERGENCE {l.player_id}: {l.shares_outstanding} vs {held.get(l.player_id,0)}")
        for u in s.execute(select(User)).scalars():
            if u.cash < 0:
                problems.append(f"NEG cash {u.username}")
            rec = ledger.reconcile(s, u, START)
            if not rec.ok:
                problems.append(f"LEDGER DRIFT {u.username} Δ{rec.drift}")

        def q(v): return Decimal(str(v or 0))
        buy_g = q(s.execute(select(func.sum(Trade.gross)).where(Trade.side == "buy")).scalar())
        sell_g = q(s.execute(select(func.sum(Trade.gross)).where(Trade.side == "sell")).scalar())
        fees = q(s.execute(select(func.sum(Trade.fee))).scalar())
        divs = q(s.execute(select(func.sum(Dividend.amount))).scalar())
        cash = money(q(s.execute(select(func.sum(User.cash))).scalar()))
        expected = money(Decimal(N_USERS) * START + sell_g - buy_g - fees + divs)
        if cash != expected:
            problems.append(f"MONEY LEAK cash={cash} expected={expected} Δ{cash-expected}")

        # settlement exactly equals floored per-(player,user) accruals
        acc = defaultdict(lambda: Decimal("0"))
        for a in s.execute(select(DividendAccrual)).scalars():
            acc[(a.player_id, a.user_id)] += a.amount
        floored = sum((max(money(v), Decimal("0.00")) for v in acc.values()), Decimal("0.00"))
        if money(floored) != divs:
            problems.append(f"ACCRUAL≠SETTLEMENT floored={money(floored)} settled_divs={divs}")
    return problems


def main():
    eng, path = make_engine()
    Base.metadata.create_all(eng)
    SL = sessionmaker(bind=eng, expire_on_commit=False, future=True)
    lid, players, uids = seed(SL)
    tally, clk = defaultdict(int), Lock()

    # live game: 1 poller + many traders, all at once
    with ThreadPoolExecutor(max_workers=TRADERS + 2) as pool:
        pool.submit(poll_loop, SL, lid, players, None)
        for uid in uids[:TRADERS]:
            pool.submit(trader, SL, uid, players, tally, clk)

    with SL() as s:
        n_acc = s.execute(select(func.count()).select_from(DividendAccrual)).scalar()
    s = SL()
    run = settle_week(s, lid, 1)
    s.close()
    problems = check(SL, lid)

    print("LIVE ACCRUAL break-it (serialized engine, poll + concurrent trades)")
    print(f"  trades: {dict(tally)} | accrual rows: {n_acc}")
    print(f"  settled: {run.rows_posted} dividend rows, {run.users_paid} users, ${run.total_paid}")
    if problems:
        print(f"  INVARIANTS: ❌ {len(problems)}")
        for p in problems[:10]:
            print(f"     - {p}")
    else:
        print("  INVARIANTS: ✅ shares conserved · cash≥0 · ledger reconciles · "
              "no money leaked · settlement == floored accruals")
    eng.dispose(); os.unlink(path)


if __name__ == "__main__":
    main()
