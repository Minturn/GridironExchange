import type { MarketRow } from '../types'
import { money } from '../api'

export function Ticker({ rows }: { rows: MarketRow[] }) {
  if (!rows.length) return null
  const movers = [...rows].sort((a, b) => Math.abs(b.delta_pct) - Math.abs(a.delta_pct)).slice(0, 20)
  // content is rendered twice so the CSS -50% translate loops seamlessly
  const half = (suffix: string) =>
    movers.map((r) => (
      <span key={r.player_id + suffix}>
        <span className="tkr">${(r.name.split(' ').pop() ?? r.name).toUpperCase()}</span>{' '}
        <span className="num">{money(r.price)}</span>{' '}
        <span className={`num ${r.delta_pct >= 0 ? 'up' : 'dn'}`}>
          {r.delta_pct >= 0 ? '▲' : '▼'}
          {Math.abs(r.delta_pct * 100).toFixed(1)}%
        </span>
      </span>
    ))
  return (
    <div className="tape" aria-hidden="true">
      <div className="tape-track">
        {half('a')}
        {half('b')}
      </div>
    </div>
  )
}
