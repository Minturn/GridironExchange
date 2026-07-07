import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { get, money } from '../api'
import type { Portfolio as PortfolioT } from '../types'

export function Portfolio() {
  const [p, setP] = useState<PortfolioT | null>(null)
  const nav = useNavigate()
  useEffect(() => {
    get<PortfolioT>('/api/portfolio').then(setP).catch(() => setP(null))
  }, [])
  if (!p) return <div className="page dim">Loading…</div>
  return (
    <div className="page">
      <section className="panel">
        <h2>
          Your Book <em>· net worth ${money(p.net_worth)} · cash ${money(p.cash)}</em>
        </h2>
        <div className="tbl-wrap">
          <table className="book-table">
            <thead>
              <tr>
                <th className="l">Player</th>
                <th>Shares</th>
                <th>Spot</th>
                <th>Mark value</th>
                <th>Avg cost</th>
                <th>P&amp;L</th>
                <th>Dividends</th>
              </tr>
            </thead>
            <tbody>
              {p.holdings.map((h) => (
                <tr key={h.player_id} className="rowlink" onClick={() => nav(`/player/${h.player_id}`)}>
                  <td className="l">
                    <span className="pname">{h.name}</span>{' '}
                    <span className="pmeta">
                      {h.pos} · {h.team ?? 'FA'}
                    </span>
                  </td>
                  <td className="num">{h.shares}</td>
                  <td className="num">${money(h.spot)}</td>
                  <td className="num">${money(h.mark_value)}</td>
                  <td className="num dim">{h.avg_cost != null ? `$${money(h.avg_cost)}` : '—'}</td>
                  <td className={`num ${h.pnl == null ? 'dim' : h.pnl >= 0 ? 'up' : 'dn'}`}>
                    {h.pnl != null ? `${h.pnl >= 0 ? '+' : '−'}$${money(Math.abs(h.pnl))}` : '—'}
                  </td>
                  <td className="num up">${money(h.dividends_earned)}</td>
                </tr>
              ))}
              {!p.holdings.length && (
                <tr>
                  <td colSpan={7} className="l dim">
                    All cash, no positions — head to The Floor.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
