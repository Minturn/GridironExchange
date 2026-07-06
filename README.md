# Gridiron Exchange

Fantasy football where the players trade like stocks. Full design: [SPEC.md](SPEC.md).
UI direction mock: `docs/mock/the-floor.html` ("The Floor").

**League money only — never real currency.**

## Backend quickstart

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

alembic upgrade head           # creates gridx.db (SQLite locally)
python scripts/seed_demo.py    # demo league, 4 users, 13 listings
uvicorn app.main:app --port 8200
```

Poke it:

```bash
curl 'localhost:8200/market?league_id=1'
curl -X POST localhost:8200/trade -H 'content-type: application/json' \
     -d '{"user_id":1,"player_id":"4034","side":"buy","shares":10}'
curl localhost:8200/portfolio/1
```

Tests: `pytest` (from `backend/`).

## Layout

```
backend/
  app/
    engine/      AMM math, trade execution, dividend run — the game
    providers/   external feeds (Sleeper) behind one interface
    services/    sync jobs, Opening Bell listing creation
    main.py      FastAPI on :8200
  migrations/    Alembic — schema source of truth
  tests/         engine-invariant suite (SPEC §6.1)
docs/mock/       "The Floor" UI mock (49ers colors; gold=up, scarlet=down; no monospace)
```

## Status

- [x] Phase 1 — engine: models + migration 0001, AMM trading, idempotent dividends,
      Sleeper provider, tests
- [ ] Phase 2 — balance backtest vs. 2025 (nflverse); lock the knobs
- [ ] Phase 3 — "The Floor" UI (:5190)
- [ ] Phase 4 — friends demo via Tailscale Funnel
- [ ] Phase 5 — season-ready on Fly.io (auth, invites, scheduler, game locks)
- [ ] Phase 6 — Opening Bell (Sep 1, 2026)
