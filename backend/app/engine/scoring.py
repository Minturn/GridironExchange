"""Scoring modes — how a week's fantasy points turn into dividends. A per-league
setting the commissioner picks (SPEC: fix "all QBs win every week").

- MARKET   raw points; every share you hold pays. The QB-heavy baseline.
- RELATIVE points normalized by position, so a QB point and a RB point are worth
           about the same dividend. Keeps "buy anyone, every share pays."
- LINEUP   raw points, but only shares of players in your starting lineup pay —
           one QB slot caps QB dividends, just like a normal league.

Only dividends change between modes; pricing (P0) never does, so switching modes
never re-prices the market or disturbs anyone's positions.
"""
from collections import Counter, defaultdict
from decimal import Decimal

MARKET = "market"
RELATIVE = "relative"
LINEUP = "lineup"
MODES = (MARKET, RELATIVE, LINEUP)

# Relative-mode factors, calibrated from the real 2025 season (per-position avg
# PPR/game among startable players; factor = overall_avg / position_avg). See
# scripts/backtest.py / docs/balance.md. A point scaled by these means the same
# across positions.
POSITION_FACTOR = {
    "QB": Decimal("0.80"),
    "RB": Decimal("0.99"),
    "WR": Decimal("1.07"),
    "TE": Decimal("1.23"),
    "K": Decimal("1.00"),
}


def position_factor(pos: str) -> Decimal:
    return POSITION_FACTOR.get(pos, Decimal("1.00"))


# Standard lineup; FLEX accepts RB/WR/TE. Per-league override lives in settings.
DEFAULT_LINEUP_SLOTS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1}
FLEX_POSITIONS = {"RB", "WR", "TE"}


def lineup_is_valid(chosen: list[dict], slots: dict) -> bool:
    """chosen: [{'id','pos'}, ...]. True if it fits the slots (dedicated + FLEX,
    with QB/non-flex positions unable to spill into FLEX). Blocks cheating like
    starting five QBs."""
    if len(chosen) > sum(slots.values()):
        return False
    if len({c["id"] for c in chosen}) != len(chosen):
        return False  # a player can't fill two slots
    flex = slots.get("FLEX", 0)
    overflow = 0
    for pos, n in Counter(c["pos"] for c in chosen).items():
        dedicated = slots.get(pos, 0)
        if n > dedicated:
            if pos in FLEX_POSITIONS:
                overflow += n - dedicated
            else:
                return False
    return overflow <= flex


def autofill(held: list[dict], slots: dict) -> set:
    """Greedily start a manager's best players (by 'weight') into the slots — used
    when they haven't set a lineup, so passive players still score. held:
    [{'id','pos','weight'}, ...]."""
    ranked = sorted(held, key=lambda c: -c["weight"])
    started, used = set(), set()
    for pos, n in slots.items():
        if pos == "FLEX":
            continue
        for c in ranked:
            if n <= 0:
                break
            if c["pos"] == pos and c["id"] not in used:
                started.add(c["id"])
                used.add(c["id"])
                n -= 1
    flex_n = slots.get("FLEX", 0)
    for c in ranked:
        if flex_n <= 0:
            break
        if c["id"] not in used and c["pos"] in FLEX_POSITIONS:
            started.add(c["id"])
            used.add(c["id"])
            flex_n -= 1
    return started


def effective_starters(held: list[dict], slots: dict, saved: list | None) -> set:
    """The set of a manager's player_ids whose shares pay this week. Uses their
    saved lineup if it's still valid (only players they still hold); otherwise
    auto-starts their best. held: [{'id','pos','weight'}, ...]."""
    by_id = {h["id"]: h for h in held}
    if saved:
        chosen = [by_id[pid] for pid in saved if pid in by_id]
        if chosen and lineup_is_valid(chosen, slots):
            return {c["id"] for c in chosen}
    return autofill(held, slots)


def eligible_slots_for(pos: str, slots: dict) -> list[str]:
    """Which slot keys a given position may fill (for the lineup UI)."""
    out = [pos] if pos in slots else []
    if pos in FLEX_POSITIONS and slots.get("FLEX", 0):
        out.append("FLEX")
    return out


def slot_keys(slots: dict) -> list[str]:
    """Expand slot counts to labelled keys, e.g. QB, RB1, RB2, WR1, WR2, TE, FLEX."""
    order = ["QB", "RB", "WR", "TE", "FLEX", "K"]
    keys = []
    for pos in order:
        n = slots.get(pos, 0)
        if n == 1:
            keys.append(pos)
        elif n > 1:
            keys.extend(f"{pos}{i + 1}" for i in range(n))
    # any non-standard positions
    for pos, n in slots.items():
        if pos not in order:
            keys.extend([pos] if n == 1 else [f"{pos}{i + 1}" for i in range(n)])
    return keys
