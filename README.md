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

**Live on the always-on Synology NAS** (v0.4.0) at **https://gridiron.tail3c5b35.ts.net**
(invite code `kickoff`); nightly DB backup. Setup: [`docs/nas-hosting.md`](docs/nas-hosting.md);
full change log in [`CHANGELOG.md`](CHANGELOG.md).

- [x] Phase 1 — engine: models + migrations, AMM trading, idempotent dividends,
      Sleeper provider, tests (44 total)
- [x] Phase 2 — balance backtest vs. real 2025 season; knobs locked (`docs/balance.md`:
      p0 1.00× · dividend $0.30/pt · slope 12%)
- [x] Phase 3 — "The Floor" UI (:5190): market+ticker, player page + order pad,
      Your Book, Standings, The Tape, Commissioner — **mobile-responsive + add-to-home-screen**
- [x] Phase 5 — season-ready: invite-code auth (case-insensitive), scheduler (nightly
      sync, price snapshots, ESPN game locks, Tuesday settlement), commissioner tools
- [x] Phase 4/6 packaging — Dockerfile + fly.toml + `docs/hosting.md` runbook
      (Tailscale Funnel demo → Fly.io season) + `Run Demo.command` launcher
- [x] **Scoring modes** — commissioner-selectable `market` / `relative` / `lineup`
      (fixes QB dominance); lineup roster + `Lineup` tab; view other managers' rosters;
      commissioner-set Week-1 start time with countdown
- [x] **DEPLOYED** — live on the Synology DS220+ (Container Manager + GHCR image via GitHub
      Actions), public Tailscale Funnel URL, scheduler + nightly backup on; 2 members
- [ ] SEASON — Opening Bell with real projections at kickoff; optional Fly.io / custom
      domain later (`docs/hosting.md`, `docs/nas-hosting.md`)

### Known issues
- Expired/invalid session shows "Loading…" instead of redirecting to sign-in (needs a
  global 401 → login). No GitHub remote yet (local repo only). See `CHANGELOG.md`.
