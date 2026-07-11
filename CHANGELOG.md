# Changelog

Dates are when work shipped to the live demo (Tailscale Funnel, served from the Mac).
League money only — never real currency.

## 2026-07-09 — v0.5.0: live in-game trading + scoring visibility + dividend record-date

Moves the pilot toward the product's marquee feature (live trading) safely, and makes the
scoring rules visible to players. Requires the `0003_holding_snapshot` migration (runs on
boot). Existing behavior is unchanged until the game-lock job starts writing snapshots.

### Scoring visibility (UI)
- New masthead **Scoring** chip → a "How Scoring Works" modal explaining market / relative /
  lineup and what each does to your dividends. `/api/state` now returns `dividend_multiplier`
  and `in_game_trading`.
- Commissioner shows the **current** scoring mode and dividend rate (dropdown pre-selects the
  active mode instead of a blank "choose…"), with a mid-season-change warning.

### Dividend record-date (engine)
- New `holding_snapshots` table + `snapshot_holdings()`: the game-lock job records who holds a
  player **at his kickoff**, and `post_week_dividends` pays off that snapshot when present
  (falls back to live holdings otherwise). Closes the Tue 13:00–13:10 dividend-sniping gap and
  makes live trading safe — you earn a player's points by owning him before his game.

### Live in-game trading (commissioner toggle)
- League setting `in_game_trading` = `locked` (default; stock freezes at kickoff) or `live`
  (stays tradeable during games — panic-sell the injury, chase the hot hand). Dividends settle
  by the kickoff snapshot either way. A "● Live" masthead badge shows when it's on. Real-time
  point *accrual* (buy at halftime, earn the second half) still needs a paid live feed —
  deliberately deferred; this is the free, NAS-hostable version.

## 2026-07-08 — deployed to the Synology NAS + nightly DB backup

Went live on the always-on NAS (no app-version bump — infrastructure + one internal job).

### Hosting (live)
- Running on the **Synology DS220+** via Container Manager, pulling the GHCR image built by
  GitHub Actions. **Public URL `https://gridiron.tail3c5b35.ts.net`** (Tailscale Funnel from
  the NAS; device renamed home→gridiron). Scheduler on; league DB on the NAS volume.
- Managed over Tailscale — the home LAN isolates the Mac from the NAS (a UniFi/Policy-Engine
  issue tied to IoT-network isolation, unrelated to the app); Tailscale tunnels around it.
- Deployed-reality gotchas captured in `docs/nas-hosting.md` (GHCR package must be public;
  Synology has SFTP off so write files via `cat | ssh 'cat >'`; home-dir perms block SSH keys;
  funnel needs root/operator).

### Added
- **Nightly DB backup** — `app/jobs.py` `job_backup_db` (08:30 UTC): a consistent SQLite
  snapshot to `data/backups/`, keeping the last 14. The league DB lives only on the NAS disk,
  so this is its safety net. Plus a one-off manual snapshot taken at deploy.

## 2026-07-06 — v0.4.0 · search/filters, version check, commissioner dials, NAS hosting

App 0.3.0 → 0.4.0. No migration. Deployed live.

### Added
- **The Floor:** search (player/team) + position filter chips (ALL/QB/RB/WR/TE).
- **Lineup:** sorted by position; tap **↗** to open a player and buy/sell; shows the roster
  requirements and a **✓ full / X of 8 set** status.
- **Manager view:** a ★ marks the players in each manager's starting lineup.
- **Version check:** a version chip + **What's New** modal (`releaseNotes.ts`); a stale bundle
  shows an **update ⟳** nudge (frontend `APP_VERSION` vs `/api/state` version).
- **Commissioner:** searchable stat correction; adjustable **dividend rate**
  (`/api/admin/rules`); scoring-mode selector.
- Demo roster set to **1 QB · 2 RB · 3 WR · 1 TE · 1 FLEX**.
- **Synology NAS hosting:** `docker-compose.yml` + `docs/nas-hosting.md` (DS220+ /
  Container Manager, always-on, Tailscale funnel from the NAS).

### Fixed
- `index.html` now served with `Cache-Control: no-store` so phones always load the latest
  bundle — fixes the stale-version problem where updates didn't appear.

## 2026-07-06 — v0.3.0 · scoring modes, lineups, mobile, live demo

App version 0.2.0 → 0.3.0. **Migration `0002`** (adds `users.lineup_json`, nullable —
a null lineup means "auto-start my best players", so no backfill needed). Deployed live;
demo league in **lineup** mode. Backend suite: 44 tests green; `tsc` clean.

### Added
- **Selectable scoring modes** — per-league, commissioner picks (Commissioner → Scoring
  mode). Modes only change how dividends are scored; they **never re-price the market**,
  so switching is safe and doesn't disturb anyone's positions.
  - `market` — every held share pays raw fantasy points (the baseline; QB-heavy).
  - `relative` — points normalized by position (QB ×0.80, RB ×0.99, WR ×1.07, TE ×1.23,
    calibrated from the real 2025 season), so a share of each position pays about the same.
  - `lineup` — only shares of your starting-lineup players pay; a single QB slot caps QB
    dividends like a normal league. Managers set a lineup on the new **Lineup** tab; if
    unset, their best players auto-start so they're never zeroed.
  - Files: `app/engine/scoring.py`, `app/engine/dividends.py` (mode branch),
    `routes/market.py` (`/api/lineup`), `routes/admin.py` (`/api/admin/scoring-mode`),
    `frontend/src/pages/Lineup.tsx`.
  - **Demo league** runs `lineup`, roster **1 QB / 2 RB / 2 WR / 1 TE / 1 FLEX**.
- **Commissioner-set Week-1 start time** — locks the market until a set time, shows a live
  countdown to everyone, opens for the whole league at once (kills the early-bird edge).
  `/api/admin/open-time`, `market_opens_at` in league settings, `OpeningBell.tsx`.
- **See other managers' rosters** — tap a name on Standings or in a player's "Held by"
  list. `/api/manager/{username}`, `ManagerPage.tsx`.
- **Mobile / phone support** — responsive layout (single column, horizontally-scrolling
  nav, trimmed market/book tables), safe-area insets for the notch / Dynamic Island, and
  add-to-home-screen (PWA `manifest.json` + PNG "GX" app icons in `frontend/public/`).
- **Tight ends** added to the demo market (Bowers, McBride, LaPorta, Kittle) so the TE
  slot is fillable.

### Changed
- Login is **case-insensitive** (`func.lower(username)`) — phone auto-capitalization no
  longer locks people out; names differing only by case can't both register.
- Persistent session secret in `backend/.env` (written by `Run Demo.command`) — restarting
  the app no longer logs everyone out.
- `Run Demo.command` one-tap launcher builds the UI, seeds, keeps the Mac awake
  (`caffeinate`), and serves the whole app on :8200.
- `scripts/reset_league.py` — wipe members + reset the market to opening (keeps listings),
  optionally rename / re-invite. First to register after a reset becomes commissioner.

### Fixed
- **Top bar hid under the status bar / Dynamic Island** on phones (from the full-bleed
  `viewport-fit=cover`) — added `env(safe-area-inset-*)` padding to the masthead. Confirmed
  on device.
- `MarketLocked` message reworded generically (covers opening-bell, game-lock, and pause).

### Known issues / follow-ups
- **Expired/invalid session shows an endless "Loading…"** instead of bouncing to sign-in —
  a dropped session reads as a hang (surfaced when a logged-in account was deleted). Fix:
  a global 401 → login redirect. **Not yet done.**
- The macOS `tailscale` CLI crashes if run via a symlink ("bundleIdentifier unknown to the
  registry"); call it by full path (`/Applications/Tailscale.app/Contents/MacOS/Tailscale`)
  or alias it. Workaround documented in the Commissioner Handbook.
- No GitHub remote yet — the repo is **local only**. Run `gh repo create` before doing the
  two-machine (desktop/laptop) workflow.
- Relative mode changes dividends but not P0, so the market re-prices itself after a mode
  switch (intended — the market finds the new price — but worth watching in play).

---

## 2026-07-05 — v0.2.0 · engine, balance, The Floor, deploy packaging

Initial build (commits `22c45b2` → `0621a6d`). See `README.md` for the phase list.

- **Phase 1 — engine.** Models + migration `0001`, linear-bonding-curve AMM, trade
  execution + immutable ledger, idempotent weekly dividends, Sleeper provider, 21 tests.
- **Phase 2 — balance.** Backtest vs. the real 2025 season; economy knobs locked
  (`docs/balance.md`): P0 = 1.0× projected pts, dividend $0.30/pt, slope 12%.
- **Phase 3 — "The Floor" UI.** React + Vite in 49ers scarlet & gold (gold = up, scarlet =
  down), no monospace: market + ticker, player pages + order pad, Your Book, Standings, The
  Tape, Commissioner.
- **Phase 5 — season-ready backend.** Invite-code auth + signed-cookie sessions,
  commissioner tools, APScheduler jobs (nightly sync, price snapshots, ESPN game locks,
  Tuesday settlement).
- **Phase 4/6 packaging.** Dockerfile + `fly.toml` + `docs/hosting.md` (Tailscale Funnel
  demo → Fly.io season) + `Run Demo.command` launcher + Opening Bell projections script.
