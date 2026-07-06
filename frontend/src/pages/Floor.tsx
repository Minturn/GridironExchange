import { useNavigate } from 'react-router-dom'
import type { MarketRow } from '../types'
import { money, pct } from '../api'
import { Spark } from '../components/Spark'

export function Floor({ rows }: { rows: MarketRow[] }) {
  const nav = useNavigate()
  return (
    <div className="page">
      <section className="panel">
        <h2>
          The Floor <em>· {rows.length} listed</em>
        </h2>
        <div className="tbl-wrap">
          <table>
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
              {rows.map((r) => (
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
              {!rows.length && (
                <tr>
                  <td className="l dim" colSpan={7}>
                    Nothing listed yet — the commissioner rings the Opening Bell to create the market.
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
