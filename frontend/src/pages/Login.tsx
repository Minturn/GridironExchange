import { useState } from 'react'
import { post } from '../api'
import type { Me } from '../types'

export function Login({ onAuthed }: { onAuthed: (me: Me) => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [invite, setInvite] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setErr(null)
    setBusy(true)
    try {
      const me =
        mode === 'login'
          ? await post<Me>('/api/auth/login', { username, password })
          : await post<Me>('/api/auth/register', { invite_code: invite, username, password })
      onAuthed(me)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'something went wrong')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-wrap">
      <form className="login panel" onSubmit={submit}>
        <div className="wordmark">
          Gridiron <b>Exchange</b>
        </div>
        <p className="dim" style={{ margin: 0, fontSize: 12 }}>
          Your league, traded like a market. Gold = up, scarlet = down.
        </p>
        {mode === 'register' && (
          <div className="field">
            <label htmlFor="invite">Invite code</label>
            <input id="invite" value={invite} onChange={(e) => setInvite(e.target.value)} required />
          </div>
        )}
        <div className="field">
          <label htmlFor="user">Name</label>
          <input id="user" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />
        </div>
        <div className="field">
          <label htmlFor="pw">Password</label>
          <input id="pw" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </div>
        {err && <p className="err">{err}</p>}
        <button className="btn solid" disabled={busy} type="submit">
          {mode === 'login' ? 'Sign in' : 'Join the league'}
        </button>
        <button
          type="button"
          className="chip"
          onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
        >
          {mode === 'login' ? 'New here? Join with an invite code' : 'Have an account? Sign in'}
        </button>
      </form>
    </div>
  )
}
