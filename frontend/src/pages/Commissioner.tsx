import { useState } from 'react'
import { post, ApiError } from '../api'

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

        <Card title="Stat correction" blurb="Fix one player-week before (re-)posting that week's dividends. No claw-backs — fix first, then post.">
          <div className="row">
            <input placeholder="player id" value={fix.player_id} style={{ width: 110 }} onChange={(e) => setFix({ ...fix, player_id: e.target.value })} />
            <input type="number" min={1} max={18} value={fix.week} style={{ width: 58 }} onChange={(e) => setFix({ ...fix, week: Number(e.target.value) })} />
            <input type="number" step="0.1" value={fix.pts} style={{ width: 70 }} onChange={(e) => setFix({ ...fix, pts: Number(e.target.value) })} />
            <button className="btn" onClick={() => run('stat fix', () => post('/api/admin/stat-fix', fix))}>
              Apply
            </button>
          </div>
        </Card>

        <Card title="Opening Bell" blurb='Create listings from a projections snapshot: {"player_id": season_pts, ...}. One shot per player — existing listings are never re-priced.'>
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
