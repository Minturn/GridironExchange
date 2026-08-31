"""Sleeper API provider — free, no key (SPEC §5).

Endpoints (unofficial but long-stable):
  GET /v1/players/nfl                          all players (big; sync nightly, not per request)
  GET /v1/stats/nfl/regular/{season}/{week}    weekly stats incl. pts_ppr

Preseason projections for P0 seeding are deliberately NOT wired here yet — Phase 6
snapshots them once at Opening Bell (Sleeper projections or a FantasyPros CSV);
services/listings.py takes a plain {player_id: season_pts} mapping so the source
stays swappable.
"""
from decimal import Decimal

import httpx

from app.providers import PlayerRecord

BASE = "https://api.sleeper.app/v1"
FANTASY_POSITIONS = {"QB", "RB", "WR", "TE", "K"}


class SleeperProvider:
    def __init__(self, client: httpx.Client | None = None):
        self._client = client or httpx.Client(timeout=60)

    def fetch_players(self) -> list[PlayerRecord]:
        raw = self._get(f"{BASE}/players/nfl")
        out: list[PlayerRecord] = []
        for pid, p in raw.items():
            if p.get("position") not in FANTASY_POSITIONS:
                continue
            if p.get("status") not in ("Active", "Injured Reserve", "PUP", "Questionable"):
                continue
            name = p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
            if not name:
                continue
            out.append(
                PlayerRecord(
                    id=str(pid),
                    name=name,
                    team=p.get("team"),
                    pos=p["position"],
                    status=p.get("status"),
                )
            )
        return out

    def fetch_week_stats(self, season: int, week: int) -> dict[str, Decimal]:
        raw = self._get(f"{BASE}/stats/nfl/regular/{season}/{week}")
        return {
            str(pid): Decimal(str(stats["pts_ppr"]))
            for pid, stats in raw.items()
            if isinstance(stats, dict) and stats.get("pts_ppr") is not None
        }

    def fetch_week_raw(self, season: int, week: int) -> dict[str, dict]:
        """player_id -> raw stat line. Same endpoint as fetch_week_stats; we keep the
        raw fields (pass_yd, rush_td, rec, ...) and score them ourselves. Sleeper's
        cumulative /stats updates in-progress during games, which is what makes it
        usable for live accrual — verify at Week 1 (scripts/probe_live_stats.py)."""
        raw = self._get(f"{BASE}/stats/nfl/regular/{season}/{week}")
        return {
            str(pid): stats
            for pid, stats in raw.items()
            if isinstance(stats, dict)
        }

    def fetch_league_scoring(self, league_id: str) -> dict:
        """A Sleeper league's scoring_settings ({stat_key: points}) — used to mirror an
        existing league's exact scoring in one step. Keys match our raw stat keys."""
        lg = self._get(f"{BASE}/league/{league_id}")
        return lg.get("scoring_settings") or {}

    def fetch_state(self) -> dict:
        """{'week': int, 'season_type': 'regular'|'pre'|'post', 'season': str, ...}"""
        return self._get(f"{BASE}/state/nfl")

    def _get(self, url: str):
        resp = self._client.get(url)
        resp.raise_for_status()
        return resp.json()
