import { useEffect, useState } from 'react'
import { get, money } from '../api'
import type { LiveScore } from '../types'

const label = { fontSize: 11, letterSpacing: '.12em', textTransform: 'uppercase' as const }

export function Live() {
  const [s, setS] = useState<LiveScore | null>(null)
  useEffect(() => {
    const load = () => get<LiveScore>('/api/live').then(setS).catch(() => {})
    load()
    const t = setInterval(load, 15000) // keep it feeling live
    return () => clearInterval(t)
  }, [])
  if (!s) return <div className="page dim">Loading…</div>
  return (
    <div className="page">
      <section className="panel">
        <h2>
          Game Day <em>· Wk {s.week}</em>
        </h2>
        <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap', alignItems: 'baseline', margin: '6px 0 4px' }}>
          <div>
            <div className="dim" style={label}>Your paycheck so far</div>
            <div className="num" style={{ fontSize: 34, color: 'var(--gold-hi)', fontWeight: 700 }}>
              ${money(s.your_paycheck)}
            </div>
          </div>
          {s.your_rank != null && (
            <div>
              <div className="dim" style={label}>Live rank</div>
              <div className="num" style={{ fontSize: 34, fontWeight: 700 }}>#{s.your_rank}</div>
            </div>
          )}
        </div>
        <p className="dim" style={{ fontSize: 12, marginTop: 0 }}>
          {s.dividend_mode === 'accrual'
            ? 'Provisional until Tuesday — this climbs live as your players score, then settles on final stats.'
            : 'This league settles by kickoff ownership; the live figures here are informational.'}
        </p>
      </section>

      <section className="panel">
        <h2>Your Book, Live</h2>
        <div className="tbl-wrap">
          <table className="book-table">
            <thead>
              <tr>
                <th className="l">Player</th>
                <th>Shares</th>
                <th>Live pts</th>
                <th>Accrued</th>
              </tr>
            </thead>
            <tbody>
              {s.holdings.map((h) => (
                <tr key={h.player_id}>
                  <td className="l">
                    <span className="pname">{h.name}</span>{' '}
                    <span className="pmeta">
                      {h.pos} · {h.team ?? 'FA'}
                    </span>
                  </td>
                  <td className="num">{h.shares}</td>
                  <td className="num">{h.live_points.toFixed(2)}</td>
                  <td className="num up">${money(h.accrued)}</td>
                </tr>
              ))}
              {!s.holdings.length && (
                <tr>
                  <td colSpan={4} className="l dim">
                    Nothing scoring yet — check back when the games kick off.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <h2>
          Live Standings <em>· this week’s paychecks</em>
        </h2>
        <div className="tbl-wrap">
          <table className="book-table">
            <thead>
              <tr>
                <th>#</th>
                <th className="l">Manager</th>
                <th>Paycheck</th>
              </tr>
            </thead>
            <tbody>
              {s.board.map((r) => (
                <tr key={r.username} style={r.is_you ? { background: 'rgba(198,169,104,0.08)' } : undefined}>
                  <td className="num">{r.rank}</td>
                  <td className="l">
                    {r.username}
                    {r.is_you && <span className="pmeta"> · you</span>}
                  </td>
                  <td className="num up">${money(r.paycheck)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
