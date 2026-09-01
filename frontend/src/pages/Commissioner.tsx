import { useEffect, useState } from 'react'
import { get, post, money, ApiError } from '../api'
import type { AuditReport, LeagueState, Member } from '../types'

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
  const [fmt, setFmt] = useState('')
  const [sleeperId, setSleeperId] = useState('')
  const [cur, setCur] = useState<LeagueState | null>(null)
  const [audit, setAudit] = useState<AuditReport | null>(null)
  const [members, setMembers] = useState<Member[]>([])
  const [pick, setPick] = useState<number | ''>('')
  const [resetInfo, setResetInfo] = useState<{ username: string; temp: string } | null>(null)

  function loadMembers() {
    return get<{ members: Member[] }>('/api/admin/members')
      .then((r) => setMembers(r.members))
      .catch(() => {})
  }

  useEffect(() => {
    get<P[]>('/api/market')
      .then((m) => setPlayers(m.map((r) => ({ player_id: r.player_id, name: r.name, pos: r.pos, team: r.team }))))
      .catch(() => {})
    get<LeagueState>('/api/state')
      .then((s) => {
        setCur(s)
        setMode(s.scoring_mode)
        setFmt(s.scoring_format)
      })
      .catch(() => {})
    loadMembers()
  }, [])

  async function removeMember() {
    const m = members.find((x) => x.user_id === pick)
    if (!m) return
    const warn =
      m.shares > 0
        ? `Remove ${m.username}? They hold ${m.shares} shares — their book is sold back to the market (this moves prices) and the account is permanently deleted. This can't be undone.`
        : `Remove ${m.username}? Their account is permanently deleted. This can't be undone.`
    if (!window.confirm(warn)) return
    await run(`remove ${m.username}`, () =>
      post('/api/admin/remove-member', { user_id: m.user_id, liquidate: m.shares > 0 }),
    )
    setPick('')
    await loadMembers()
  }

  async function resetPassword() {
    const m = members.find((x) => x.user_id === pick)
    if (!m) return
    if (
      !window.confirm(
        `Reset ${m.username}'s password? Their current one stops working and you'll get a temporary password to give them.`,
      )
    )
      return
    setResetInfo(null)
    await run(`reset ${m.username}`, async () => {
      const r = await post<{ username: string; temp_password: string }>(
        '/api/admin/reset-password',
        { user_id: m.user_id },
      )
      setResetInfo({ username: r.username, temp: r.temp_password })
      return { reset: r.username } // keep the temp password out of the generic status line
    })
  }

  async function run(label: string, fn: () => Promise<unknown>) {
    setOut(`${label}…`)
    try {
      const r = await fn()
      setOut(`${label}: ${JSON.stringify(r)}`)
    } catch (e) {
      setOut(`${label} FAILED: ${e instanceof ApiError ? e.message : String(e)}`)
    }
  }

  const picked = members.find((m) => m.user_id === pick) ?? null

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
          blurb="How weekly points become dividends (only dividends — never re-prices the market or moves positions, so it's safe to switch). Market: every share pays raw points; simplest, position choice is nearly free. Relative: points normalized by position — tilts value toward WR/TE. Lineup: only your starting-lineup shares pay, one QB slot like a normal league."
        >
          <div className="row">
            <span className="dim" style={{ fontSize: 12 }}>
              Current: <b style={{ color: 'var(--gold-hi)' }}>{cur ? cur.scoring_mode : '…'}</b>
            </span>
          </div>
          <div className="row">
            <select value={mode} onChange={(e) => setMode(e.target.value)} aria-label="Scoring mode">
              <option value="market">Market — raw points</option>
              <option value="relative">Relative — position-normalized</option>
              <option value="lineup">Lineup — starters only</option>
            </select>
            <button
              className="btn solid"
              disabled={!mode || mode === cur?.scoring_mode}
              onClick={() =>
                run('scoring mode', () => post('/api/admin/scoring-mode', { mode })).then(() =>
                  setCur((c) => (c ? { ...c, scoring_mode: mode as LeagueState['scoring_mode'] } : c)),
                )
              }
            >
              Set mode
            </button>
          </div>
          {cur && mode !== cur.scoring_mode && (
            <p className="err" style={{ fontSize: 11.5 }}>
              Mid-season change: this reshapes everyone’s weekly income starting the next dividend run.
              Positions and prices are untouched.
            </p>
          )}
        </Card>

        <Card
          title="In-game trading"
          blurb="Locked: a player's stock freezes at his kickoff — no trading on live info (pilot default, everyone on equal footing). Live: stocks stay tradeable during games so you can panic-sell an injury or chase a hot hand. Dividends settle by the kickoff snapshot either way, so switching is safe."
        >
          <div className="row">
            <span className="dim" style={{ fontSize: 12 }}>
              Current:{' '}
              <b style={{ color: cur?.in_game_trading === 'live' ? 'var(--scarlet-hi)' : 'var(--gold-hi)' }}>
                {cur ? cur.in_game_trading : '…'}
              </b>
            </span>
          </div>
          <div className="row">
            <button
              className="btn"
              disabled={cur?.in_game_trading === 'locked'}
              onClick={() =>
                run('in-game trading', () => post('/api/admin/in-game-trading', { mode: 'locked' })).then(() =>
                  setCur((c) => (c ? { ...c, in_game_trading: 'locked' } : c)),
                )
              }
            >
              Lock at kickoff
            </button>
            <button
              className="btn danger"
              disabled={cur?.in_game_trading === 'live'}
              onClick={() =>
                run('in-game trading', () => post('/api/admin/in-game-trading', { mode: 'live' })).then(() =>
                  setCur((c) => (c ? { ...c, in_game_trading: 'live' } : c)),
                )
              }
            >
              Go live
            </button>
          </div>
          {cur?.in_game_trading === 'live' && (
            <p className="err" style={{ fontSize: 11.5 }}>
              Live: rewards whoever’s watching the game and fastest to react. Great drama, but not
              everyone can be online — worth watching how it feels.
            </p>
          )}
        </Card>

        <Card
          title="Scoring format"
          blurb="How raw stats become fantasy points — full PPR (1/reception), half PPR, or standard. We compute points ourselves from the raw box score (not the feed's number), so it's per-league. Takes effect on the next dividend run; never re-prices the market."
        >
          <div className="row">
            <span className="dim" style={{ fontSize: 12 }}>
              Current: <b style={{ color: 'var(--gold-hi)' }}>{cur ? cur.scoring_format : '…'}</b>
            </span>
          </div>
          <div className="row">
            <select value={fmt} onChange={(e) => setFmt(e.target.value)} aria-label="Scoring format">
              <option value="ppr">Full PPR</option>
              <option value="half_ppr">Half PPR</option>
              <option value="std">Standard (non-PPR)</option>
            </select>
            <button
              className="btn solid"
              disabled={!fmt || fmt === cur?.scoring_format}
              onClick={() =>
                run('scoring format', () => post('/api/admin/scoring-format', { fmt })).then(() =>
                  setCur((c) => (c ? { ...c, scoring_format: fmt as LeagueState['scoring_format'] } : c)),
                )
              }
            >
              Set format
            </button>
          </div>
        </Card>

        <Card
          title="Import scoring (Sleeper)"
          blurb="Mirror an existing Sleeper league's exact scoring — paste its league ID and we import its rules (bonuses included) in one step. Sets the format to Custom; takes effect on the next dividend run."
        >
          <div className="row">
            <input
              placeholder="Sleeper league ID"
              value={sleeperId}
              style={{ width: 200 }}
              onChange={(e) => setSleeperId(e.target.value)}
            />
            <button
              className="btn solid"
              disabled={!sleeperId}
              onClick={() =>
                run('import scoring', () =>
                  post('/api/admin/import-scoring', { sleeper_league_id: sleeperId.trim() }),
                ).then(() => setCur((c) => (c ? { ...c, scoring_format: 'custom' } : c)))
              }
            >
              Import
            </button>
          </div>
        </Card>

        <Card
          title="Dividend mode"
          blurb="Snapshot: the whole week's dividend goes to whoever owned a player at kickoff (simple, safe). Accrual: the dividend follows ownership through the game — buy the hot hand and earn his rest-of-game, with a live Game Day board. Under accrual the own-at-kickoff rule no longer applies."
        >
          <div className="row">
            <span className="dim" style={{ fontSize: 12 }}>
              Current:{' '}
              <b style={{ color: cur?.dividend_mode === 'accrual' ? 'var(--scarlet-hi)' : 'var(--gold-hi)' }}>
                {cur ? cur.dividend_mode : '…'}
              </b>
            </span>
          </div>
          <div className="row">
            <button
              className="btn"
              disabled={cur?.dividend_mode === 'snapshot'}
              onClick={() =>
                run('dividend mode', () => post('/api/admin/dividend-mode', { mode: 'snapshot' })).then(() =>
                  setCur((c) => (c ? { ...c, dividend_mode: 'snapshot' } : c)),
                )
              }
            >
              Own at kickoff
            </button>
            <button
              className="btn danger"
              disabled={cur?.dividend_mode === 'accrual'}
              onClick={() =>
                run('dividend mode', () => post('/api/admin/dividend-mode', { mode: 'accrual' })).then(() =>
                  setCur((c) => (c ? { ...c, dividend_mode: 'accrual' } : c)),
                )
              }
            >
              Live accrual
            </button>
          </div>
          {cur?.dividend_mode === 'accrual' && (
            <p className="err" style={{ fontSize: 11.5 }}>
              Accrual: dividends follow ownership through games and settle Tuesday (provisional until
              then). The kickoff-ownership rule no longer applies. Best paired with live in-game trading.
            </p>
          )}
        </Card>

        <Card
          title="Dividend rate"
          blurb="$ paid per fantasy point, per share, each week — the main scoring dial. Higher = bigger weekly payouts. Takes effect on the next dividend run; never re-prices the market. Default 0.30."
        >
          <div className="row">
            <span className="dim" style={{ fontSize: 12 }}>
              Current: <b style={{ color: 'var(--gold-hi)' }}>${cur ? cur.dividend_multiplier.toFixed(2) : '…'}</b>/pt
            </span>
          </div>
          <div className="row">
            <label>$/pt</label>
            <input
              type="number"
              step="0.05"
              min={0}
              placeholder={cur ? cur.dividend_multiplier.toFixed(2) : '0.30'}
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

        <Card
          title="Registration"
          blurb="Open: anyone with the invite code can join. Closed: the code stops working for new members — everyone already in is unaffected. Close it once your league is set so a leaked code can't add strangers."
        >
          <div className="row">
            <span className="dim" style={{ fontSize: 12 }}>
              Current:{' '}
              <b style={{ color: cur?.registration_open === false ? 'var(--scarlet-hi)' : 'var(--gold-hi)' }}>
                {cur ? (cur.registration_open ? 'open' : 'closed') : '…'}
              </b>
            </span>
          </div>
          <div className="row">
            <button
              className="btn"
              disabled={cur?.registration_open === true}
              onClick={() =>
                run('registration', () => post('/api/admin/registration', { open: true })).then(() =>
                  setCur((c) => (c ? { ...c, registration_open: true } : c)),
                )
              }
            >
              Open
            </button>
            <button
              className="btn danger"
              disabled={cur?.registration_open === false}
              onClick={() =>
                run('registration', () => post('/api/admin/registration', { open: false })).then(() =>
                  setCur((c) => (c ? { ...c, registration_open: false } : c)),
                )
              }
            >
              Close
            </button>
          </div>
        </Card>

        <Card
          title="Members"
          blurb="Everyone who's joined with the invite code. Reset password gives a locked-out manager a fresh temporary one to sign in with. Remove takes someone out of the league (you and other commissioners can't be removed) — if they hold shares their book is sold back to the market first. Removal is permanent."
        >
          <div className="row">
            <span className="dim" style={{ fontSize: 12 }}>
              <b style={{ color: 'var(--gold-hi)' }}>{members.length}</b> joined
            </span>
          </div>
          <div className="row">
            <select
              value={pick}
              style={{ minWidth: 260 }}
              aria-label="Member"
              onChange={(e) => {
                setPick(e.target.value ? Number(e.target.value) : '')
                setResetInfo(null)
              }}
            >
              <option value="">choose a member…</option>
              {members.map((m) => (
                <option key={m.user_id} value={m.user_id}>
                  {m.username}
                  {m.is_you ? ' (you)' : m.is_commissioner ? ' (commish)' : ''} — {m.shares} shares · {m.trades} trades
                </option>
              ))}
            </select>
          </div>
          <div className="row">
            <button className="btn" disabled={!picked} onClick={resetPassword}>
              Reset password
            </button>
            <button
              className="btn danger"
              disabled={!picked || picked.is_you || picked.is_commissioner}
              onClick={removeMember}
            >
              Remove
            </button>
          </div>
          {resetInfo && (
            <p style={{ fontSize: 12.5, marginTop: 8 }}>
              Temp password for <b>{resetInfo.username}</b>:{' '}
              <b style={{ color: 'var(--gold-hi)', fontFamily: 'monospace', fontSize: 14 }}>{resetInfo.temp}</b>{' '}
              — text it to them; they sign in with it.
            </p>
          )}
          {picked && (picked.is_you || picked.is_commissioner) && (
            <p className="dim" style={{ fontSize: 11.5 }}>
              You and other commissioners can’t be removed — reset is fine.
            </p>
          )}
        </Card>

        <Card title="Money audit" blurb="Replay every member's trade + dividend ledger and compare to their cash balance. All green means the books are exact; any drift points to a bug or hand-edit, with the amount.">
          <button
            className="btn"
            onClick={() =>
              run('audit', async () => {
                const r = await get<AuditReport>('/api/admin/audit')
                setAudit(r)
                return { all_ok: r.all_ok, members: r.members.length }
              })
            }
          >
            Run audit
          </button>
          {audit && (
            <table className="book-table" style={{ marginTop: 10 }}>
              <thead>
                <tr>
                  <th className="l">Member</th>
                  <th>Cash</th>
                  <th>Ledger</th>
                  <th>Drift</th>
                </tr>
              </thead>
              <tbody>
                {audit.members.map((m) => (
                  <tr key={m.username}>
                    <td className="l">{m.username}</td>
                    <td className="num">${money(m.cash)}</td>
                    <td className="num dim">${money(m.computed_cash)}</td>
                    <td className={`num ${m.ok ? 'up' : 'dn'}`}>
                      {m.ok ? '✓' : `$${money(m.drift)}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
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
