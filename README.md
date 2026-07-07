# Gridiron Exchange

Fantasy football where the players trade like stocks. Full design: [SPEC.md](SPEC.md).
UI direction mock: `docs/mock/the-floor.html` ("The Floor").

**League money only — never real currency.**

## Dev quickstart

```bash
# backend (:8200) — use Homebrew python3.13, system python is 3.9
cd backend
/opt/homebrew/bin/python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head           # creates gridx.db (SQLite locally)
python scripts/seed_demo.py    # demo league · logins ryan/sal/derek/matty · pw demo123 · invite 'demo'
uvicorn app.main:app --port 8200

# frontend dev server (:5190, proxies /api -> :8200) — separate tab
cd frontend && npm install && npm run dev
```

Open http://localhost:5190. For a one-process setup (demo/prod), `npm run build`
once — the backend serves `frontend/dist` at `/` so :8200 is the whole app.

**Showing friends?** Just double-click **`Run Demo.command`** (builds, seeds,
keeps the Mac awake, serves on :8200), then `tailscale funnel 8200` to get a
public link. Full walkthrough: `docs/hosting.md` → Phase A.

Tests: `pytest` (from `backend/`, 32 tests). Balance backtest:
`python scripts/backtest.py` (see `docs/balance.md`). Hosting: `docs/hosting.md`.

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
- [x] Phase 2 — balance backtest vs. real 2025 season; knobs locked (`docs/balance.md`:
      p0 1.00× · dividend $0.30/pt · slope 12%)
- [x] Phase 3 — "The Floor" UI (:5190): market+ticker, player page + order pad,
      Your Book, Standings, The Tape, Commissioner
- [x] Phase 5 — season-ready: invite-code auth, scheduler (nightly sync, price
      snapshots, ESPN game locks, Tuesday settlement), commissioner tools
- [x] Phase 4/6 packaging — Dockerfile + fly.toml + `docs/hosting.md` runbook
      (Tailscale Funnel demo → Fly.io season) + `scripts/projections_snapshot.py`
- [ ] OPERATIONAL — demo to friends (Phase A), Fly.io launch (Phase B),
      Opening Bell Sep 1, 2026 (checklist at the end of `docs/hosting.md`)
