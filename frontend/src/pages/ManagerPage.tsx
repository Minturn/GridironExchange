import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { get, money } from '../api'
import type { ManagerBook } from '../types'

/** Read-only view of another manager's roster — rosters are public in a league. */
export function ManagerPage() {
  const { username } = useParams()
  const [book, setBook] = useState<ManagerBook | null>(null)
  const [notFound, setNotFound] = useState(false)
  const nav = useNavigate()

  useEffect(() => {
    setBook(null)
    setNotFound(false)
    if (username)
      get<ManagerBook>(`/api/manager/${encodeURIComponent(username)}`)
        .then(setBook)
        .catch(() => setNotFound(true))
  }, [username])

  if (notFound) return <div className="page dim">No such manager in your league.</div>
  if (!book) return <div className="page dim">Loading…</div>

  return (
    <div className="page">
      <section className="panel">
        <h2>
          {book.username}
          {book.is_you ? ' (you)' : ''} <em>· net worth ${money(book.net_worth)} · cash ${money(book.cash)}</em>
        </h2>
        <div className="tbl-wrap">
          <table>
            <thead>
              <tr>
                <th className="l">Player</th>
                <th>Shares</th>
                <th>Price</th>
                <th>Value</th>
              </tr>
            </thead>
            <tbody>
              {book.holdings.map((h) => (
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
                </tr>
              ))}
              {!book.holdings.length && (
                <tr>
                  <td colSpan={4} className="l dim">
                    All cash — no positions yet.
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
