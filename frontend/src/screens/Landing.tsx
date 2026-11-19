import { useState } from 'react'
import { api } from '../api'
import { useApp } from '../store'
import { sound } from '../sound'

const AVATARS = ['🏏', '🦁', '🦅', '🐯', '🦊', '🐺', '🦅', '⚡', '🔥', '🛡️', '🎯', '🏆']
const COLORS = ['#22c55e', '#38bdf8', '#f59e0b', '#f43f5e', '#a78bfa', '#14b8a6']

export function Landing() {
  const { dispatch } = useApp()
  const [name, setName] = useState(() => localStorage.getItem('cm-name') || '')
  const [avatar, setAvatar] = useState('🏏')
  const [color, setColor] = useState(COLORS[0])
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [victoryMode, setVictoryMode] = useState('last_standing')
  const [turnLimit, setTurnLimit] = useState(20)

  const playBots = async () => {
    if (!name.trim()) { setError('Enter your manager name first.'); return }
    setBusy(true); setError('')
    localStorage.setItem('cm-name', name.trim())
    try {
      const result = await api.quickMatch(name.trim(), 2, 'smart', victoryMode, turnLimit)
      sound.play('victory')
      dispatch({
        type: 'SESSION',
        session: { code: result.code, playerId: result.player_id,
                   name: name.trim(), avatar, color },
      })
      dispatch({ type: 'VIEW', view: 'game' })
    } catch (err: any) {
      setError(err.message || 'Could not start a bot match')
    } finally { setBusy(false) }
  }

  const enter = async (mode: 'create' | 'join') => {
    if (!name.trim()) { setError('Enter your manager name first.'); return }
    if (mode === 'join' && code.trim().length < 4) { setError('Enter a valid room code.'); return }
    setBusy(true); setError('')
    localStorage.setItem('cm-name', name.trim())
    try {
      const result = mode === 'create'
        ? await api.createRoom(name.trim(), avatar, color)
        : await api.joinRoom(code.trim().toUpperCase(), name.trim(), avatar, color)
      sound.play('buy')
      dispatch({
        type: 'SESSION',
        session: { code: result.code, playerId: result.player_id, name: name.trim(), avatar, color },
      })
      dispatch({ type: 'VIEW', view: 'lobby' })
    } catch (err: any) {
      setError(err.message || 'Could not connect to the server')
    } finally { setBusy(false) }
  }

  return (
    <div className="landing">
      <div className="landing-glow" />
      <header className="landing-nav">
        <div className="brand-mark"><span className="brand-ball">🏏</span> CRICKET <b>MONOPOLY</b></div>
        <nav>
          <button onClick={() => dispatch({ type: 'VIEW', view: 'howto' })}>How to play</button>
          <button onClick={() => dispatch({ type: 'VIEW', view: 'leaderboard' })}>Leaderboard</button>
        </nav>
      </header>

      <main className="landing-main">
        <div className="hero">
          <div className="hero-tag">THE ULTIMATE CRICKET STRATEGY ARENA</div>
          <h1>Build a squad.<br /><span>Bowl them out.</span><br />Survive the innings.</h1>
          <p className="hero-copy">
            Draft a cricket legend or create your own, build a five-batsman squad, and outlast
            three rivals in a real-time cricket economy. Every wicket counts. Every six scales.
          </p>
          <div className="hero-feats">
            <div><strong>32</strong><span>Board spaces</span></div>
            <div><strong>4</strong><span>Managers</span></div>
            <div><strong>5</strong><span>Batsmen per squad</span></div>
          </div>
        </div>

        <div className="entry-card">
          <div className="entry-head">
            <span className="eyebrow">ENTER THE ARENA</span>
            <h2>Create your manager</h2>
          </div>
          <label className="field">
            <span>Manager name</span>
            <input value={name} maxLength={20} placeholder="e.g. DhoniFan_07"
              onChange={e => setName(e.target.value)} />
          </label>
          <div className="field">
            <span>Avatar</span>
            <div className="avatar-grid">
              {AVATARS.map((a, i) => (
                <button key={i} className={avatar === a ? 'selected' : ''} onClick={() => { setAvatar(a); sound.play('click') }}>{a}</button>
              ))}
            </div>
          </div>
          <div className="field">
            <span>Team colour</span>
            <div className="color-grid">
              {COLORS.map(c => (
                <button key={c} style={{ background: c }} className={color === c ? 'selected' : ''}
                  onClick={() => { setColor(c); sound.play('click') }} />
              ))}
            </div>
          </div>
          <label className="field">
            <span>Room code <em>(to join a friend)</em></span>
            <input value={code} maxLength={6} placeholder="ABC123" className="code-input"
              onChange={e => setCode(e.target.value.toUpperCase())} />
          </label>
          {error && <p className="form-error">{error}</p>}
          <div className="entry-actions">
            <button className="btn primary large" disabled={busy} onClick={() => enter('create')}>
              {busy ? 'Creating…' : 'Create room'}
            </button>
            <button className="btn ghost large" disabled={busy} onClick={() => enter('join')}>Join room</button>
          </div>
          <div className="quick-settings">
            <label className="field compact"><span>Win condition</span>
              <select value={victoryMode} onChange={e => setVictoryMode(e.target.value)}>
                <option value="last_standing">Last manager standing</option>
                <option value="turn_limit">Turn-limit ranking</option>
              </select>
            </label>
            {victoryMode === 'turn_limit' && (
              <label className="field compact"><span>Rounds</span>
                <input type="number" min={1} max={200} value={turnLimit}
                  onChange={e => setTurnLimit(Number(e.target.value) || 1)} />
              </label>
            )}
          </div>
          <button className="btn gold large quick-bots" disabled={busy} onClick={playBots}>
            {busy ? 'Starting…' : '⚡ Play vs Bots (instant match)'}
          </button>
          <p className="hint">Instant matches auto-draft your opening batsman. Create a room to choose a famous cricketer or customise your own.</p>
          <p className="entry-foot">No account needed. Share your room code to invite friends.</p>
        </div>
      </main>
    </div>
  )
}
