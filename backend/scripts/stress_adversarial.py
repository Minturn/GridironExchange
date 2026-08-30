"""Adversarial concurrency torture — different angles than simulate_season.py.

Each trade uses a FRESH session (exactly like the app's per-request get_session),
and every scenario runs against the SERIALIZED engine config that now ships in
app/db.py (WAL + busy_timeout + BEGIN IMMEDIATE) to see if the fix can be broken
from angles the season sim didn't cover:

  A. one USER hammered by 60 threads at once   (intra-account race on cash/holdings)
  B. opposing BUYS *and* SELLS on one player, simultaneously
  C. cap-boundary hammer — 60 threads, one user, buy the same player (cap=25)
  D. trading concurrently WHILE the weekly dividend run settles cash
  E. buy/sell wash oscillation on one player
  F. full chaos — everything at once

Invariants (must ALL hold):
  shares_outstanding == Σ holdings ·  cash ≥ 0 ·  0 ≤ holding ≤ cap ·
  per-user ledger reconciles ·  GLOBAL money conservation (no cash created/destroyed
  except dividends injected / fees burned).

Scenario C is also run once on the LIVE (unfixed) engine to show it still breaks there.

Usage (from backend/, venv):  python scripts/stress_adversarial.py
"""
import os
import random
import sys
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.auth import hash_password
from app.db import Base
from app.engine import ledger
from app.engine.amm import money
from app.engine.dividends import post_week_dividends
from app.engine.trading import TradeError, execute_trade
from app.models import Dividend, Holding, League, Listing, Player, StatWeek, Trade, User
from app.services.listings import create_listings

SEED = 424242
N_USERS = 100
N_PLAYERS = 60
CAP = 25
START = Decimal("10000.00")


def make_engine(mode: str):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    url = f"sqlite:///{path}"
    if mode == "live":
        return create_engine(url, future=True), path
    eng = create_engine(url, future=True, pool_size=64, max_overflow=32,
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


def fresh_setup(mode):
    eng, path = make_engine(mode)
    Base.metadata.create_all(eng)
    SL = sessionmaker(bind=eng, expire_on_commit=False, future=True)
    rng = random.Random(SEED)
    with SL() as s:
        lg = League(name="Adv", invite_code="adv", season_year=2026,
                    settings_json={"scoring_mode": "market", "in_game_trading": "live",
                                   "starting_cash": str(START), "share_cap": CAP,
                                   "fee_rate": "0.01", "dividend_multiplier": "0.30"})
        s.add(lg); s.flush()
        for i in range(N_USERS):
            s.add(User(league_id=lg.id, username=f"u{i:03d}", pw_hash=hash_password("x"), cash=START))
        players = [f"pp{i:02d}" for i in range(N_PLAYERS)]
        for pid in players:
            s.add(Player(id=pid, name=pid, pos="WR", team="ADV", status="Active"))
        s.commit()
        create_listings(s, lg, {pid: Decimal(rng.randint(60, 300)) for pid in players})
        uids = [r[0] for r in s.execute(select(User.id))]
        return eng, path, SL, lg.id, players, uids


def one_trade(SL, uid, pid, side, shares, tally, clk):
    """Fresh session per trade — mirrors the app's per-request session."""
    s = SL()
    try:
        execute_trade(s, user_id=uid, player_id=pid, side=side, shares=shares)
        with clk:
            tally[f"{side}_ok"] += 1
    except TradeError:
        with clk:
            tally["rejected"] += 1
    except OperationalError:
        s.rollback()
        with clk:
            tally["db_locked"] += 1
    finally:
        s.close()


def run(jobs, workers=48):
    from threading import Lock
    tally, clk = Counter(), Lock()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for fn in jobs:
            pool.submit(fn, tally, clk)
    return tally


def check_all(SL, league_id):
    problems = []
    with SL() as s:
        held = Counter()
        for h in s.execute(select(Holding)).scalars():
            held[h.player_id] += h.shares
            if h.shares < 0:
                problems.append(f"NEG holding u{h.user_id} {h.player_id}={h.shares}")
            if h.shares > CAP:
                problems.append(f"OVER-CAP u{h.user_id} {h.player_id}={h.shares}>{CAP}")
        for l in s.execute(select(Listing)).scalars():
            if l.shares_outstanding != held.get(l.player_id, 0):
                problems.append(f"SHARE DIVERGENCE {l.player_id}: "
                                f"listing={l.shares_outstanding} vs holdings={held.get(l.player_id, 0)}")
        for u in s.execute(select(User)).scalars():
            if u.cash < 0:
                problems.append(f"NEG cash {u.username}={u.cash}")
            rec = ledger.reconcile(s, u, START)
            if not rec.ok:
                problems.append(f"LEDGER DRIFT {u.username} Δ{rec.drift}")
        # global money conservation, computed independently from the ledgers
        def q(v):
            return Decimal(str(v or 0))
        buy_g = q(s.execute(select(func.sum(Trade.gross)).where(Trade.side == "buy")).scalar())
        sell_g = q(s.execute(select(func.sum(Trade.gross)).where(Trade.side == "sell")).scalar())
        fees = q(s.execute(select(func.sum(Trade.fee))).scalar())
        divs = q(s.execute(select(func.sum(Dividend.amount))).scalar())
        actual = money(q(s.execute(select(func.sum(User.cash))).scalar()))
        expected = money(Decimal(N_USERS) * START + sell_g - buy_g - fees + divs)
        if actual != expected:
            problems.append(f"MONEY LEAK: cash={actual} but ledger-expected={expected} (Δ{actual - expected})")
    return problems


def scen(name, SL, league_id, tally):
    problems = check_all(SL, league_id)
    ok = "✅ HELD" if not problems else f"❌ BROKE ({len(problems)})"
    extra = f"  [{dict(tally)}]" if tally else ""
    print(f"  {name:<48} {ok}{extra}")
    for p in problems[:4]:
        print(f"        - {p}")
    return not problems


def seq_seed_holdings(SL, uids, pid, per_user_shares):
    """Give a batch of users some shares of pid, sequentially (setup, not under test)."""
    for uid in uids:
        s = SL()
        try:
            execute_trade(s, user_id=uid, player_id=pid, side="buy", shares=per_user_shares)
        except TradeError:
            pass
        finally:
            s.close()


def main():
    print("ADVERSARIAL CONCURRENCY TORTURE (fresh session per trade, serialized engine)\n")
    all_ok = True

    # A. one user hammered by 60 threads
    eng, path, SL, lid, players, uids = fresh_setup("serialized")
    u = uids[0]
    rng = random.Random(1)
    jobs = [(lambda t, c, p=rng.choice(players), sd=rng.choice(["buy", "buy", "sell"]),
             sh=rng.randint(1, 4): one_trade(SL, u, p, sd, sh, t, c)) for _ in range(60)]
    all_ok &= scen("A. same-user storm (60 threads, 1 account)", SL, lid, run(jobs))
    eng.dispose(); os.unlink(path)

    # B. opposing buys AND sells on one player at once
    eng, path, SL, lid, players, uids = fresh_setup("serialized")
    X = players[0]
    seq_seed_holdings(SL, uids[:40], X, 5)          # 40 holders, 5 each
    jobs = []
    for i in range(80):
        if i % 2 == 0:
            jobs.append(lambda t, c, uid=uids[50 + (i // 2)]: one_trade(SL, uid, X, "buy", 3, t, c))
        else:
            jobs.append(lambda t, c, uid=uids[i // 2]: one_trade(SL, uid, X, "sell", 2, t, c))
    all_ok &= scen("B. opposing buy+sell storm on one player", SL, lid, run(jobs))
    eng.dispose(); os.unlink(path)

    # C. cap-boundary hammer — 60 threads, one user, buy same player 1 share each
    for mode in ("serialized", "live"):
        eng, path, SL, lid, players, uids = fresh_setup(mode)
        X, u = players[0], uids[0]
        jobs = [(lambda t, c: one_trade(SL, u, X, "buy", 1, t, c)) for _ in range(60)]
        tally = run(jobs)
        with SL() as s:
            held = s.execute(select(Holding.shares).where(
                Holding.user_id == u, Holding.player_id == X)).scalar() or 0
        label = f"C. cap hammer 60→1 user ({mode}): holds {held} (want exactly {CAP})"
        problems = check_all(SL, lid)
        cap_ok = (held == CAP) and not problems
        all_ok &= (cap_ok if mode == "serialized" else True)  # live is expected to break
        mark = "✅" if cap_ok else "❌"
        print(f"  {label:<58} {mark}{'  (live expected to break)' if mode=='live' else ''}")
        for p in problems[:4]:
            print(f"        - {p}")
        eng.dispose(); os.unlink(path)

    # D. trade WHILE dividends settle
    eng, path, SL, lid, players, uids = fresh_setup("serialized")
    for pid in players:                              # spread some holdings around first
        seq_seed_holdings(SL, uids[:30], pid, 1)
    with SL() as s:
        lg = s.get(League, lid)
        r = random.Random(7)
        for pid in players:
            s.add(StatWeek(season=lg.season_year, week=1, player_id=pid,
                           pts=Decimal(str(round(r.uniform(0, 30), 2))), is_final=True))
        s.commit()

    def dividend_job(t, c):
        s = SL()
        try:
            post_week_dividends(s, lid, 1)
        finally:
            s.close()
    r2 = random.Random(9)
    jobs = [dividend_job] + [(lambda t, c, uid=r2.choice(uids), p=r2.choice(players),
                              sd=r2.choice(["buy", "sell"]): one_trade(SL, uid, p, sd, 2, t, c))
                             for _ in range(60)]
    all_ok &= scen("D. trade concurrently WHILE dividends settle", SL, lid, run(jobs))
    eng.dispose(); os.unlink(path)

    # E. wash oscillation — same player, alternating buy/sell across threads
    eng, path, SL, lid, players, uids = fresh_setup("serialized")
    X = players[0]
    seq_seed_holdings(SL, uids[:50], X, 4)
    r3 = random.Random(11)
    jobs = [(lambda t, c, uid=r3.choice(uids[:50]), sd=r3.choice(["buy", "sell"]):
             one_trade(SL, uid, X, sd, r3.randint(1, 3), t, c)) for _ in range(120)]
    all_ok &= scen("E. wash oscillation on one player (120 ops)", SL, lid, run(jobs))
    eng.dispose(); os.unlink(path)

    # F. full chaos
    eng, path, SL, lid, players, uids = fresh_setup("serialized")
    r4 = random.Random(13)
    jobs = []
    for _ in range(400):
        uid = uids[0] if r4.random() < 0.15 else r4.choice(uids)   # 15% pile on one account
        pid = players[0] if r4.random() < 0.35 else r4.choice(players)  # hot player
        jobs.append(lambda t, c, uid=uid, pid=pid, sd=r4.choice(["buy", "buy", "sell"]),
                    sh=r4.randint(1, 5): one_trade(SL, uid, pid, sd, sh, t, c))
    all_ok &= scen("F. full chaos (400 concurrent ops)", SL, lid, run(jobs, workers=64))
    eng.dispose(); os.unlink(path)

    print(f"\n{'='*66}\n  OVERALL: {'✅ ALL ANGLES HELD — fix is solid' if all_ok else '❌ SOMETHING BROKE — see above'}\n{'='*66}")


if __name__ == "__main__":
    main()
