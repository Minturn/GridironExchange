export interface Me {
  user_id: number
  username: string
  is_commissioner: boolean
  league: { id: number; name: string; season: number }
  cash: number
}

export interface MarketRow {
  player_id: string
  name: string
  team: string | null
  pos: string
  price: number
  p0: number
  delta_pct: number
  spark: number[]
  last_wk_pts: number
  shares_outstanding: number
  your_shares: number
  locked: boolean
}

export interface PlayerDetail {
  player_id: string
  name: string
  team: string | null
  pos: string
  status: string | null
  price: number
  p0: number
  shares_outstanding: number
  locked_until: string | null
  your_shares: number
  series: { ts: string; price: number }[]
  holders: { username: string; shares: number }[]
  dividends: { week: number; per_share: number }[]
  weekly_pts: Record<string, number>
}

export interface Quote {
  side: string
  shares: number
  gross: number
  fee: number
  total: number
  price_avg: number
  price_after: number
  ok: boolean
  reason: string | null
}

export interface Holding {
  player_id: string
  name: string
  team: string | null
  pos: string
  shares: number
  spot: number
  mark_value: number
  avg_cost: number | null
  pnl: number | null
  dividends_earned: number
}

export interface Portfolio {
  username: string
  cash: number
  holdings: Holding[]
  net_worth: number
}

export interface ManagerBook {
  username: string
  is_you: boolean
  cash: number
  net_worth: number
  scoring_mode: string
  starters: string[]
  holdings: {
    player_id: string
    name: string
    team: string | null
    pos: string
    shares: number
    spot: number
    mark_value: number
  }[]
}

export interface BoardRow {
  rank: number
  username: string
  cash: number
  net_worth: number
  is_you: boolean
}

export interface FeedEvent {
  type: 'trade' | 'dividends'
  ts: string
  username?: string
  player_id?: string
  player_name?: string
  side?: string
  shares?: number
  price_avg?: number
  week?: number
  total?: number
}

export interface CashEvent {
  ts: string | null
  kind: 'start' | 'buy' | 'sell' | 'dividend'
  delta: number
  balance: number
  player_id: string | null
  player_name: string | null
  shares: number | null
  week: number | null
  fee: number | null
}

export interface CashHistory {
  username: string
  starting_cash: number
  cash: number
  computed_cash: number
  reconciled: boolean
  events: CashEvent[]
}

export interface AuditRow {
  username: string
  cash: number
  computed_cash: number
  drift: number
  ok: boolean
}

export interface AuditReport {
  league: string
  starting_cash: number
  all_ok: boolean
  members: AuditRow[]
}

export interface LeagueState {
  season: number
  league_name: string
  last_final_week: number
  current_week: number
  market_open: boolean
  market_opens_at: string | null
  scoring_mode: 'market' | 'relative' | 'lineup'
  dividend_multiplier: number
  in_game_trading: 'locked' | 'live'
  lineup_slots: Record<string, number>
  version: string
}

export interface LineupData {
  mode: string
  slots: Record<string, number>
  slot_keys: string[]
  flex_positions: string[]
  held: { player_id: string; name: string; pos: string; team: string | null; shares: number }[]
  saved: string[] | null
  current: string[]
}
