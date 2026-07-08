import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { MarketRow } from '../types'
import { money, pct } from '../api'
import { Spark } from '../components/Spark'

export function Floor({ rows }: { rows: MarketRow[] }) {
  const nav = useNavigate()
  const [q, setQ] = useState('')
  const [pos, setPos] = useState('ALL')

  const positions = useMemo(
    () => ['ALL', ...Array.from(new Set(rows.map((r) => r.pos))).sort()],
    [rows],
  )

  const filtered = useMemo(() => {
    const query = q.trim().toLowerCase()
    return rows.filter(
      (r) =>
        (pos === 'ALL' || r.pos === pos) &&
        (!query ||
          r.name.toLowerCase().includes(query) ||
          (r.team ?? '').toLowerCase().includes(query)),
    )
  }, [rows, q, pos])

  return (
    <div className="page">
      <section className="panel">
        <h2>
          The Floor{' '}
          <em>
            · {filtered.length}
            {filtered.length !== rows.length ? ` of ${rows.length}` : ' listed'}
          </em>
        </h2>
        <div className="market-controls">
          <input
            className="search"
            type="search"
            placeholder="Search player or team…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Search players"
          />
          <div className="pos-filter">
            {positions.map((p) => (
              <button
                key={p}
                className={`chip ${pos === p ? 'live' : ''}`}
                onClick={() => setPos(p)}
                type="button"
              >
                {p}
              </button>
            ))}
          </div>
        </div>
        <div className="tbl-wrap">
          <table className="market-table">
            <thead>
              <tr>
                <th className="l">Player</th>
                <th className="l">Pos · Team</th>
                <th>Price</th>
                <th>Δ</th>
                <th>Trend</th>
                <th>Last Wk</th>
                <th>You</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.player_id} className="rowlink" onClick={() => nav(`/player/${r.player_id}`)}>
                  <td className="l">
                    <span className="pname">{r.name}</span>{' '}
                    {r.locked && <span className="lock">LOCKED</span>}
                  </td>
                  <td className="l pmeta">
                    {r.pos} · {r.team ?? 'FA'}
                  </td>
                  <td className="num">${money(r.price)}</td>
                  <td className={`num ${r.delta_pct >= 0 ? 'up' : 'dn'}`}>{pct(r.delta_pct)}</td>
                  <td>
                    <Spark data={r.spark} />
                  </td>
                  <td className="num dim">{r.last_wk_pts ? r.last_wk_pts.toFixed(1) : '—'}</td>
                  <td className={`num ${r.your_shares ? '' : 'dim'}`}>
                    {r.your_shares ? `${r.your_shares} sh` : '—'}
                  </td>
                </tr>
              ))}
              {!filtered.length && (
                <tr>
                  <td className="l dim" colSpan={7}>
                    {rows.length
                      ? 'No players match your search.'
                      : 'Nothing listed yet — the commissioner rings the Opening Bell to create the market.'}
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
