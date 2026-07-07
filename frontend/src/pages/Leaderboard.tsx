import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { get, money } from '../api'
import type { BoardRow } from '../types'

export function Leaderboard() {
  const [rows, setRows] = useState<BoardRow[]>([])
  const nav = useNavigate()
  useEffect(() => {
    get<BoardRow[]>('/api/leaderboard').then(setRows).catch(() => setRows([]))
  }, [])
  return (
    <div className="page" style={{ maxWidth: 640 }}>
      <section className="panel board">
        <h2>
          Standings <em>· tap a name to see their roster</em>
        </h2>
        <ol>
          {rows.map((r) => (
            <li
              key={r.username}
              className={`rowlink ${r.is_you ? 'me' : ''}`}
              onClick={() => nav(`/manager/${encodeURIComponent(r.username)}`)}
            >
              <span className="rk num">{r.rank}</span>
              <span className="nm">{r.username} ›</span>
              <span className="num">${money(r.net_worth)}</span>
              <span className="num dim" style={{ fontSize: 11 }}>${money(r.cash)} cash</span>
            </li>
          ))}
        </ol>
      </section>
    </div>
  )
}
