import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, get, post } from '../api'
import type { LineupData } from '../types'

const baseOf = (slotKey: string) => slotKey.replace(/\d+$/, '')
const POS_RANK: Record<string, number> = { QB: 0, RB: 1, WR: 2, TE: 3, K: 4 }

export function Lineup() {
  const [data, setData] = useState<LineupData | null>(null)
  const [assign, setAssign] = useState<Record<string, string>>({})
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const nav = useNavigate()

  function load() {
    get<LineupData>('/api/lineup')
      .then((d) => {
        setData(d)
        // seed the slot dropdowns from the currently-scoring lineup
        const posById: Record<string, string> = {}
        d.held.forEach((h) => (posById[h.player_id] = h.pos))
        const a: Record<string, string> = {}
        const used = new Set<string>()
        for (const key of d.slot_keys) {
          const base = baseOf(key)
          for (const id of d.current) {
            if (used.has(id)) continue
            const pos = posById[id]
            if (!pos) continue
            const ok = base === 'FLEX' ? d.flex_positions.includes(pos) : pos === base
            if (ok) {
              a[key] = id
              used.add(id)
              break
            }
          }
        }
        setAssign(a)
      })
      .catch(() => setData(null))
  }
  useEffect(load, [])

  if (!data) return <div className="page dim">Loading…</div>
  if (data.mode !== 'lineup')
    return (
      <div className="page dim">
        This league isn’t using lineup scoring — every share you hold pays dividends. (The
        commissioner can switch modes.)
      </div>
    )

  const usedIds = new Set(Object.values(assign).filter(Boolean))
  const ORDER = ['QB', 'RB', 'WR', 'TE', 'FLEX', 'K']
  const rosterSummary = ORDER.filter((p) => data.slots[p])
    .map((p) => `${data.slots[p]} ${p}`)
    .join(' · ')
  const total = data.slot_keys.length
  const filled = data.slot_keys.filter((k) => assign[k]).length
  const complete = filled === total
  const eligibleFor = (slotKey: string, current: string) => {
    const base = baseOf(slotKey)
    return data.held
      .filter((h) => (base === 'FLEX' ? data.flex_positions.includes(h.pos) : h.pos === base))
      .filter((h) => !usedIds.has(h.player_id) || h.player_id === current)
      .sort(
        (a, b) => (POS_RANK[a.pos] ?? 9) - (POS_RANK[b.pos] ?? 9) || a.name.localeCompare(b.name),
      )
  }

  async function save() {
    setMsg(null)
    try {
      await post('/api/lineup', { player_ids: Object.values(assign).filter(Boolean) })
      setMsg({ ok: true, text: 'Lineup saved — these are the shares that will pay.' })
      load()
    } catch (e) {
      setMsg({ ok: false, text: e instanceof ApiError ? e.message : 'save failed' })
    }
  }

  return (
    <div className="page" style={{ maxWidth: 620 }}>
      <section className="panel">
        <h2>
          Your Lineup <em>· only these shares pay dividends</em>
        </h2>
        <div style={{ padding: '8px 14px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div className="lineup-status">
            <span className="dim">Requires {rosterSummary} · FLEX = any RB/WR/TE</span>
            <span className={complete ? 'ok-msg' : filled === 0 ? 'dim' : 'err'}>
              {complete ? '✓ lineup full' : `${filled} of ${total} set`}
            </span>
          </div>
          {data.held.length === 0 ? (
            <p className="dim">
              You don’t hold anyone yet — buy players on The Floor, then come set your lineup.
            </p>
          ) : (
            <>
              {data.slot_keys.map((key) => (
                <div key={key} className="lineup-row">
                  <label>{key}</label>
                  <select
                    value={assign[key] ?? ''}
                    onChange={(e) => setAssign({ ...assign, [key]: e.target.value })}
                  >
                    <option value="">— empty —</option>
                    {eligibleFor(key, assign[key] ?? '').map((h) => (
                      <option key={h.player_id} value={h.player_id}>
                        {h.name} · {h.pos} · {h.shares} sh
                      </option>
                    ))}
                  </select>
                  {assign[key] ? (
                    <button
                      className="slot-link"
                      type="button"
                      title="View player — buy or sell"
                      onClick={() => nav(`/player/${assign[key]}`)}
                    >
                      ↗
                    </button>
                  ) : (
                    <span />
                  )}
                </div>
              ))}
              {msg && <p className={msg.ok ? 'ok-msg' : 'err'}>{msg.text}</p>}
              <button className="btn solid" onClick={save} type="button">
                Save lineup
              </button>
            </>
          )}
          <p className="dim" style={{ fontSize: 12 }}>
            An empty slot scores nothing. Set no lineup at all and we auto-start your best
            players each week, so you’re never zeroed for forgetting.
          </p>
        </div>
      </section>
    </div>
  )
}
