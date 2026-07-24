import { useCallback, useEffect, useState } from 'react'
import { HashRouter, NavLink, Route, Routes } from 'react-router-dom'
import { get, post, money, ApiError } from './api'
import type { LeagueState, MarketRow, Me } from './types'
import { Ticker } from './components/Ticker'
import { OpeningBellBanner } from './components/OpeningBell'
import { WhatsNew } from './components/WhatsNew'
import { ScoringInfo } from './components/ScoringInfo'
import { APP_VERSION } from './releaseNotes'
import { Login } from './pages/Login'
import { Floor } from './pages/Floor'
import { PlayerPage } from './pages/PlayerPage'
import { Portfolio } from './pages/Portfolio'
import { CashHistory } from './pages/CashHistory'
import { Leaderboard } from './pages/Leaderboard'
import { ManagerPage } from './pages/ManagerPage'
import { Lineup } from './pages/Lineup'
import { Tape } from './pages/Tape'
import { Commissioner } from './pages/Commissioner'

export default function App() {
  const [me, setMe] = useState<Me | null>(null)
  const [checked, setChecked] = useState(false)
  const [market, setMarket] = useState<MarketRow[]>([])
  const [state, setState] = useState<LeagueState | null>(null)
  const [whatsNew, setWhatsNew] = useState(false)
  const [scoringInfo, setScoringInfo] = useState(false)

  const refreshMe = useCallback(() => {
    get<Me>('/api/auth/me')
      .then(setMe)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) setMe(null)
      })
      .finally(() => setChecked(true))
  }, [])

  const refreshMarket = useCallback(() => {
    get<MarketRow[]>('/api/market').then(setMarket).catch(() => {})
    get<LeagueState>('/api/state').then(setState).catch(() => {})
  }, [])

  useEffect(refreshMe, [refreshMe])
  useEffect(() => {
    if (!me) return
    refreshMarket()
    const t = setInterval(refreshMarket, 15000)
    return () => clearInterval(t)
  }, [me, refreshMarket])

  if (!checked) return null
  if (!me) return <Login onAuthed={(m) => setMe(m)} />

  async function signOut() {
    await post('/api/auth/logout')
    setMe(null)
  }

  return (
    <HashRouter>
      <header className="mast">
        <div className="wordmark">
          Gridiron <b>Exchange</b>
        </div>
        <div className="sess">
          {state && (
            <span className="chip live">
              {state.league_name} · Wk {state.current_week}
            </span>
          )}
          {state && (
            <button
              className="chip"
              onClick={() => setScoringInfo(true)}
              type="button"
              title="How scoring works"
            >
              Scoring · {state.scoring_mode}
            </button>
          )}
          {state?.in_game_trading === 'live' && (
            <span
              className="chip"
              style={{ borderColor: 'var(--scarlet)', color: 'var(--scarlet-hi)' }}
              title="In-game trading is live — stocks stay tradeable during games"
            >
              ● Live
            </span>
          )}
          <span>
            Cash <span className="cash num">${money(me.cash)}</span>
          </span>
          <span className="dim">{me.username}</span>
          <button className="chip" onClick={() => setWhatsNew(true)} type="button" title="What’s new / version">
            v{APP_VERSION}
          </button>
          {state?.version && state.version !== APP_VERSION && (
            <button className="chip update" onClick={() => window.location.reload()} type="button">
              update ⟳
            </button>
          )}
          <button className="chip" onClick={signOut} type="button">
            Sign out
          </button>
        </div>
        <nav className="nav">
          <NavLink to="/" end className={({ isActive }) => (isActive ? 'active' : '')}>
            The Floor
          </NavLink>
          <NavLink to="/portfolio" className={({ isActive }) => (isActive ? 'active' : '')}>
            Your Book
          </NavLink>
          <NavLink to="/cash" className={({ isActive }) => (isActive ? 'active' : '')}>
            Cash Ledger
          </NavLink>
          {state?.scoring_mode === 'lineup' && (
            <NavLink to="/lineup" className={({ isActive }) => (isActive ? 'active' : '')}>
              Lineup
            </NavLink>
          )}
          <NavLink to="/standings" className={({ isActive }) => (isActive ? 'active' : '')}>
            Standings
          </NavLink>
          <NavLink to="/tape" className={({ isActive }) => (isActive ? 'active' : '')}>
            The Tape
          </NavLink>
          {me.is_commissioner && (
            <NavLink to="/commish" className={({ isActive }) => (isActive ? 'active' : '')}>
              Commissioner
            </NavLink>
          )}
        </nav>
      </header>
      <Ticker rows={market} />
      <OpeningBellBanner opensAt={state?.market_opens_at ?? null} />
      <Routes>
        <Route path="/" element={<Floor rows={market} />} />
        <Route path="/player/:playerId" element={<PlayerPage onCashChange={refreshMe} />} />
        <Route path="/portfolio" element={<Portfolio />} />
        <Route path="/cash" element={<CashHistory />} />
        <Route path="/standings" element={<Leaderboard />} />
        <Route path="/manager/:username" element={<ManagerPage />} />
        <Route path="/lineup" element={<Lineup />} />
        <Route path="/tape" element={<Tape />} />
        {me.is_commissioner && <Route path="/commish" element={<Commissioner />} />}
      </Routes>
      <p className="foot">
        GRIDIRON EXCHANGE · league money only — never real currency · gold = up · scarlet = down
      </p>
      {whatsNew && <WhatsNew onClose={() => setWhatsNew(false)} />}
      {scoringInfo && state && (
        <ScoringInfo
          mode={state.scoring_mode}
          rate={state.dividend_multiplier}
          onClose={() => setScoringInfo(false)}
        />
      )}
    </HashRouter>
  )
}
