import { useEffect, useState } from 'react'
import { get, post, ApiError } from '../api'

interface P {
  player_id: string
  name: string
  pos: string
  team: string | null
}

function Card({ title, blurb, children }: { title: string; blurb: string; children: React.ReactNode }) {
  return (
    <section className="panel admin-card">
      <h3>{title}</h3>
      <p>{blurb}</p>
      {children}
    </section>
  )
}

export function Commissioner() {
  const [out, setOut] = useState<string>('')
  const [week, setWeek] = useState(1)
  const [pauseHours, setPauseHours] = useState(2)
  const [fix, setFix] = useState({ player_id: '', week: 1, pts: 0 })
  const [projections, setProjections] = useState('')
  const [openAt, setOpenAt] = useState('')
  const [mode, setMode] = useState('')
  const [players, setPlayers] = useState<P[]>([])
  const [fixSearch, setFixSearch] = useState('')
  const [divRate, setDivRate] = useState('')

  useEffect(() => {
    get<P[]>('/api/market')
      .then((m) => setPlayers(m.map((r) => ({ player_id: r.player_id, name: r.name, pos: r.pos, team: r.team }))))
      .catch(() => {})
  }, [])

  async function run(label: string, fn: () => Promise<unknown>) {
    setOut(`${label}…`)
    try {
      const r = await fn()
      setOut(`${label}: ${JSON.stringify(r)}`)
    } catch (e) {
      setOut(`${label} FAILED: ${e instanceof ApiError ? e.message : String(e)}`)
    }
  }

  return (
    <div className="page">
      <div className="admin-grid">
        <Card title="Week 1 start time" blurb="Lock the market until a time you set, then it opens for the whole league at once — no early-bird edge for whoever logs in first. Pick a time everyone can be online. Leave it off to trade right now.">
          <div className="row">
            <input
              type="datetime-local"
              value={openAt}
              onChange={(e) => setOpenAt(e.target.value)}
              aria-label="Market open date and time"
            />
          </div>
          <div className="row">
            <button
              className="btn solid"
              disabled={!openAt}
              onClick={() =>
                run('set start time', () =>
                  post('/api/admin/open-time', { opens_at: new Date(openAt).toISOString() }),
                )
              }
            >
              Set start time
            </button>
            <button className="btn" onClick={() => run('open now', () => post('/api/admin/open-time', { opens_at: null }))}>
              Open now
            </button>
          </div>
        </Card>

        <Card
          title="Scoring mode"
          blurb="How dividends are scored (never re-prices the market). Market: every share pays raw points — QBs dominate. Relative: points normalized by position, so a QB and RB share pay about the same. Lineup: only your starting-lineup shares pay — one QB slot, like a normal league."
        >
          <div className="row">
            <select value={mode} onChange={(e) => setMode(e.target.value)} aria-label="Scoring mode">
              <option value="">choose…</option>
              <option value="market">Market — raw points</option>
              <option value="relative">Relative — position-normalized</option>
              <option value="lineup">Lineup — starters only</option>
            </select>
            <button
              className="btn solid"
              disabled={!mode}
              onClick={() => run('scoring mode', () => post('/api/admin/scoring-mode', { mode }))}
            >
              Set mode
            </button>
          </div>
        </Card>

        <Card
          title="Dividend rate"
          blurb="$ paid per fantasy point, per share, each week — the main scoring dial. Higher = bigger weekly payouts. Takes effect on the next dividend run; never re-prices the market. Default 0.30."
        >
          <div className="row">
            <label>$/pt</label>
            <input
              type="number"
              step="0.05"
              min={0}
              placeholder="0.30"
              value={divRate}
              style={{ width: 80 }}
              onChange={(e) => setDivRate(e.target.value)}
            />
            <button
              className="btn solid"
              disabled={!divRate}
              onClick={() => run('dividend rate', () => post('/api/admin/rules', { dividend_multiplier: Number(divRate) }))}
            >
              Set rate
            </button>
          </div>
        </Card>

        <Card title="Sync players" blurb="Pull the player universe from Sleeper (runs nightly by itself in season).">
          <button className="btn" onClick={() => run('sync players', () => post('/api/admin/sync-players'))}>
            Sync now
          </button>
        </Card>

        <Card title="Week settlement" blurb="Pull final stats for a week, then post its dividends. Safe to re-run — already-paid rows are skipped.">
          <div className="row">
            <label htmlFor="wk">Week</label>
            <input id="wk" type="number" min={1} max={18} value={week} style={{ width: 64 }} onChange={(e) => setWeek(Number(e.target.value))} />
            <button className="btn" onClick={() => run(`stats wk${week}`, () => post('/api/admin/sync-stats', { week, final: true }))}>
              Pull stats
            </button>
            <button className="btn" onClick={() => run(`dividends wk${week}`, () => post('/api/admin/dividends', { week }))}>
              Post dividends
            </button>
          </div>
        </Card>

        <Card title="Pause / resume market" blurb="Locks every listing (or resumes trading everywhere). Use for disputes, not game locks — those are automatic.">
          <div className="row">
            <label htmlFor="ph">Hours</label>
            <input id="ph" type="number" min={1} max={336} value={pauseHours} style={{ width: 64 }} onChange={(e) => setPauseHours(Number(e.target.value))} />
            <button className="btn danger" onClick={() => run('pause', () => post('/api/admin/pause', { hours: pauseHours }))}>
              Pause all
            </button>
            <button className="btn" onClick={() => run('resume', () => post('/api/admin/resume'))}>
              Resume
            </button>
          </div>
        </Card>

        <Card title="Stat correction" blurb="Fix one player's points for a week before (re-)posting that week's dividends. No claw-backs — fix first, then post. Search for the player.">
          <div className="row">
            <input
              placeholder="search player…"
              value={fixSearch}
              style={{ width: 160 }}
              onChange={(e) => setFixSearch(e.target.value)}
            />
          </div>
          <div className="row">
            <select value={fix.player_id} style={{ maxWidth: 240 }} onChange={(e) => setFix({ ...fix, player_id: e.target.value })}>
              <option value="">choose player…</option>
              {players
                .filter(
                  (p) =>
                    !fixSearch ||
                    `${p.name} ${p.pos} ${p.team ?? ''}`.toLowerCase().includes(fixSearch.toLowerCase()),
                )
                .slice()
                .sort((a, b) => a.name.localeCompare(b.name))
                .map((p) => (
                  <option key={p.player_id} value={p.player_id}>
                    {p.name} · {p.pos} · {p.team ?? 'FA'}
                  </option>
                ))}
            </select>
          </div>
          <div className="row">
            <label>Wk</label>
            <input type="number" min={1} max={18} value={fix.week} style={{ width: 56 }} onChange={(e) => setFix({ ...fix, week: Number(e.target.value) })} />
            <label>Pts</label>
            <input type="number" step="0.1" value={fix.pts} style={{ width: 70 }} onChange={(e) => setFix({ ...fix, pts: Number(e.target.value) })} />
            <button className="btn" disabled={!fix.player_id} onClick={() => run('stat fix', () => post('/api/admin/stat-fix', fix))}>
              Apply
            </button>
          </div>
        </Card>

        <Card title="Build the market (projections)" blurb='Create listings from a projections snapshot: {"player_id": season_pts, ...}. One shot per player — existing listings are never re-priced. Set the start time separately, above.'>
          <textarea value={projections} onChange={(e) => setProjections(e.target.value)} placeholder='{"4034": 350, "6786": 357}' />
          <button
            className="btn solid"
            onClick={() =>
              run('opening bell', () => post('/api/admin/opening-bell', { projections: JSON.parse(projections) }))
            }
          >
            Ring the bell
          </button>
        </Card>
      </div>
      {out && (
        <p className="dim num" style={{ marginTop: 14, wordBreak: 'break-all' }}>
          {out}
        </p>
      )}
    </div>
  )
}
