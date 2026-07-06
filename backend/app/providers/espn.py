"""ESPN public scoreboard — kickoff times for the game-lock job (SPEC §3.4).

Sleeper has no public schedule endpoint; ESPN's scoreboard is the long-standing
free source. Only used to decide WHEN to lock trading, never for scoring.
"""
from datetime import datetime

import httpx

SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"

# ESPN team abbreviations that differ from Sleeper's
_TEAM_MAP = {"WSH": "WAS", "LA": "LAR"}


def _norm(abbr: str) -> str:
    return _TEAM_MAP.get(abbr, abbr)


class EspnSchedule:
    def __init__(self, client: httpx.Client | None = None):
        self._client = client or httpx.Client(timeout=30)

    def current_week_games(self) -> list[dict]:
        """[{kickoff: naive-UTC datetime, teams: [abbr, abbr], state: str}, ...]"""
        resp = self._client.get(SCOREBOARD)
        resp.raise_for_status()
        data = resp.json()
        games = []
        for ev in data.get("events", []):
            try:
                kickoff = datetime.strptime(ev["date"], "%Y-%m-%dT%H:%MZ")
            except ValueError:
                kickoff = datetime.strptime(ev["date"], "%Y-%m-%dT%H:%M:%SZ")
            comp = ev["competitions"][0]
            teams = [_norm(c["team"]["abbreviation"]) for c in comp["competitors"]]
            state = ev.get("status", {}).get("type", {}).get("state", "pre")
            games.append({"kickoff": kickoff, "teams": teams, "state": state})
        return games

    def current_week(self) -> int | None:
        resp = self._client.get(SCOREBOARD)
        resp.raise_for_status()
        return resp.json().get("week", {}).get("number")
