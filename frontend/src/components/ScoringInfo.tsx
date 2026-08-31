// Player-facing explainer: what the league's scoring mode does to dividends.
// Opened from the masthead "Scoring" chip. Data comes from /api/state.

interface ModeInfo {
  key: 'market' | 'relative' | 'lineup'
  name: string
  tag: string
  body: string
}

const MODES: ModeInfo[] = [
  {
    key: 'market',
    name: 'Market',
    tag: 'raw points',
    body:
      'Every share you hold pays its player’s fantasy points × the dividend rate. QBs post the biggest raw payouts because they score the most — but their shares also cost the most, so across a season every position returns about the same. Simplest rule: buy anyone, every share pays.',
  },
  {
    key: 'relative',
    name: 'Relative',
    tag: 'position-normalized',
    body:
      'Points are scaled by position (QB ×0.80 · RB ×0.99 · WR ×1.07 · TE ×1.23) so a share of each position pays about the same each week. In practice it tilts yield toward the cheaper positions — TEs and WRs become the value plays, QBs the tax.',
  },
  {
    key: 'lineup',
    name: 'Lineup',
    tag: 'starters only',
    body:
      'Only shares of players in your starting lineup pay — QB1 · RB2 · WR3 · TE1 · FLEX. One QB slot caps QB dividends, just like a normal league. Set your lineup before kickoff, or your best players auto-start so you’re never zeroed.',
  },
]

const FORMAT_LABEL: Record<string, string> = {
  ppr: 'Full PPR (1 pt / reception)',
  half_ppr: 'Half PPR (0.5 / reception)',
  std: 'Standard (non-PPR)',
  custom: 'Custom (imported from your league)',
}

export function ScoringInfo({
  mode,
  rate,
  format,
  dividendMode,
  onClose,
}: {
  mode: 'market' | 'relative' | 'lineup'
  rate: number
  format: 'ppr' | 'half_ppr' | 'std' | 'custom'
  dividendMode: 'snapshot' | 'accrual'
  onClose: () => void
}) {
  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="How scoring works">
        <div className="modal-head">
          <h2>How Scoring Works</h2>
          <button className="chip" onClick={onClose} type="button">
            Close
          </button>
        </div>
        <div className="modal-body">
          <div
            style={{
              display: 'flex', flexWrap: 'wrap', gap: '6px 16px', margin: '2px 0 12px',
              fontSize: 12.5,
            }}
          >
            <span className="dim">
              Points:{' '}
              <b style={{ color: 'var(--gold-hi)' }}>{FORMAT_LABEL[format] ?? format}</b>
            </span>
            <span className="dim">
              Payout:{' '}
              <b style={{ color: 'var(--ink)' }}>
                {dividendMode === 'accrual'
                  ? 'Live accrual — you earn a player’s points while you hold him'
                  : 'Own at kickoff — the whole week goes to who held him at kickoff'}
              </b>
            </span>
          </div>
          <p className="dim" style={{ fontSize: 12.5, margin: '2px 0 10px' }}>
            Every Tuesday, each share you hold pays a dividend based on last week’s fantasy points.
            The <b style={{ color: 'var(--ink)' }}>scoring mode</b> decides how points become dividends — it
            only changes dividends, never prices or your positions. Current rate:{' '}
            <span className="num" style={{ color: 'var(--gold-hi)' }}>${rate.toFixed(2)}</span> per point, per share.
          </p>
          {MODES.map((m) => {
            const active = m.key === mode
            return (
              <div
                key={m.key}
                className="release"
                style={
                  active
                    ? { borderLeft: '2px solid var(--gold)', paddingLeft: 10, marginLeft: -12 }
                    : undefined
                }
              >
                <h3>
                  {m.name} <span className="dim">· {m.tag}</span>
                  {active && (
                    <span
                      className="chip"
                      style={{ marginLeft: 8, borderColor: 'var(--gold)', color: 'var(--gold)' }}
                    >
                      Active
                    </span>
                  )}
                </h3>
                <p style={{ margin: 0, fontSize: 13, lineHeight: 1.5, color: 'var(--ink-dim)' }}>{m.body}</p>
              </div>
            )
          })}
          <p className="dim" style={{ fontSize: 11.5, marginTop: 12 }}>
            Your commissioner sets the mode for the whole league.
          </p>
        </div>
      </div>
    </div>
  )
}
