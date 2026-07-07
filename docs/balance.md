# Balance — economy knobs locked by backtest (Phase 2, 2026-07-05)

**Locked knobs (now `DEFAULT_RULES` in `backend/app/models.py`):**

| knob | value | meaning |
|---|---|---|
| `p0_factor` | **1.00** | IPO price = 1.00 × projected season PPR pts (CMC ≈ $350) |
| `dividend_multiplier` | **0.30** | $0.30 per fantasy point per share, weekly |
| `slope_pct` | **0.12** | one member maxing the cap moves a price ~+12% |
| `fee_rate` | 0.01 | unchanged |
| `share_cap` | 25 | unchanged — a max stud position ≈ $8,750, most of a bankroll |
| `starting_cash` | 10,000 | unchanged |

## Method

`backend/scripts/backtest.py` replays the **real 2025 season** (nflverse weekly
PPR, top-200 players) through the **real engine** — same ORM, `execute_trade`,
dividend run — with 12 scripted bots (chalk, indexer, streamer, momentum,
contrarian, week-1 all-in), 3 seeds per knob combo. Projections are modeled as
actual season totals × ±25% noise (real preseason-2025 projections aren't in the
dataset; the noise models forecast error).

## Why these values

Grid results (median return / all-in return / active-vs-passive spread):

```
   p0   div  slope |  median  top10%  | strategy means
 0.50  0.75  0.08  | +167.9%          | (original SPEC guesses — wildly too hot)
 0.50  0.15  0.08  |  +28.7%  +33.4%  | allin:+33% momo:+25%  ← all-in NOT punished
 0.75  0.22  0.08  |  +28.5%  +33.6%  | allin:+34%            ← same problem
 1.00  0.30  0.12  |  +29.4%  +36.3%  | allin:+13% chalk:+28% index:+30% momo:+34% contra:+30% stream:+19%  ← PICK
 1.25  0.40  0.12  |  +29.1%  +38.7%  | allin:+19% momo:+37%
```

The pick hits every SPEC §4 criterion that's achievable:

- **Median +29%** — in the +20–30% target band; everyone's number goes up.
- **All-in is punished but survivable** (+13% vs +29% median): at p0=1.00 a maxed
  stud position eats most of the bankroll, and slope 0.12 makes the entry/exit
  spread on a 25-share block genuinely expensive.
- **No dominant strategy**: momentum +34%, index +30%, contrarian +30%, chalk +28%.
  Active play edges passive, churn (streamer +19%) pays real fee costs.
- **Prices stay sane**: max price ≈ $585 (stud QB after a hot season + demand).

## Caveat on the "+80% top decile" SPEC target

Bot pools are tight — 12 similar-skill bots on 3 seeds give a +36% top decile.
Human leagues disperse far more (people hold injured players, chase news, panic).
Treat the bot spread as a floor; revisit after real Week-6 data this fall.

## Relative-mode position factors (v0.3.0)

For the `relative` scoring mode (app/engine/scoring.py), dividends are scaled by a
per-position factor so a point means the same across positions. Factor =
`overall_avg / position_avg`, from per-game PPR among startable players in the 2025 season:

| pos | startable pool | avg PPR/game | factor |
|-----|----------------|--------------|--------|
| QB  | top 24 | 17.13 | **0.80** |
| RB  | top 36 | 13.91 | **0.99** |
| WR  | top 48 | 12.84 | **1.07** |
| TE  | top 18 | 11.18 | **1.23** |

QBs score ~23% more than RBs in PPR, so they're scaled down the most; TEs up. Recompute
with the snippet in `scripts/` or by adapting `backtest.py`'s `load_season`.

## Re-running

```bash
cd backend
.venv/bin/python scripts/backtest.py          # locked knobs only
.venv/bin/python scripts/backtest.py --grid   # full sweep
```

Data: `backend/data/stats_player_week_2025.csv` (nflverse `stats_player_week_2025`,
gitignored; re-download from github.com/nflverse/nflverse-data releases).
