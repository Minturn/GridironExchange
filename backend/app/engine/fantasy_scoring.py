"""Fantasy scoring from RAW stat lines — the product-grade, source-resilient path.

Today the sync trusts a provider's precomputed `pts_ppr`. That locks every league
to one format (full PPR) AND to that one vendor's scoring math. Instead, pull the
raw stat primitives — pass_yd, pass_td, rush_td, rec, rec_yd, ... — and apply the
league's own rubric here. Raw stats are the stable, universal layer every stats
source reports (Sleeper, ESPN, nflverse, a paid feed); the rubric lives per-league
in settings_json, so a league can pick a preset or import its real scoring verbatim.

Reliability: because we compute points ourselves, the same rubric reproduces the
provider's own number — verified 100% to the penny against Sleeper's pts_ppr across
a full week (scripts/validate_scoring.py). That cross-check is a *tripwire*: if our
PPR ever stops matching upstream, something in the feed changed and we alert the
commissioner instead of silently paying wrong dividends.

Stat keys follow Sleeper's naming so a league's `scoring_settings` imports 1:1.
"""
from decimal import Decimal, ROUND_HALF_UP

# Offensive skill scoring — this market lists QB/RB/WR/TE. Kicking/defense would add
# their own keys (fgm by distance, def_*, ...) the same way when those positions ship.
_BASE: dict[str, Decimal] = {
    "pass_yd": Decimal("0.04"),   # 1 pt / 25 passing yds
    "pass_td": Decimal("4"),
    "pass_int": Decimal("-1"),
    "pass_2pt": Decimal("2"),
    "rush_yd": Decimal("0.1"),    # 1 pt / 10 rushing yds
    "rush_td": Decimal("6"),
    "rush_2pt": Decimal("2"),
    "rec_yd": Decimal("0.1"),     # 1 pt / 10 receiving yds
    "rec_td": Decimal("6"),
    "rec_2pt": Decimal("2"),
    "fum_lost": Decimal("-2"),
    "fum_rec_td": Decimal("6"),
}

# Canned rubrics. The only knob that separates the three standard formats is `rec`.
PRESETS: dict[str, dict[str, Decimal]] = {
    "ppr": {**_BASE, "rec": Decimal("1")},
    "half_ppr": {**_BASE, "rec": Decimal("0.5")},
    "std": {**_BASE, "rec": Decimal("0")},
}

PRESET_LABELS = {
    "ppr": "Full PPR",
    "half_ppr": "Half PPR",
    "std": "Standard (non-PPR)",
    "custom": "Custom (imported)",
}

_CENT = Decimal("0.01")


def rubric_for(fmt: str | None) -> dict[str, Decimal]:
    """A league's rubric. A preset name yields the canned rubric; anything else
    falls back to full PPR (the safe default the pilot launched on)."""
    return PRESETS.get((fmt or "ppr"), PRESETS["ppr"])


def resolve_rubric(scoring_format: str | None, custom: dict | None) -> dict[str, Decimal]:
    """A league's actual rubric: an imported custom map wins over the format preset.
    Custom values arrive as JSON strings (Decimal-safe) and are coerced back here."""
    if custom:
        return {k: Decimal(str(v)) for k, v in custom.items()}
    return rubric_for(scoring_format)


def sleeper_to_rubric(scoring_settings: dict) -> dict[str, Decimal]:
    """Map a Sleeper league's `scoring_settings` to a rubric. Sleeper uses the same
    stat keys we score (pass_yd, rec, rush_td, bonus_*, ...), so this is a coerce +
    drop-zeros — importing a real league mirrors its exact scoring, bonuses included."""
    return {
        str(k): Decimal(str(v))
        for k, v in scoring_settings.items()
        if isinstance(v, (int, float)) and Decimal(str(v)) != 0
    }


def score(raw: dict, rubric: dict[str, Decimal]) -> Decimal:
    """Weekly fantasy points = Σ (rubric[stat] × raw[stat]). Missing/zero stats
    contribute nothing. Result is quantized to cents, matching StatWeek.pts."""
    total = Decimal("0")
    for key, pts in rubric.items():
        v = raw.get(key)
        if v:
            total += Decimal(str(v)) * Decimal(str(pts))
    return total.quantize(_CENT, rounding=ROUND_HALF_UP)


def score_preset(raw: dict, fmt: str | None) -> Decimal:
    """Convenience: score a raw line with a named preset (ppr/half_ppr/std)."""
    return score(raw, rubric_for(fmt))
