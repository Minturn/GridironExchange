import { useEffect, useState } from 'react'
import { get, money } from '../api'
import type { CashEvent, CashHistory as CashHistoryT } from '../types'

const when = (ts: string | null) =>
  ts
    ? new Date(ts).toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
      })
    : '—'

function label(e: CashEvent): string {
  switch (e.kind) {
    case 'start':
      return 'Opening balance'
    case 'buy':
      return `Bought ${e.shares} ${e.player_name ?? e.player_id}`
    case 'sell':
      return `Sold ${e.shares} ${e.player_name ?? e.player_id}`
    case 'dividend':
      return `Dividend · Wk ${e.week} · ${e.player_name ?? e.player_id}`
  }
}

export function CashHistory() {
  const [h, setH] = useState<CashHistoryT | null>(null)
  useEffect(() => {
    get<CashHistoryT>('/api/cash-history').then(setH).catch(() => setH(null))
  }, [])
  if (!h) return <div className="page dim">Loading…</div>
  return (
    <div className="page">
      <section className="panel">
        <h2>
          Cash Ledger <em>· current cash ${money(h.cash)}</em>
        </h2>
        <p className="dim" style={{ fontSize: 12, marginTop: -4 }}>
          Every dollar in and out, newest first — opening balance ${money(h.starting_cash)}, then each
          trade and dividend. Cash goes up only when you sell or a dividend pays; it never moves on its own.
        </p>
        {h.reconciled ? (
          <p className="chip live" style={{ display: 'inline-block' }}>
            ✓ Reconciled — this ledger reproduces your ${money(h.cash)} exactly.
          </p>
        ) : (
          <p className="err">
            ⚠ Does not reconcile: replaying the ledger gives ${money(h.computed_cash)} but your balance is $
            {money(h.cash)}. Tell the commissioner.
          </p>
        )}
        <div className="tbl-wrap">
          <table className="book-table">
            <thead>
              <tr>
                <th className="l">When</th>
                <th className="l">Activity</th>
                <th>Change</th>
                <th>Cash balance</th>
              </tr>
            </thead>
            <tbody>
              {h.events.map((e, i) => (
                <tr key={i}>
                  <td className="l dim">{when(e.ts)}</td>
                  <td className="l">
                    <span className="pname">{label(e)}</span>
                    {e.fee != null && e.fee > 0 && (
                      <span className="pmeta"> · fee ${money(e.fee)}</span>
                    )}
                  </td>
                  <td className={`num ${e.kind === 'start' ? 'dim' : e.delta >= 0 ? 'up' : 'dn'}`}>
                    {e.kind === 'start'
                      ? `$${money(e.delta)}`
                      : `${e.delta >= 0 ? '+' : '−'}$${money(Math.abs(e.delta))}`}
                  </td>
                  <td className="num">${money(e.balance)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
