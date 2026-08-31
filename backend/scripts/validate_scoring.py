"""Source tripwire: prove our scoring engine reproduces the provider's own numbers.

Pulls a real Sleeper stats week, scores every offensive player from RAW stats with
our PPR rubric, and asserts it matches Sleeper's precomputed `pts_ppr` to the penny.

Why it matters: this is how we "always get the correct stats." If the feed's shape
changes (renamed fields, new bonuses, a broken endpoint), our computed PPR stops
matching `pts_ppr` and this fails LOUD — so we catch it before a Tuesday dividend
run pays wrong. Run it after any provider change, and it's cheap enough for CI /
a weekly cron. Stdlib only (urllib) so it has no runtime deps.

Usage (from backend/):
    python scripts/validate_scoring.py            # default season/week
    python scripts/validate_scoring.py 2024 1
"""
import json
import sys
import urllib.request
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine.fantasy_scoring import PRESETS, score  # noqa: E402

# offensive lines only — this market lists QB/RB/WR/TE, not K/DEF/IDP
_NON_OFFENSE_PREFIX = (
    "fgm", "fga", "xpm", "xpa", "def_", "st_", "idp_", "sack", "ff", "tkl",
    "blk", "safe", "int_ret", "fum_ret", "kr", "pr", "pass_def",
)


def fetch_week(season: int, week: int) -> dict:
    url = f"https://api.sleeper.app/v1/stats/nfl/regular/{season}/{week}"
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def main() -> int:
    season = int(sys.argv[1]) if len(sys.argv) > 1 else 2024
    week = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    data = fetch_week(season, week)

    checked = exact = 0
    mismatches = []
    for pid, s in data.items():
        if not isinstance(s, dict) or s.get("pts_ppr") is None:
            continue
        if any(k.startswith(_NON_OFFENSE_PREFIX) for k in s):
            continue
        checked += 1
        ours = score(s, PRESETS["ppr"])
        theirs = Decimal(str(s["pts_ppr"]))
        if ours == theirs:
            exact += 1
        else:
            mismatches.append((pid, ours, theirs, ours - theirs))

    print(f"Sleeper {season} wk{week}: {checked} offensive players checked")
    print(f"  our PPR == Sleeper pts_ppr (to the penny): {exact}/{checked}"
          f"  ({100 * exact / checked:.1f}%)" if checked else "  no players")
    for pid, ours, theirs, d in mismatches[:10]:
        print(f"    MISMATCH {pid}: ours={ours} theirs={theirs} (Δ{d})")

    ok = checked > 0 and not mismatches
    print("\nRESULT:", "PASS — engine reproduces the feed exactly ✅" if ok
          else "FAIL — feed shape or rubric drifted ❌")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
