"""Opening Bell prep (SPEC §3.1): snapshot Sleeper season projections to JSON.

Sums Sleeper's weekly PPR projections for weeks 1-18 into season totals for
every player already synced into the players table, and writes
projections_<season>.json — paste its contents into Commissioner → Opening Bell
(or POST it to /api/admin/opening-bell).

Usage (from backend/, after admin sync-players):
    python scripts/projections_snapshot.py 2026
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Player

BASE = "https://api.sleeper.app/v1"


def main() -> None:
    season = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    with SessionLocal() as session:
        known = set(session.execute(select(Player.id)).scalars())
    if not known:
        print("players table is empty — run the commissioner player sync first")
        return

    totals: dict[str, float] = defaultdict(float)
    with httpx.Client(timeout=60) as client:
        for week in range(1, 19):
            resp = client.get(f"{BASE}/projections/nfl/regular/{season}/{week}")
            resp.raise_for_status()
            data = resp.json()
            n = 0
            for pid, proj in data.items():
                pts = (proj or {}).get("pts_ppr")
                if pts and str(pid) in known:
                    totals[str(pid)] += float(pts)
                    n += 1
            print(f"week {week}: {n} projected players")

    # keep it to fantasy-relevant names; the floor price covers the rest
    snapshot = {pid: round(t, 1) for pid, t in totals.items() if t >= 40}
    out = Path(__file__).resolve().parent.parent / f"projections_{season}.json"
    out.write_text(json.dumps(snapshot, indent=0, sort_keys=True))
    print(f"wrote {len(snapshot)} projections -> {out}")
    if not snapshot:
        print("(empty — Sleeper likely hasn't published projections for that season yet)")


if __name__ == "__main__":
    main()
