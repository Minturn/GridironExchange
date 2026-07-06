# Gridiron Exchange — SPEC

> Fantasy football where the players trade like stocks. Working name **Gridiron Exchange**
> (ticker vibe: `$GRIDX`) — rename freely, nothing is coupled to the name yet.
>
> **Two-phase goal:** run it for Ryan's league in fall 2026 (NFL Week 1 ≈ Sep 10, 2026),
> then harden into a product. Every pilot decision below notes where the product version
> diverges so we don't paint ourselves into a corner.

---

## 1. The pitch (one paragraph, for the friends)

Everyone starts the season with **$10,000 of league money**. Every NFL player is a stock.
Prices move when league members buy and sell. Every Tuesday, each player you hold pays a
**dividend equal to his fantasy points** for the week. No draft, no lineups, no waivers —
just a portfolio. Highest net worth after Week 18 wins. Buy the rookie before the breakout,
dump the aging RB before the cliff, panic-sell the injury on Sunday night like everyone else.

## 2. Hard guardrail: virtual currency only

Real-money player-share trading is what killed Football Index (UK, 2021) and sits in a
US legal no-man's-land between securities and gambling law. **The app never touches money.**
The league's entry fee / prize pool, if any, is handled offline exactly like any normal
fantasy league. This stays true in the product version — monetize the platform
(subscriptions, league fees), never the trading.

---

## 3. Game design

### 3.1 Setup
- League of **N players** (pilot: ~10–14 friends). Everyone starts with **$10,000 cash**.
- Every rostered NFL player is listed (synced from Sleeper). Only the ~400 with projections
  matter; the rest sit at floor prices and cost nothing to carry in the system.
- Season = NFL Weeks 1–18. Market opens at a scheduled, announced **Opening Bell**
  (target: Tue Sep 1, 2026, 6:00 PM PT) so nobody gets an early-access edge.

### 3.2 Pricing — automated market maker (no order book)
A small league can't sustain an order book (no counterparty = no trade = boring). Instead
every player has a **linear bonding curve** the house always quotes against:

```
price(s) = P0 + m·s          s = net shares outstanding (held by users)
```

- **P0 (IPO price)** seeded from preseason projections: `P0 = 1.00 × projected_season_pts`
  (PPR) **[LOCKED by the Phase 2 backtest — docs/balance.md]**. CMC ≈ 350 proj pts → $350.
  A streamer at 120 → $120. Deep bench → $5 floor. A maxed stud position (25 shares)
  costs most of a bankroll — concentration is expensive by design.
- **Buying n shares** costs the integral along the curve:
  `cost = n·P0 + m·(s·n + n²/2)` — big buys move the price against you, so hype is
  self-limiting. **Selling** returns value along the same curve.
- **Slope m** per player: calibrated so one member maxing the per-player cap moves the
  price ≈ +12%: `m = 0.12 × P0 / cap` **[LOCKED, Phase 2]**.
- **1% fee** on every trade (burned; shown as a running "house pot" for flavor). Kills
  zero-risk oscillation games around the curve.

Prices therefore move on **demand** (league sentiment: news, injuries, hype) around a
**fundamentals anchor** (P0 from projections, dividends from real scoring). That hybrid is
the game.

### 3.3 Dividends — the fundamentals engine
- Every Tuesday ~6:00 AM PT (stats final), each share pays
  `dividend = week_fantasy_pts × $0.30` (PPR) **[LOCKED, Phase 2]**. Injured/bye = $0.
- Payback math at locked knobs: buy at P0 and the player exactly hits projection →
  season dividends = `0.30 × pts = 0.30 × P0` → **~+30% season yield before price
  movement** (backtested median outcome +29%). Dividends inject new cash league-wide
  each week — everyone's number goes up; the *competition* is relative.
- The dividend multiplier and P0 factor were locked by the Phase 2 backtest against the
  real 2025 season (docs/balance.md), not by vibes.

### 3.4 Market rules
- **Per-player cap:** one member may hold at most **25 shares** of any one player
  (no cornering CMC in a 12-person league).
- **Game locks:** each player's trading locks at his game's kickoff and reopens when his
  stats are final (Tue 6 AM). No trading on in-game information. (Live in-game trading is
  the marquee **product** feature — deliberately out of scope for the pilot, §12.)
- **No shorts, no margin** in the pilot. (Product "degenerate mode" candidates.)
- **Injury/IR:** nothing special — the player pays $0 dividends and the market reprices
  him. That's the game working.
- **Winner:** highest **net worth** (cash + holdings marked to the curve) at final whistle
  of Week 18. Optional podium settle: force-liquidate all books along the curve so the
  final number is cash, not a mark.

### 3.5 Season arc / retention beats
- **Opening Bell** (Sep 1): market opens, 10 days of pre-Week-1 positioning on projections.
- **Tuesday Earnings:** dividends post + a weekly digest ("$KITTLE paid $18.40/share").
- **Trade deadline** (optional, ~Week 12) — forces conviction, mirrors real fantasy.
- **Feed:** every trade is public in-app ("Ryan dumped 40 shares of Kyler") — the
  trash-talk surface. This feed is the retention feature; treat it as first-class.

---

## 4. Calibration backtest (before anyone plays)

Replay the **2025 season** from nflverse weekly data against the pricing engine with
scripted bot personalities (chalk-holder, streamer-chaser, injury-panicker, contrarian).
Tune `P0` factor, dividend multiplier, slope, cap until:
- median bot portfolio ≈ **+20–30%** on the season, top decile ≈ +80%;
- no strategy dominates (buy-and-hold-studs must NOT strictly beat active trading);
- a Week-1 all-in on one player is survivable but clearly punished.

Deliverable: `backend/scripts/backtest.py` + a short results note in `docs/balance.md`.
This is the highest-leverage engineering in the project — the UI sells it, the balance
makes it fun for 18 weeks.

---

## 5. Data

| Need | Source | Notes |
|---|---|---|
| Players, teams, injuries, bye weeks | **Sleeper API** | Free, no key. `GET /v1/players/nfl` (nightly sync). |
| Weekly fantasy points | **Sleeper API** stats endpoints | Poll Tue AM; also drives game-lock schedule. |
| Preseason projections (P0 seed) | Sleeper projections; fallback FantasyPros CSV import | Snapshot once at Opening Bell; never re-priced from projections after. |
| Backtest history | **nflverse** (nflfastR data releases) | 2025 weekly player stats, free CSVs. |

Keep every external feed behind one `providers/` interface — the product version will want
a paid feed (SportsDataIO etc.) for live scoring; swapping providers must be a one-file job.

---

## 6. Architecture & stack

Same family as Shotgun so context transfers, **new ports** so everything coexists:

- **Backend:** FastAPI (Python 3.12), SQLAlchemy 2 + Alembic, APScheduler for jobs
  (nightly player sync, Tuesday dividend run, lock/unlock at kickoffs). Port **:8200**.
- **DB:** SQLite for local dev; **Postgres from day one on the deploy target** (Fly.io
  ships it; don't build a migration cliff for the product).
- **Frontend:** React + Vite + TypeScript, Tailwind. Charts hand-rolled SVG (sparklines,
  area charts) — no chart lib; the terminal aesthetic (§8) wants full control. Port **:5190**.
- **Realtime:** MVP polls (10s market refresh). WebSocket price ticker is v1.1 — design the
  frontend store so the poll can be swapped for a socket without touching components.
- **Auth (pilot):** username + password behind a single league **invite code**; session
  cookie. Ryan = commissioner (admin: pause market, adjust a bad stat, kick a user).
  Product swaps this for real auth + multi-league tenancy (§12) — keep `league_id` on
  every table **from the first migration** even though the pilot has exactly one league.

### 6.1 Engine invariants (test these, not the UI)
- Trade execution is **transactional and serialized per player** (row lock) — two
  simultaneous buys must both pay correct curve prices.
- `cash ≥ 0` always; buys validate against quoted cost including fee.
- Dividend run is **idempotent** (safe to re-run a week; keyed on `(week, player, holder)`).
- Every trade/dividend writes an immutable ledger row — net worth must be derivable from
  the ledger alone (this is also the anti-"my money vanished" audit trail for friends).

---

## 7. Data model (first migration)

```
leagues        id, name, invite_code, settings_json (knobs from §3), season_year
users          id, league_id, username, pw_hash, is_commissioner, cash
players        id (sleeper_id), name, team, pos, status, bye_week, headshot_url
listings       league_id, player_id, p0, slope, shares_outstanding, locked_until
holdings       user_id, player_id, shares            (cap enforced here)
trades         id, ts, user_id, player_id, side, shares, price_avg, fee, cash_after   [ledger]
dividends      week, player_id, user_id, shares_held, pts, amount                     [ledger]
price_history  player_id, ts, price                  (sparkline source; hourly snapshot + every trade)
stat_weeks     week, player_id, pts, is_final
```

---

## 8. UI — design language: **“The Floor”**

**The requirement:** looks like nothing previously built here. The ERP is a light,
utilitarian dashboard; StrokesGained is a mobile app; Shotgun is a standard SaaS web UI.
This is the opposite: a **dark trading terminal wearing 49ers colors** —
Bloomberg-terminal-meets-Levi's-Stadium. Dense, numeric, alive.

### 8.1 Tokens
```
--ground:    #0C0A09   near-black, warm bias (not pure black, not cool grey)
--panel:     #171310   card/panel surface
--line:      #2A231B   hairline borders
--scarlet:   #AA0000   49ers scarlet — DOWN, sell, alerts, losses
--gold:      #B3995D   49ers metallic gold — UP, buy, gains, the accent
--gold-hi:   #E4D5AE   bright gold — emphasized numbers, hovers
--ink:       #EDE6D6   primary text (warm off-white)
--ink-dim:   #8D8272   secondary text, labels
```
**Signature move: gold = up, scarlet = down.** Deliberately not green/red — it's ownable,
on-theme, and instantly "different." Semantic color never leaks into decoration: scarlet
and gold on a screen always *mean* something.

### 8.2 Type
- **Display / headers:** condensed athletic sans — `"Avenir Next Condensed", "Arial Narrow",
  sans-serif`, uppercase, tight tracking on big numbers, +4% letter-spacing on small labels.
  (Product: license a real condensed face, e.g. Barlow Condensed self-hosted.)
- **Data / numbers:** ⚠ **NO MONOSPACE anywhere — operator rule (2026-07-05).** Use a
  proportional sans — `"Avenir Next", "Helvetica Neue", -apple-system, sans-serif` — with
  `font-variant-numeric: tabular-nums` on every numeric cell so price columns still align
  perfectly. (Product: self-host a face with strong tabular figures, e.g. Archivo.)
- **Body:** same proportional sans — this UI is scanned, not read.

### 8.3 Screens (pilot = 6)
1. **The Floor (market)** — the home screen. Scrolling **ticker tape** across the top
   (last trades + movers). Dense player grid: pos, name, team, price, day Δ, 4-wk
   sparkline, yield, your position. Sort/filter by position; search. Row click → Player.
2. **Player page** — big price area-chart (season), P0 line, dividend history bars,
   news/injury status, the **order pad** (buy/sell with live curve quote: "40 shares ≈
   $2,140 incl. fee, avg $53.50"), holders list ("who owns him" — trash-talk fuel).
3. **Portfolio (“Your Book”)** — holdings with cost basis, P&L, yield; cash; net-worth
   line chart vs. league median.
4. **Leaderboard** — net worth standings styled like a division standings board; weekly
   movement arrows.
5. **The Tape (feed)** — every trade + dividend event, newest first. Public by design.
6. **Commissioner** — market pause, knob view (read-only after Opening Bell), stat
   correction, user management. Utilitarian is fine here.

Mock of screens 1's direction (ticker, grid, order pad, standings) lives in
`docs/mock/` and was the buy-in demo artifact.

### 8.4 Motion
Price ticks pulse the cell (gold flash up / scarlet flash down, 300ms). Ticker tape
scrolls continuously. Everything else is still — restraint keeps the two live elements
meaningful. Respect `prefers-reduced-motion` (disable tape scroll + pulses).

---

## 9. Hosting

**Phase A — buy-in demo (now → August): this Mac.**
Run backend+frontend locally, expose with **Tailscale Funnel** (free, stable
`https://…ts.net` URL, HTTPS, zero router config) — `tailscale funnel 8200`.
Cloudflare Tunnel is the alternate if a custom domain is wanted early.
Caveats: demo dies when the Mac sleeps (`caffeinate -s` during demo windows); fine for
showing friends, **not fine for the season**.

**Phase B — the season (by Sep 1): Fly.io**, ~$5–10/mo. One Dockerfile (FastAPI serves
the built Vite bundle), Fly Postgres, `fly deploy`. Reasons over Mac-as-host: friends will
check portfolios at work/on phones all week; a sleeping laptop = dead league. Reasons over
Render/Railway: cheap Postgres + easy scale path for the product. Buy the domain when the
name is settled.

---

## 10. Build phases

| # | When (2026) | Milestone | Definition of done |
|---|---|---|---|
| 1 | Jul 5 – Jul 19 | **Engine** | Models+migrations, AMM trade exec, dividend job, Sleeper sync; engine-invariant tests green (§6.1). |
| 2 | Jul 19 – Jul 26 | **Backtest & balance** | 2025 replay w/ bots; knobs locked in `docs/balance.md` (§4). |
| 3 | Jul 26 – Aug 9 | **The Floor UI** | Screens 1–5 against live local engine; The Floor look (§8) done. |
| 4 | Aug 9 – Aug 15 | **Demo live** | Tailscale Funnel URL; friends poke a fake-week sandbox; collect buy-in + name/roast feedback. |
| 5 | Aug 15 – Aug 29 | **Season-ready** | Fly.io deploy, invites, commissioner screen, Tuesday digest, game locks vs. real 2026 schedule. |
| 6 | Sep 1 | **Opening Bell** | 2026 projections snapshotted → P0; market opens. |
| 7 | Sep 10 → Jan | **Season ops** | Tuesday dividend runs, patches, feature notes for the product. |

Weeks 1–2 have zero UI on purpose: if the engine + balance are right, the product is real;
the UI is the sizzle.

## 11. Pilot → product: decided now so the pilot doesn't fight it

- `league_id` on every row from migration 1 (multi-league is a WHERE clause, not a rewrite).
- Data providers behind one interface (paid live feed swap, §5).
- Engine knobs live in `leagues.settings_json`, not code (per-league economies later).
- Frontend market store poll→WebSocket swappable (§6).
- The ledger is the product's trust story — never shortcut it.

## 12. Product backlog (post-season, from a position of "my league loved it")
Live in-game price ticks (the killer feature) · public/multi leagues + real auth · shorts &
options ("degenerate mode") · mobile PWA + push ("KITTLE −12% — injury designation") ·
season-long "IPO calendar" (rookies unlock at draft) · other sports (NBA is 82 games of
liquidity) · league-history museum.

## 13. Open decisions (don't block Phase 1)
- **Name.** Gridiron Exchange / Pigskin Exchange ($PIGX) / The Tape / Two-Minute Market —
  let the friends bikeshed it at the demo; great buy-in trick.
- Trade deadline in the pilot? (Lean yes, Week 12.)
- Podium settle vs. mark-to-curve at Week 18. (Lean force-liquidation — cleaner story.)
- League scoring flavor for dividends (PPR assumed — confirm with the league).
