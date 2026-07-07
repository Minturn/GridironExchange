import { useEffect, useState } from 'react'

/** Countdown to the commissioner-set Week-1 start time. Everyone sees the same
 *  clock, so the market opens for the whole league at once. Hides itself the
 *  instant the clock hits zero (and /state stops sending a time once it's open). */
export function OpeningBellBanner({ opensAt }: { opensAt: string | null }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!opensAt) return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [opensAt])

  if (!opensAt) return null
  const diff = new Date(opensAt).getTime() - now
  if (diff <= 0) return null

  const d = Math.floor(diff / 86400000)
  const h = Math.floor((diff % 86400000) / 3600000)
  const m = Math.floor((diff % 3600000) / 60000)
  const s = Math.floor((diff % 60000) / 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  const clock = d > 0 ? `${d}d ${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(h)}:${pad(m)}:${pad(s)}`
  const when = new Date(opensAt).toLocaleString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  })

  return (
    <div className="bell-banner" role="status" aria-live="polite">
      <span className="bell-icon" aria-hidden="true">🏈</span>
      <span className="bell-label">Market opens in</span>
      <span className="bell-count num">{clock}</span>
      <span className="bell-when">{when} · the whole league starts together</span>
    </div>
  )
}
