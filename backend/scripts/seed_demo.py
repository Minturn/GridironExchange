"""Seed a local demo league so /market has something to show.

Usage (from backend/, venv active, after `alembic upgrade head`):
    python scripts/seed_demo.py
"""
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.db import SessionLocal
from app.models import League, Player, User
from app.services.listings import create_listings

DEMO_PLAYERS = [
    # (sleeper-ish id, name, team, pos, projected 2026 season PPR pts)
    ("4034", "Christian McCaffrey", "SF", "RB", "350"),
    ("6786", "Ja'Marr Chase", "CIN", "WR", "357"),
    ("6794", "Justin Jefferson", "MIN", "WR", "328"),
    ("9509", "Bijan Robinson", "ATL", "RB", "316"),
    ("6797", "CeeDee Lamb", "DAL", "WR", "279"),
    ("9226", "Jahmyr Gibbs", "DET", "RB", "298"),
    ("4984", "Josh Allen", "BUF", "QB", "380"),
    ("6770", "Lamar Jackson", "BAL", "QB", "364"),
    ("9493", "Puka Nacua", "LAR", "WR", "270"),
    ("8183", "Brock Purdy", "SF", "QB", "312"),
    ("11566", "Malik Nabers", "NYG", "WR", "252"),
    ("5859", "George Kittle", "SF", "TE", "216"),
    ("5849", "Kyler Murray", "ARI", "QB", "290"),
]


def main() -> None:
    with SessionLocal() as session:
        if session.execute(select(League)).scalars().first():
            print("Already seeded — delete gridx.db to start over.")
            return
        league = League(name="Demo League", invite_code="demo", season_year=2026)
        session.add(league)
        session.flush()
        for name in ("ryan", "sal", "derek", "matty"):
            session.add(
                User(
                    league_id=league.id,
                    username=name,
                    cash=league.rules.starting_cash,
                    is_commissioner=(name == "ryan"),
                )
            )
        for pid, name, team, pos, _ in DEMO_PLAYERS:
            session.add(Player(id=pid, name=name, team=team, pos=pos, status="Active"))
        session.commit()
        projections = {pid: Decimal(proj) for pid, _, _, _, proj in DEMO_PLAYERS}
        n = create_listings(session, league, projections)
        print(f"Seeded league '{league.name}' (id={league.id}), 4 users, {n} listings.")


if __name__ == "__main__":
    main()
