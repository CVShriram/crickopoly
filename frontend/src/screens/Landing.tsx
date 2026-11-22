import React, { useState } from 'react'
import { useApp } from '../store'
import { Button, Panel, Badge } from '../components/UI'
import { money, timeAgo } from '../utils'

const AVATARS = ['🦁', '🦅', '🐯', '🐋', '🦘', '🦓', '🦉', '🐊']
const COLORS = ['#c8a24b', '#4fd1c5', '#f56565', '#68d391', '#b794f4', '#f6ad55', '#63b3ed', '#fc8181']

const DEFAULTS = {
  starting_credits: 1500,
  max_players: 6,
  mode: 'standard',
  season_rounds: 8,
  ai_difficulty: 'medium',
  transfer_window_every: 3,
  pitch: 'flat',
  victory_mode: 'standard_season',
}

export function Landing() {
  const { app, create, join, quick, continueRoom, dispatch, refreshSaved, joinCode } = useApp()
  const [tab, setTab] = useState<'new' | 'join' | 'quick'>(() => joinCode ? 'join' : 'new')
  const [name, setName] = useState(() => localStorage.getItem('fg-name') || 'Manager')
  const [avatar, setAvatar] = useState(() => localStorage.getItem('fg-avatar') || '🦁')
  const [color, setColor] = useState(() => localStorage.getItem('fg-color') || '#c8a24b')
  const [code, setCode] = useState(() => joinCode || '')
  const [settings, setSettings] = useState(DEFAULTS)

  const profile = { name: name.trim() || 'Manager', avatar, color }
  const saveProfile = () => {
    localStorage.setItem('fg-name', profile.name)
    localStorage.setItem('fg-avatar', avatar)
    localStorage.setItem('fg-color', color)
  }

  const switchTab = (next: 'new' | 'join' | 'quick') => {
    setTab(next)
    if (joinCode) dispatch({ type: 'JOIN_CODE', code: null })
  }

  const submitJoin = () => {
    saveProfile()
    join(code.trim().toUpperCase(), profile.name, avatar, color)
    dispatch({ type: 'JOIN_CODE', code: null })
  }

  const submitCreate = () => {
    saveProfile()
    create({ ...profile, settings })
  }

  return (
    <div className="landing">
      <div className="landing-hero">
        <div className="hero-copy">
          <Badge tone="gold" icon="✨">THE COMPLETE FRANCHISE BOARD GAME</Badge>
          <h1>BUILD A DYNASTY.<br /><span>OWN THE SEASON.</span></h1>
          <p>
            Draft a squad of 15 real cricketers from 2015-2023, explore 52 live board tiles, buy player
            markets and stadiums, submit concealed T20 tactics, and out-manage up to five rivals.
          </p>
          <div className="hero-stats">
            <div><strong>8</strong><span>Countries</span></div>
            <div><strong>96</strong><span>Real Cricketers</span></div>
            <div><strong>52</strong><span>Board Tiles</span></div>
            <div><strong>100</strong><span>Final Points</span></div>
          </div>
        </div>
        <div className="hero-card">
          <div className="hero-card-top"><span>🏏</span><div><small>SEASON PASS</small><strong>CRICKOPOLY FC</strong></div></div>
          <div className="hero-pitch">
            {Array.from({ length: 6 }).map((_, i) => <i key={i} />)}
            <span>🏟️</span>
          </div>
          <div className="hero-card-row"><span>Starting purse</span><strong>1,500 FC</strong></div>
          <div className="hero-card-row"><span>Squad / XI</span><strong>15 / 11</strong></div>
          <div className="hero-card-row"><span>Format</span><strong>T20 · 20 overs</strong></div>
        </div>
      </div>

      <div className="landing-grid">
        <Panel title="Start a franchise" subtitle="Create a private room or jump straight into a bots-only season" icon="🚀">
          <div className="profile-row">
            <div className="avatar-picker">
              {AVATARS.map(a => (
                <button key={a} type="button" className={avatar === a ? 'active' : ''} onClick={() => setAvatar(a)}>{a}</button>
              ))}
            </div>
            <div className="color-picker">
              {COLORS.map(c => (
                <button key={c} type="button" style={{ background: c }} className={color === c ? 'active' : ''}
                  onClick={() => setColor(c)} aria-label={`Colour ${c}`} />
              ))}
            </div>
          </div>
          <label className="field">
            <span>Manager / Franchise name</span>
            <input value={name} maxLength={24} onChange={e => setName(e.target.value)} placeholder="Your franchise name" />
          </label>
          <div className="tabs compact">
            <button className={tab === 'new' ? 'active' : ''} onClick={() => switchTab('new')}>New room</button>
            <button className={tab === 'join' ? 'active' : ''} onClick={() => switchTab('join')}>Join code</button>
            <button className={tab === 'quick' ? 'active' : ''} onClick={() => switchTab('quick')}>Quick play</button>
          </div>

          {tab === 'new' && (
            <div className="settings-grid">
              <label className="field"><span>Mode</span>
                <select value={settings.mode} onChange={e => setSettings({ ...settings, mode: e.target.value })}>
                  <option value="standard">Standard Season (100 pts)</option>
                  <option value="classic">Classic Survival</option>
                </select>
              </label>
              <label className="field"><span>Franchises</span>
                <select value={settings.max_players} onChange={e => setSettings({ ...settings, max_players: Number(e.target.value) })}>
                  {[2, 3, 4, 5, 6].map(n => <option key={n} value={n}>{n} managers</option>)}
                </select>
              </label>
              <label className="field"><span>League rounds</span>
                <select value={settings.season_rounds} onChange={e => setSettings({ ...settings, season_rounds: Number(e.target.value) })}>
                  {[2, 4, 6, 8, 10, 12, 16].map(n => <option key={n} value={n}>{n} rounds</option>)}
                </select>
              </label>
              <label className="field"><span>AI difficulty</span>
                <select value={settings.ai_difficulty} onChange={e => setSettings({ ...settings, ai_difficulty: e.target.value })}>
                  <option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option>
                </select>
              </label>
              <label className="field"><span>Opening pitch</span>
                <select value={settings.pitch} onChange={e => setSettings({ ...settings, pitch: e.target.value })}>
                  {Object.entries(app.gamedata?.pitches || { flat: { name: 'Flat Pitch' } }).map(([key, p]) =>
                    <option key={key} value={key}>{p.name}</option>)}
                </select>
              </label>
              <label className="field"><span>Transfer window</span>
                <select value={settings.transfer_window_every} onChange={e => setSettings({ ...settings, transfer_window_every: Number(e.target.value) })}>
                  <option value={0}>Always open</option>
                  <option value={2}>Every 2 rounds</option>
                  <option value={3}>Every 3 rounds</option>
                  <option value={4}>Every 4 rounds</option>
                </select>
              </label>
            </div>
          )}

          {tab === 'join' && (
            <>
              {joinCode && (
                <div className="callout">
                  <strong>Invite link opened</strong>
                  <p>Enter your own manager name below. You will join as a new franchise, not as the host.</p>
                </div>
              )}
              <label className="field">
                <span>Room code</span>
                <input className="code-input" value={code} maxLength={8} placeholder="ABCDE"
                  onChange={e => setCode(e.target.value.toUpperCase())} />
              </label>
            </>
          )}

          {tab === 'quick' && (
            <div className="callout">
              <strong>Instant season</strong>
              <p>Creates a 3-franchise room with two Medium AI managers and sensible defaults.</p>
            </div>
          )}

          <div className="button-row">
            {tab === 'new' && <Button onClick={submitCreate} disabled={app.busy}>Create room →</Button>}
            {tab === 'join' && <Button onClick={submitJoin}
              disabled={app.busy || code.trim().length < 4}>Join room →</Button>}
            {tab === 'quick' && <Button onClick={() => { saveProfile(); quick({ ...profile, settings: { ...DEFAULTS, max_players: 3 } }) }}
              disabled={app.busy}>Start quick play →</Button>}
          </div>
        </Panel>

        <Panel title="Continue a saved season" subtitle="Every action is persisted — refresh or restart safely" icon="💾"
          action={<Button variant="subtle" small onClick={refreshSaved}>Refresh</Button>}>
          {app.saved.length === 0 ? (
            <div className="empty"><span>💾</span><strong>No saved seasons yet</strong>
              <p>Create a room and your progress will appear here.</p></div>
          ) : (
            <div className="saved-list">
              {app.saved.slice(0, 8).map(row => (
                <button key={row.room_id} type="button" className="saved-row" onClick={() => continueRoom(row)}>
                  <span className="saved-icon">{row.finished ? '🏆' : '🏏'}</span>
                  <span className="saved-info">
                    <strong>{row.winner_name || row.franchises.join(' vs ')}</strong>
                    <small>{row.code} · Round {row.round} · {row.matches} matches · {row.mode}</small>
                  </span>
                  <span className="saved-time">{timeAgo(row.updated_at)}</span>
                </button>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <div className="feature-strip">
        <div><span>🎯</span><strong>Real T20 engine</strong><small>Phase-by-phase ball simulation with pitch, form and tactics.</small></div>
        <div><span>🔒</span><strong>Concealed plans</strong><small>Both managers submit tactics before anything is revealed.</small></div>
        <div><span>🤝</span><strong>Two-sided trades</strong><small>Contracts, venues, sponsors, cards and FC swap atomically.</small></div>
        <div><span>⚙️</span><strong>Editable roster</strong><small>Hosts can rename and re-rate players before kickoff.</small></div>
      </div>
    </div>
  )
}
