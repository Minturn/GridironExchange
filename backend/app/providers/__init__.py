"""Every external feed lives behind this interface (SPEC §5) — the product version
swaps in a paid live-scoring provider by implementing the same three methods."""
from decimal import Decimal
from typing import Protocol, TypedDict


class PlayerRecord(TypedDict):
    id: str
    name: str
    team: str | None
    pos: str
    status: str | None


class StatsProvider(Protocol):
    def fetch_players(self) -> list[PlayerRecord]: ...

    def fetch_week_stats(self, season: int, week: int) -> dict[str, Decimal]:
        """player_id -> PPR fantasy points for the week."""
        ...

    def fetch_week_raw(self, season: int, week: int) -> dict[str, dict]:
        """player_id -> raw stat line (pass_yd, rush_td, rec, ...). The stable,
        universal layer we score ourselves via app/engine/fantasy_scoring.py, so
        scoring is per-league and not hostage to the feed's precomputed points.
        Works for a final box score or an in-progress one (drives live accrual)."""
        ...
