"""Probe: does Sleeper's weekly stats endpoint update DURING games? (SPEC §14.2)

The $0 "accrual-lite" path assumes /v1/stats/nfl/regular/{season}/{week} reports
in-progress cumulative pts_ppr, so you can diff successive polls and credit current
holders. This can only be confirmed during a live game — run it Thu/Sun/Mon and
watch for per-poll deltas.

  Offseason  → no games, so no deltas (expected). Plumbing still verifiable against a
               finished week (--season/--week): it should poll and report "no change".
  Live game  → players whose games are in progress should show pts_ppr rising each poll.

Usage (from backend/):
  python scripts/probe_live_stats.py                       # current week, 45s x40
  python scripts/probe_live_stats.py --interval 30 --iters 60
  python scripts/probe_live_stats.py --season 2024 --week 1 --iters 2 --interval 1   # dry-run
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.providers.sleeper import SleeperProvider


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=45.0, help="seconds between polls")
    ap.add_argument("--iters", type=int, default=40)
    ap.add_argument("--season", type=int)
    ap.add_argument("--week", type=int)
    args = ap.parse_args()

    p = SleeperProvider()
    state = p.fetch_state()
    season = args.season or int(state.get("season"))
    week = args.week if args.week is not None else int(state.get("week") or 0)
    print(f"sleeper state: season_type={state.get('season_type')} week={state.get('week')}")
    if state.get("season_type") == "off" and args.week is None:
        print("→ Offseason: no live games. Re-run during a Week-1 game, or pass --season/--week "
              "to dry-run the plumbing against a finished week.")
    if week < 1:
        print("no valid week to poll — exiting.")
        return
    print(f"polling season {season} week {week} every {args.interval}s x{args.iters} …\n")

    last: dict[str, float] = {}
    moves = 0
    for i in range(args.iters):
        try:
            cur = {pid: float(v) for pid, v in p.fetch_week_stats(season, week).items()}
        except Exception as e:  # noqa: BLE001 — probe, keep going
            print(f"[poll {i}] fetch error: {e}")
            time.sleep(args.interval)
            continue
        if last:
            deltas = [(pid, cur[pid] - last.get(pid, 0.0)) for pid in cur
                      if abs(cur[pid] - last.get(pid, 0.0)) > 1e-9]
            if deltas:
                moves += len(deltas)
                top = sorted(deltas, key=lambda d: -abs(d[1]))[:8]
                print(f"[poll {i}] {len(deltas)} players moved: "
                      + ", ".join(f"{pid}{v:+.2f}" for pid, v in top))
            else:
                print(f"[poll {i}] no change")
        else:
            print(f"[poll {i}] baseline: {len(cur)} players with pts_ppr")
        last = cur
        if i < args.iters - 1:
            time.sleep(args.interval)

    print(f"\nVERDICT: {'LIVE IN-GAME UPDATES SEEN — accrual-lite on Sleeper is GO (SPEC §14.6 step 2)' if moves else 'no in-poll changes — offseason, finished week, or the endpoint is post-game only (fall back to ESPN, §14.2)'}")


if __name__ == "__main__":
    main()
