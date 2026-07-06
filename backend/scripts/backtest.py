"""Phase 2 — balance backtest (SPEC §4).

Replays the 2025 season (nflverse weekly PPR points) through the REAL engine —
same ORM, same execute_trade, same dividend run — with 12 scripted bot
personalities, across a grid of economy knobs. Prints a table and a
recommendation against the SPEC §4 criteria:

  * median bot return ≈ +20–30%, top decile ≈ +80%
  * no strategy strictly dominates
  * a week-1 all-in on one player is survivable but clearly punished

Usage (from backend/):  python scripts/backtest.py [--grid]
Default runs the recommended knobs only; --grid sweeps the full grid.
"""
import argparse
import csv
import random
import statistics
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.engine.amm import sell_gross
from app.engine.dividends import post_week_dividends
from app.engine.trading import TradeError, execute_trade
from app.models import Holding, League, Listing, Player, StatWeek, User

DATA = Path(__file__).resolve().parent.parent / "data" / "stats_player_week_2025.csv"
POSITIONS = {"QB", "RB", "WR", "TE", "K"}
WEEKS = range(1, 19)
UNIVERSE = 200  # top-N by season pts — the fantasy-relevant market


def load_season():
    pts: dict[str, dict[int, Decimal]] = defaultdict(dict)
    names: dict[str, tuple[str, str]] = {}
    with open(DATA) as f:
        for row in csv.DictReader(f):
            if row["season_type"] != "REG" or row["position"] not in POSITIONS:
                continue
            week = int(row["week"])
            if week not in WEEKS or not row["fantasy_points_ppr"]:
                continue
            pid = row["player_id"]
            pts[pid][week] = Decimal(row["fantasy_points_ppr"]).quantize(Decimal("0.01"))
            names[pid] = (row["player_display_name"], row["position"])
    totals = {pid: sum(w.values()) for pid, w in pts.items()}
    top = sorted(totals, key=totals.get, reverse=True)[:UNIVERSE]
    return {p: pts[p] for p in top}, {p: names[p] for p in top}, {p: totals[p] for p in top}


# --- bot personalities ----------------------------------------------------------
# Each is f(session, user, ctx) called once per week AFTER dividends post.
# ctx: week, listings {pid: Listing}, last_week_pts {pid: pts}, price_delta {pid: Δ%}


def _try(session, user, pid, side, n):
    if n <= 0:
        return
    try:
        execute_trade(session, user_id=user.id, player_id=pid, side=side, shares=n)
    except TradeError:
        pass


def _affordable(user, listing, want):
    # rough shares affordable at spot+slope drift, conservative
    px = float(listing.p0) + float(listing.slope) * listing.shares_outstanding
    n = int(float(user.cash) * 0.98 / (px * 1.02)) if px > 0 else 0
    return min(want, n)


def bot_chalk(session, user, ctx):
    if ctx["week"] != 1:
        return
    ranked = sorted(ctx["proj"], key=ctx["proj"].get, reverse=True)[:8]
    for pid in ranked:
        _try(session, user, pid, "buy", _affordable(user, ctx["listings"][pid], 12))


def bot_indexer(session, user, ctx):
    if ctx["week"] != 1:
        return
    ranked = sorted(ctx["proj"], key=ctx["proj"].get, reverse=True)[:40]
    for pid in ranked:
        _try(session, user, pid, "buy", _affordable(user, ctx["listings"][pid], 3))


def bot_streamer(session, user, ctx):
    session.expire_all()
    for h in session.query(Holding).filter_by(user_id=user.id).all():
        if h.shares > 0 and ctx["last_pts"].get(h.player_id, Decimal(0)) < 8:
            _try(session, user, h.player_id, "sell", h.shares)
    hot = sorted(ctx["last_pts"], key=ctx["last_pts"].get, reverse=True)[:5]
    for pid in hot:
        if pid in ctx["listings"]:
            _try(session, user, pid, "buy", _affordable(user, ctx["listings"][pid], 6))


def bot_momentum(session, user, ctx):
    for h in session.query(Holding).filter_by(user_id=user.id).all():
        if h.shares > 0 and ctx["delta"].get(h.player_id, 0) < -0.04:
            _try(session, user, h.player_id, "sell", h.shares)
    rising = sorted(ctx["delta"], key=ctx["delta"].get, reverse=True)[:4]
    for pid in rising:
        _try(session, user, pid, "buy", _affordable(user, ctx["listings"][pid], 8))


def bot_contrarian(session, user, ctx):
    dippers = sorted(ctx["delta"], key=ctx["delta"].get)[:4]
    for pid in dippers:
        if ctx["proj"].get(pid, 0) > 0:
            _try(session, user, pid, "buy", _affordable(user, ctx["listings"][pid], 8))
    for h in session.query(Holding).filter_by(user_id=user.id).all():
        if h.shares > 0 and ctx["delta"].get(h.player_id, 0) > 0.06:
            _try(session, user, h.player_id, "sell", h.shares // 2)


def bot_allin(session, user, ctx):
    # the degenerate case SPEC §4 wants punished-but-survivable
    if ctx["week"] != 1:
        return
    best = max(ctx["proj"], key=ctx["proj"].get)
    _try(session, user, best, "buy", 25)
    second = sorted(ctx["proj"], key=ctx["proj"].get, reverse=True)[1]
    _try(session, user, second, "buy", _affordable(user, ctx["listings"][second], 25))


BOTS = [
    ("chalk-1", bot_chalk), ("chalk-2", bot_chalk),
    ("index-1", bot_indexer), ("index-2", bot_indexer),
    ("stream-1", bot_streamer), ("stream-2", bot_streamer), ("stream-3", bot_streamer),
    ("momo-1", bot_momentum), ("momo-2", bot_momentum),
    ("contra-1", bot_contrarian), ("contra-2", bot_contrarian),
    ("allin-1", bot_allin),
]


def net_worth(session, user, listings):
    session.expire_all()
    total = user.cash
    for h in session.query(Holding).filter_by(user_id=user.id).all():
        if h.shares > 0:
            l = listings[h.player_id]
            total += sell_gross(l.p0, l.slope, l.shares_outstanding, h.shares)
    return total


def run_sim(weekly, totals, knobs, seed):
    rng = random.Random(seed)
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        league = League(
            name="BT", invite_code=f"bt{seed}", season_year=2025,
            settings_json={k: str(v) for k, v in knobs.items()},
        )
        session.add(league)
        session.flush()
        users = []
        for name, _ in BOTS:
            u = User(league_id=league.id, username=name, cash=Decimal("10000.00"))
            session.add(u)
            users.append(u)
        # projections = actual season total × forecast noise (we don't have real
        # preseason 2025 projections; ±25% lognormal-ish noise models forecast error)
        proj = {
            pid: float(t) * rng.uniform(0.75, 1.25) for pid, t in totals.items()
        }
        rules = league.rules
        listings = {}
        for pid in weekly:
            session.add(Player(id=pid, name=pid, pos="X", status="Active"))
        session.flush()
        from app.services.listings import create_listings

        create_listings(
            session, league, {pid: Decimal(str(round(p, 2))) for pid, p in proj.items()}
        )
        for l in session.query(Listing).filter_by(league_id=league.id):
            listings[l.player_id] = l

        last_prices = {
            pid: float(l.p0) for pid, l in listings.items()
        }
        last_pts: dict[str, Decimal] = {}
        for week in WEEKS:
            # bots trade on info available BEFORE this week's games
            session.expire_all()
            delta = {}
            for pid, l in listings.items():
                px = float(l.p0) + float(l.slope) * l.shares_outstanding
                delta[pid] = (px - last_prices[pid]) / last_prices[pid] if last_prices[pid] else 0
                last_prices[pid] = px
            ctx = {
                "week": week, "listings": listings, "proj": proj,
                "last_pts": last_pts, "delta": delta,
            }
            order = list(zip(users, BOTS))
            rng.shuffle(order)
            for user, (_, fn) in order:
                fn(session, user, ctx)
            # games play out; stats post final; dividends run
            wk_pts = {pid: w.get(week, Decimal(0)) for pid, w in weekly.items()}
            for pid, p in wk_pts.items():
                session.add(
                    StatWeek(season=2025, week=week, player_id=pid, pts=p, is_final=True)
                )
            session.commit()
            post_week_dividends(session, league.id, week)
            last_pts = wk_pts

        results = {}
        for user, (name, fn) in zip(users, BOTS):
            nw = net_worth(session, user, listings)
            results[name] = float(nw) / 10000.0 - 1.0
        max_px = max(
            float(l.p0) + float(l.slope) * l.shares_outstanding for l in listings.values()
        )
        return results, max_px


def summarize(all_results):
    per_bot = defaultdict(list)
    everything = []
    for res in all_results:
        for name, r in res.items():
            per_bot[name.rsplit("-", 1)[0]].append(r)
            everything.append(r)
    everything.sort()
    med = statistics.median(everything)
    top_decile = everything[int(len(everything) * 0.9)]
    strat = {k: statistics.mean(v) for k, v in per_bot.items()}
    return med, top_decile, strat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", action="store_true")
    args = ap.parse_args()

    weekly, names, totals = load_season()
    print(f"Loaded {len(weekly)} players from 2025 REG weeks 1-18.\n")

    if args.grid:
        combos = [
            {"p0_factor": p, "dividend_multiplier": d, "slope_pct": s}
            for p, d in (
                ("0.50", "0.15"),
                ("0.75", "0.22"),
                ("0.75", "0.30"),
                ("1.00", "0.30"),
                ("1.00", "0.40"),
                ("1.25", "0.40"),
            )
            for s in ("0.08", "0.12")
        ]
    else:
        # the locked Phase 2 knobs (= DEFAULT_RULES) — see docs/balance.md
        combos = [{"p0_factor": "1.00", "dividend_multiplier": "0.30", "slope_pct": "0.12"}]

    print(f"{'p0':>5} {'div':>5} {'slope':>6} | {'median':>7} {'top10%':>7} {'maxPx':>8} | per-strategy mean return")
    print("-" * 100)
    for knobs in combos:
        runs, max_px = [], 0.0
        for seed in (1, 2, 3):
            res, mp = run_sim(weekly, totals, knobs, seed)
            runs.append(res)
            max_px = max(max_px, mp)
        med, top, strat = summarize(runs)
        strat_s = "  ".join(f"{k}:{v:+.0%}" for k, v in sorted(strat.items()))
        print(
            f"{knobs.get('p0_factor', '0.50'):>5} {knobs['dividend_multiplier']:>5} {knobs['slope_pct']:>6} |"
            f" {med:+7.1%} {top:+7.1%} {max_px:8.0f} | {strat_s}"
        )


if __name__ == "__main__":
    main()
