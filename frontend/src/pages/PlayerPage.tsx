import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { get, post, money, ApiError } from '../api'
import type { PlayerDetail, Quote } from '../types'
import { AreaChart } from '../components/AreaChart'

export function PlayerPage({ onCashChange }: { onCashChange: () => void }) {
  const { playerId } = useParams()
  const [detail, setDetail] = useState<PlayerDetail | null>(null)
  const [side, setSide] = useState<'buy' | 'sell'>('buy')
  const [shares, setShares] = useState(5)
  const [quote, setQuote] = useState<Quote | null>(null)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    if (playerId) get<PlayerDetail>(`/api/players/${playerId}`).then(setDetail).catch(() => setDetail(null))
  }, [playerId])
  useEffect(load, [load])

  useEffect(() => {
    setQuote(null)
    if (!playerId || !shares || shares < 1) return
    const t = setTimeout(() => {
      get<Quote>(`/api/quote?player_id=${playerId}&side=${side}&shares=${shares}`)
        .then(setQuote)
        .catch(() => setQuote(null))
    }, 200)
    return () => clearTimeout(t)
  }, [playerId, side, shares, detail])

  async function place() {
    if (!playerId || !quote?.ok) return
    setBusy(true)
    setMsg(null)
    try {
      const r = await post<{ shares: number; price_avg: number; total: number }>('/api/trade', {
        player_id: playerId,
        side,
        shares,
      })
      setMsg({
        ok: true,
        text: `${side === 'buy' ? 'Bought' : 'Sold'} ${r.shares} sh @ avg $${money(r.price_avg)} — ${side === 'buy' ? 'cost' : 'received'} $${money(r.total)}`,
      })
      load()
      onCashChange()
    } catch (e) {
      setMsg({ ok: false, text: e instanceof ApiError ? e.message : 'order failed' })
    } finally {
      setBusy(false)
    }
  }

  if (!detail) return <div className="page dim">Loading…</div>

  const divTotal = detail.dividends.reduce((s, d) => s + d.per_share, 0)
  return (
    <div className="page cols">
      <section className="panel">
        <div className="pc-head">
          <span className="tkr-big">{detail.name}</span>
          <span className="pos">
            {detail.pos} · {detail.team ?? 'FA'} {detail.status && detail.status !== 'Active' ? `· ${detail.status}` : ''}
          </span>
        </div>
        <div className="pc-price">
          <span className="big num">${money(detail.price)}</span>
          {detail.locked_until && <span className="lock">LOCKED — game in progress</span>}
        </div>
        <div style={{ padding: '0 14px 8px' }}>
          <AreaChart data={detail.series.map((s) => s.price)} p0={detail.p0} width={640} height={150} />
        </div>
        <div className="pc-stats">
          <div>
            <span className="lbl">IPO (P0)</span>
            <span className="val num">${money(detail.p0)}</span>
          </div>
          <div>
            <span className="lbl">Shares out</span>
            <span className="val num">{detail.shares_outstanding}</span>
          </div>
          <div>
            <span className="lbl">Dividends/sh to date</span>
            <span className="val num up">${money(divTotal)}</span>
          </div>
        </div>
        <div className="tbl-wrap">
          <table>
            <thead>
              <tr>
                <th className="l">Week</th>
                {Object.keys(detail.weekly_pts)
                  .sort((a, b) => Number(a) - Number(b))
                  .map((w) => (
                    <th key={w}>{w}</th>
                  ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="l pmeta">PPR pts</td>
                {Object.entries(detail.weekly_pts)
                  .sort((a, b) => Number(a[0]) - Number(b[0]))
                  .map(([w, p]) => (
                    <td key={w} className="num">
                      {p.toFixed(1)}
                    </td>
                  ))}
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <aside style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
        <section className="panel">
          <h2>Order Pad</h2>
          <div className="pad">
            <div className="side">
              <button className={`buy ${side === 'buy' ? 'on' : ''}`} onClick={() => setSide('buy')} type="button">
                Buy
              </button>
              <button className={`sell ${side === 'sell' ? 'on' : ''}`} onClick={() => setSide('sell')} type="button">
                Sell
              </button>
            </div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <label htmlFor="qty">Shares</label>
              <input
                id="qty"
                style={{ width: 80, textAlign: 'right' }}
                type="number"
                min={1}
                max={1000}
                value={shares}
                onChange={(e) => setShares(Math.max(0, Math.floor(Number(e.target.value))))}
              />
              <span className="pmeta">you hold {detail.your_shares}</span>
            </div>
            {quote && (
              <p className="quote num">
                {quote.shares} sh ≈ <b>${money(quote.total)}</b> {side === 'buy' ? 'incl.' : 'after'} fee ·
                avg <b>${money(quote.price_avg)}</b> · moves price to <b>${money(quote.price_after)}</b>
                {!quote.ok && quote.reason && (
                  <>
                    <br />
                    <span className="err">{quote.reason}</span>
                  </>
                )}
              </p>
            )}
            {msg && <p className={msg.ok ? 'ok-msg' : 'err'}>{msg.text}</p>}
            <button
              className={`btn ${side === 'buy' ? 'solid' : 'danger'}`}
              disabled={busy || !quote?.ok || !!detail.locked_until}
              onClick={place}
              type="button"
            >
              {side === 'buy' ? 'Place buy' : 'Place sell'}
            </button>
          </div>
        </section>

        <section className="panel board">
          <h2>
            Held by <em>· {detail.holders.length}</em>
          </h2>
          <ol>
            {detail.holders.map((h, i) => (
              <li key={h.username}>
                <span className="rk num">{i + 1}</span>
                <span className="nm">{h.username}</span>
                <span className="num">{h.shares} sh</span>
                <span />
              </li>
            ))}
            {!detail.holders.length && <li className="dim" style={{ display: 'block' }}>Nobody yet — be first.</li>}
          </ol>
        </section>
      </aside>
    </div>
  )
}
