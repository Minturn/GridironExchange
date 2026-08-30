"""Full-season stress + concurrency simulation.

100 managers, 100 players, 18 weeks of HEAVY concurrent trading, weekly dividends.
Runs entirely against a throwaway temp SQLite file — NEVER touches the live league.

Why this exists: execute_trade serializes with SELECT ... FOR UPDATE, but SQLite
ignores FOR UPDATE, and app/db.py builds the engine with no busy_timeout / WAL.
So simultaneous trades on the same player are the danger zone. This proves whether
the invariants hold, and contrasts the live engine config against a hardened one.

Invariants checked (must ALWAYS hold):
  1. shares_outstanding == sum(holdings) per player   <- lost-update corruption canary
  2. every user's cash >= 0
  3. every holding 0 <= shares <= share_cap
  4. every user's cash reconciles with the trade+dividend ledger (engine/ledger.py)

Usage (from backend/, venv active):
    python scripts/simulate_season.py
"""
import os
import random
import sys
import tempfile
from collections import Counter
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
from app.engine.dividends import post_week_dividends
from app.engine.trading import TradeError, execute_trade
from app.models import Dividend, Holding, League, Listing, Player, StatWeek, Trade, User
from app.services.listings import create_listings

SEED = 20260828
N_USERS = 100
N_PLAYERS = 100
N_WEEKS = 18
HOT = 12                    # a few players everyone piles into -> real collisions
TRADES_PER_USER_WEEK = 8
WORKERS = 40               # threads hammering the DB at once
HERD = 90                  # threads that buy the SAME player at the SAME instant

LEAGUE_SETTINGS = {
    "scoring_mode": "market",
    "in_game_trading": "live",
    "starting_cash": "10000.00",
    "share_cap": 25,
    "fee_rate": "0.01",
    "dividend_multiplier": "0.30",
}


def make_engine(mode: str):
    """mode: 'live' (app/db.py as-is) | 'wal' (WAL+busy_timeout) |
    'serialized' (WAL+busy_timeout+BEGIN IMMEDIATE — the real fix)."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    url = f"sqlite:///{path}"
    if mode == "live":
        return create_engine(url, future=True), path  # EXACTLY app/db.py

    eng = create_engine(
        url, future=True, pool_size=WORKERS + 8, max_overflow=32,
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(eng, "connect")
    def _pragmas(dbapi, _rec):
        if mode == "serialized":
            dbapi.isolation_level = None  # we drive transactions ourselves
        cur = dbapi.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

    if mode == "serialized":
        @event.listens_for(eng, "begin")
        def _begin_immediate(conn):
            # grab the write lock BEFORE the read-modify-write, so trades serialize
            # (what FOR UPDATE would do on Postgres). busy_timeout makes rivals wait.
            conn.exec_driver_sql("BEGIN IMMEDIATE")

    return eng, path


def seed(SessionLocal):
    rng = random.Random(SEED)
    with SessionLocal() as s:
        league = League(name="Sim League", invite_code="sim",
                        season_year=2026, settings_json=dict(LEAGUE_SETTINGS))
        s.add(league)
        s.flush()
        for i in range(N_USERS):
            s.add(User(league_id=league.id, username=f"mgr{i:03d}",
                       pw_hash=hash_password("x"), cash=league.rules.starting_cash))
        players = [f"p{i:03d}" for i in range(N_PLAYERS)]
        for pid in players:
            s.add(Player(id=pid, name=pid.upper(), pos=rng.choice(["QB", "RB", "WR", "TE"]),
                         team="SIM", status="Active"))
        s.commit()
        projections = {pid: Decimal(rng.randint(40, 380)) for pid in players}
        create_listings(s, league, projections)
        uids = [u.id for u in s.execute(select(User.id)).all()]
        return league.id, players, [u[0] for u in s.execute(select(User.id))]


def pick(rng, players):
    # bias toward the HOT players so concurrent threads collide on the same listing
    if rng.random() < 0.55:
        return players[rng.randrange(HOT)]
    return players[rng.randrange(len(players))]


def trade_burst(SessionLocal, uid, players, counters, clock):
    rng = random.Random(SEED ^ uid)
    s = SessionLocal()
    try:
        for _ in range(TRADES_PER_USER_WEEK):
            pid = pick(rng, players)
            side = "buy" if rng.random() < 0.62 else "sell"
            shares = rng.randint(1, 5)
            try:
                execute_trade(s, user_id=uid, player_id=pid, side=side, shares=shares)
                with clock:
                    counters[f"{side}_ok"] += 1
            except TradeError:
                with clock:
                    counters["rejected_business"] += 1
            except OperationalError:
                s.rollback()
                with clock:
                    counters["FAILED_db_locked"] += 1
    finally:
        s.close()


def run_week(SessionLocal, uids, players, counters, clock):
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for uid in uids:
            pool.submit(trade_burst, SessionLocal, uid, players, counters, clock)


def post_stats_and_dividends(SessionLocal, league_id, players, week):
    rng = random.Random(SEED + week)
    with SessionLocal() as s:
        league = s.get(League, league_id)
        for pid in players:
            pts = Decimal(str(round(rng.uniform(-3, 34), 2)))
            s.add(StatWeek(season=league.season_year, week=week, player_id=pid,
                           pts=pts, is_final=True))
        s.commit()
        run = post_week_dividends(s, league_id, week)
        return run.rows_posted, run.total_paid


def herd_test(SessionLocal, players, uids, counters, clock):
    """The sharp edge: HERD threads buy the SAME player simultaneously."""
    target = players[0]
    buyers = uids[:HERD]

    def one(uid):
        s = SessionLocal()
        try:
            execute_trade(s, user_id=uid, player_id=target, side="buy", shares=1)
            with clock:
                counters["herd_ok"] += 1
        except TradeError:
            with clock:
                counters["herd_rejected"] += 1
        except OperationalError:
            s.rollback()
            with clock:
                counters["herd_FAILED_db_locked"] += 1
        finally:
            s.close()

    with ThreadPoolExecutor(max_workers=HERD) as pool:
        list(pool.map(one, buyers))
    return target


def check_invariants(SessionLocal, league_id):
    problems = []
    with SessionLocal() as s:
        league = s.get(League, league_id)
        start = league.rules.starting_cash
        cap = league.rules.share_cap

        # 1. shares_outstanding == sum(holdings) per player  (corruption canary)
        held = Counter()
        for h in s.execute(select(Holding)).scalars():
            held[h.player_id] += h.shares
            if h.shares < 0:
                problems.append(f"NEGATIVE holding: u{h.user_id} {h.player_id}={h.shares}")
            if h.shares > cap:
                problems.append(f"OVER CAP: u{h.user_id} {h.player_id}={h.shares} > {cap}")
        divergent = 0
        for l in s.execute(select(Listing)).scalars():
            if l.shares_outstanding != held.get(l.player_id, 0):
                divergent += 1
                if divergent <= 6:
                    problems.append(
                        f"SHARE DIVERGENCE {l.player_id}: "
                        f"listing={l.shares_outstanding} vs holdings={held.get(l.player_id, 0)}"
                    )
        if divergent > 6:
            problems.append(f"... and {divergent - 6} more divergent listings")

        # 2/4. cash >= 0 and ledger reconciles
        neg_cash = drift = 0
        for u in s.execute(select(User)).scalars():
            if u.cash < 0:
                neg_cash += 1
                problems.append(f"NEGATIVE cash: {u.username} = {u.cash}")
            rec = ledger.reconcile(s, u, start)
            if not rec.ok:
                drift += 1
                if drift <= 6:
                    problems.append(f"LEDGER DRIFT {u.username}: stored {rec.stored_cash} "
                                    f"vs ledger {rec.computed_cash} (Δ {rec.drift})")
    return problems, divergent


def simulate(mode: str):
    eng, path = make_engine(mode)
    Base.metadata.create_all(eng)
    SessionLocal = sessionmaker(bind=eng, expire_on_commit=False, future=True)
    counters = Counter()
    clock = Lock()

    league_id, players, uids = seed(SessionLocal)

    # focused concurrency canary first
    herd_test(SessionLocal, players, uids, counters, clock)

    total_div_rows = 0
    total_div_paid = Decimal("0.00")
    for wk in range(1, N_WEEKS + 1):
        run_week(SessionLocal, uids, players, counters, clock)
        rows, paid = post_stats_and_dividends(SessionLocal, league_id, players, wk)
        total_div_rows += rows
        total_div_paid += paid

    problems, divergent = check_invariants(SessionLocal, league_id)

    # aggregate money view
    with SessionLocal() as s:
        total_cash = s.execute(select(func.sum(User.cash))).scalar() or 0
        n_trades = s.execute(select(func.count()).select_from(Trade)).scalar()

    eng.dispose()
    os.unlink(path)
    return {
        "mode": mode, "counters": counters, "problems": problems,
        "divergent": divergent, "div_rows": total_div_rows,
        "div_paid": total_div_paid, "total_cash": total_cash, "n_trades": n_trades,
    }


MODE_LABEL = {
    "live": "LIVE config (app/db.py as-is)",
    "wal": "WAL + busy_timeout (locking only)",
    "serialized": "BEGIN IMMEDIATE (the real fix)",
}


def report(r):
    cfg = MODE_LABEL[r["mode"]]
    c = r["counters"]
    print(f"\n{'='*70}\n  {cfg}\n{'='*70}")
    print(f"  herd buys (90 threads, 1 player, simultaneous): "
          f"{c['herd_ok']} ok / {c['herd_rejected']} rejected / "
          f"{c['herd_FAILED_db_locked']} DB-LOCKED failures")
    print(f"  season trades: {c['buy_ok']} buys + {c['sell_ok']} sells committed, "
          f"{c['rejected_business']} business rejects, "
          f"{c['FAILED_db_locked']} DB-LOCKED failures")
    print(f"  ledger trade rows: {r['n_trades']:,} | dividend rows: {r['div_rows']:,} "
          f"| paid ${r['div_paid']:,} | total cash now ${r['total_cash']:,}")
    if r["problems"]:
        print(f"  INVARIANTS: ❌ {len(r['problems'])} problem(s), "
              f"{r['divergent']} listings corrupted")
        for p in r["problems"][:12]:
            print(f"     - {p}")
    else:
        print("  INVARIANTS: ✅ all held (shares conserved, cash≥0, caps ok, ledger reconciles)")


if __name__ == "__main__":
    print("Simulating a full 18-week season, 100 managers, concurrent trading...")
    results = {}
    for mode in ("live", "wal", "serialized"):
        results[mode] = simulate(mode)
        report(results[mode])
    print(f"\n{'='*70}\n  VERDICT")
    for mode in ("live", "wal", "serialized"):
        r = results[mode]
        dl = r["counters"]["FAILED_db_locked"] + r["counters"]["herd_FAILED_db_locked"]
        held = "HELD ✅" if not r["problems"] else f"BROKE ❌ ({r['divergent']} corrupted listings)"
        print(f"   {MODE_LABEL[mode]:<38} invariants {held}, {dl} db-locked")
    print(f"{'='*70}")
