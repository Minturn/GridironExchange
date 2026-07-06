import { useEffect, useState } from 'react'
import { get, money } from '../api'
import type { FeedEvent } from '../types'

function when(ts: string) {
  const d = new Date(ts + 'Z')
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export function Tape() {
  const [events, setEvents] = useState<FeedEvent[]>([])
  useEffect(() => {
    get<FeedEvent[]>('/api/feed').then(setEvents).catch(() => setEvents([]))
    const t = setInterval(() => get<FeedEvent[]>('/api/feed').then(setEvents).catch(() => {}), 15000)
    return () => clearInterval(t)
  }, [])
  return (
    <div className="page">
      <section className="panel feed">
        <h2>
          The Tape <em>· every trade is public</em>
        </h2>
        <ul>
          {events.map((e, i) => (
            <li key={i}>
              <span className="t num">{when(e.ts)}</span>
              {e.type === 'trade' ? (
                <>
                  <span className="who">{e.username}</span>
                  <span>
                    {e.side === 'buy' ? 'bought' : 'sold'} {e.shares}{' '}
                    <span className="tkr">{e.player_name}</span> @{' '}
                    <span className="num">${money(e.price_avg ?? 0)}</span>
                  </span>
                </>
              ) : (
                <>
                  <span className="who">—</span>
                  <span>
                    Week {e.week} dividends posted — <span className="up num">${money(e.total ?? 0)}</span> league-wide
                  </span>
                </>
              )}
            </li>
          ))}
          {!events.length && <li className="dim">Quiet so far — trades and dividends land here.</li>}
        </ul>
      </section>
    </div>
  )
}
