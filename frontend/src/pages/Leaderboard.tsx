import { useEffect, useState } from 'react'
import { get, money } from '../api'
import type { BoardRow } from '../types'

export function Leaderboard() {
  const [rows, setRows] = useState<BoardRow[]>([])
  useEffect(() => {
    get<BoardRow[]>('/api/leaderboard').then(setRows).catch(() => setRows([]))
  }, [])
  return (
    <div className="page" style={{ maxWidth: 640 }}>
      <section className="panel board">
        <h2>
          Standings <em>· net worth</em>
        </h2>
        <ol>
          {rows.map((r) => (
            <li key={r.username} className={r.is_you ? 'me' : ''}>
              <span className="rk num">{r.rank}</span>
              <span className="nm">{r.username}</span>
              <span className="num">${money(r.net_worth)}</span>
              <span className="num dim" style={{ fontSize: 11 }}>${money(r.cash)} cash</span>
            </li>
          ))}
        </ol>
      </section>
    </div>
  )
}
