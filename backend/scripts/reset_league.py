"""Reset the league to a clean opening state — wipes all members and every trade,
dividend, and price tick, and puts the market back to opening (every player at its
IPO price, nobody holding anything). Keeps the player listings so there's a live
market to trade the moment people join.

Turn the demo into a real league: run this, then YOU register first (the first
member to register becomes commissioner) and hand out the invite code.

Usage (from backend/):
    python scripts/reset_league.py                          # wipe members, keep name + invite code
    python scripts/reset_league.py --name "Sunday Money" --invite kickoff
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, update

from app.db import SessionLocal
from app.models import Dividend, Holding, League, Listing, PriceHistory, Trade, User


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", help="rename the league")
    ap.add_argument("--invite", help="set a new invite code friends will type to join")
    args = ap.parse_args()

    with SessionLocal() as s:
        league = s.query(League).first()
        if league is None:
            print("No league found — run scripts/seed_demo.py first.")
            return
        # wipe every member + all trading history
        s.execute(delete(Trade))
        s.execute(delete(Dividend))
        s.execute(delete(PriceHistory))
        s.execute(delete(Holding))
        s.execute(delete(User))
        # market back to opening: every player at its IPO price, nobody holding
        s.execute(update(Listing).values(shares_outstanding=0, locked_until=None))
        # clear any scheduled Week-1 start time
        if league.settings_json and "market_opens_at" in league.settings_json:
            cleaned = dict(league.settings_json)
            cleaned.pop("market_opens_at", None)
            league.settings_json = cleaned
        if args.name:
            league.name = args.name
        if args.invite:
            league.invite_code = args.invite
        s.commit()
        listings = s.query(Listing).count()
        print(f"League '{league.name}' reset to a clean opening state.")
        print(f"  invite code : {league.invite_code}")
        print(f"  members     : 0  (register first to claim commissioner)")
        print(f"  market      : {listings} players, all at opening price, 0 shares held")


if __name__ == "__main__":
    main()
