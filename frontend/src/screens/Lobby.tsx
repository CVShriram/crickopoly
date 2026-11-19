import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApp } from '../store'
import { sound } from '../sound'
import { BatsmanAvatar } from '../components/BatsmanAvatar'
import type { Selection } from '../types'

const JERSEY_COLORS = ['#1e40af', '#22c55e', '#dc2626', '#facc15', '#7c3aed', '#065f46', '#0f172a']
const AVATARS = ['🏏', '🧤', '🎯', '🦁', '🦅', '⚡', '🔥', '🛡️']

export function Lobby() {
  const { app, dispatch, send, disconnect } = useApp()
  const state = app.state
  const config = app.config
  const me = state?.players.find(p => p.id === app.session?.playerId)
  const isHost = !!me?.is_host
  const [copied, setCopied] = useState(false)
  const [tab, setTab] = useState<'famous' | 'custom'>('famous')
  const [custom, setCustom] = useState<Selection>(() => ({ ...(config?.custom_defaults || {}) }))
  const [turnLimit, setTurnLimit] = useState(config?.default_turn_limit || 20)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (config?.custom_defaults) setCustom({ ...config.custom_defaults })
    if (config?.default_turn_limit) setTurnLimit(config.default_turn_limit)
  }, [config])

  const copy = async () => {
    if (!state) return
    try { await navigator.clipboard.writeText(state.code) } catch { /* clipboard optional */ }
    setCopied(true); sound.play('click')
    window.setTimeout(() => setCopied(false), 1600)
  }

  const leave = () => {
    disconnect()
    dispatch({ type: 'SESSION', session: null })
    dispatch({ type: 'STATE', state: null })
    dispatch({ type: 'VIEW', view: 'landing' })
  }

  const inviteBot = async () => {
    if (!state) return
    setBusy(true)
    try {
      const next = await api.addBots(state.code, 1, 'smart')
      dispatch({ type: 'STATE', state: next })
      sound.play('buy')
    } catch { /* host may not be able to add bots */ }
    finally { setBusy(false) }
  }

  if (!state || !me) return <div className="screen-bg loading-screen">Connecting to room…</div>

  const famous = config?.famous_batsmen || {}
  const claimed = new Set(state.players
    .filter(p => p.id !== me.id && p.selection?.identity_id)
    .map(p => p.selection.identity_id as string))
  const humans = state.players.filter(p => !p.is_bot)
  const humansSelected = humans.every(p => p.selection && (p.selection.identity_id || p.selection.is_custom))
  const enoughPlayers = state.players.length >= 2
  const meSelected = !!(me.selection && (me.selection.identity_id || me.selection.is_custom))

  const selectFamous = (key: string) => {
    sound.play('click')
    send('select_batsman', { identity_id: key })
  }

  const submitCustom = () => {
    if (!String(custom.name || '').trim()) {
      dispatch({ type: 'ERROR', error: 'Give your batsman a name first.' })
      return
    }
    sound.play('buy')
    send('create_batsman', { custom: { ...custom, name: String(custom.name).trim() } })
  }

  const applyVictory = () => {
    sound.play('click')
    send('victory_mode', { mode: state.victory_mode, turn_limit: turnLimit })
  }

  return (
    <div className="lobby screen-bg draft-screen">
      <header className="screen-topbar">
        <div className="brand-mark small"><span className="brand-ball">🏏</span> CRICKET <b>MONOPOLY</b></div>
        <button className="btn ghost small" onClick={leave}>← Leave room</button>
      </header>

      <div className="draft-layout">
        <section className="draft-side">
          <div className="lobby-card">
            <span className="eyebrow">PLAYER LOBBY</span>
            <h1>Gather your rivals</h1>
            <p className="muted">Share this code with friends, then choose your opening batsman.</p>
            <button className="room-code" onClick={copy}>
              <span>{state.code}</span><small>{copied ? 'Copied!' : 'Click to copy'}</small>
            </button>
            <div className={`connection-pill ${app.connected ? 'online' : ''}`}>
              {app.connected ? '● Connected — state is live' : '○ Reconnecting…'}
            </div>
          </div>

          <div className="lobby-card players-card">
            <div className="panel-heading">
              <span className="eyebrow">MANAGERS</span>
              <h3>{state.players.length} / 4 ready</h3>
            </div>
            <div className="lobby-players">
              {state.players.map(player => {
                const identity = player.selection?.identity_id ? famous[player.selection.identity_id] : null
                return (
                  <div key={player.id} className={`lobby-player ${player.id === me.id ? 'me' : ''}`}
                    style={{ ['--accent' as any]: player.color }}>
                    <div className="lobby-avatar" style={{ background: player.color }}>{player.avatar}</div>
                    <div className="lobby-player-info">
                      <strong>{player.name} {player.id === me.id && <span className="you-tag">YOU</span>}</strong>
                      <span className="muted">
                        {player.is_bot ? 'AI manager' : identity?.name || (player.selection?.name ?? 'Choosing batsman…')}
                      </span>
                    </div>
                    {player.is_bot ? <span className="ready-badge bot"><span className="bot-tag">BOT</span></span>
                      : <span className={`ready-badge ${player.selection ? 'ready' : ''}`}>
                          {player.selection ? '✓ Picked' : 'Pick a batsman'}
                        </span>}
                  </div>
                )
              })}
              {Array.from({ length: Math.max(0, 4 - state.players.length) }).map((_, i) => (
                <div key={i} className="lobby-player empty"><span>Waiting for manager…</span></div>
              ))}
            </div>
          </div>

          {isHost && (
            <div className="lobby-card victory-settings">
              <div className="panel-heading"><span className="eyebrow">HOST SETTINGS</span><h3>Victory</h3></div>
              <label className="field compact">
                <span>Mode</span>
                <select value={state.victory_mode} onChange={e => {
                  send('victory_mode', { mode: e.target.value, turn_limit: turnLimit })
                }}>
                  <option value="last_standing">Last manager standing</option>
                  <option value="turn_limit">Turn-limit ranking</option>
                </select>
              </label>
              {state.victory_mode === 'turn_limit' && (
                <label className="field compact">
                  <span>Rounds</span>
                  <div className="inline-field">
                    <input type="number" min={1} max={200} value={turnLimit}
                      onChange={e => setTurnLimit(Number(e.target.value) || 1)} />
                    <button className="btn ghost small" onClick={applyVictory}>Apply</button>
                  </div>
                </label>
              )}
              <button className="btn ghost small" disabled={busy || state.players.length >= 4} onClick={inviteBot}>
                {busy ? 'Adding…' : '+ Add smart bot'}
              </button>
            </div>
          )}
        </section>

        <section className="draft-main">
          <div className="draft-header">
            <div>
              <span className="eyebrow">OPENER SELECTION</span>
              <h2>Choose your first batsman</h2>
              <p className="muted">One pick per manager. Every cricketer starts with 3 wickets and identical stats.</p>
            </div>
            {meSelected && <div className="draft-confirmed">✓ Opening batsman locked in</div>}
          </div>

          <div className="draft-tabs">
            <button className={tab === 'famous' ? 'active' : ''} onClick={() => { setTab('famous'); sound.play('click') }}>
              Famous cricketers
            </button>
            <button className={tab === 'custom' ? 'active' : ''} onClick={() => { setTab('custom'); sound.play('click') }}>
              Create your own
            </button>
          </div>

          {tab === 'famous' ? (
            <div className="famous-grid">
              {Object.entries(famous).map(([key, info]) => {
                const taken = claimed.has(key)
                const selected = me.selection?.identity_id === key
                return (
                  <button key={key} className={`famous-card ${selected ? 'selected' : ''} ${taken ? 'taken' : ''}`}
                    disabled={taken} onClick={() => selectFamous(key)}
                    style={{ ['--jersey' as any]: info.jersey_color }}>
                    <BatsmanAvatar person={{ ...info, skin: '#f1c27d', hair: 'short', face: 'smile' }} size="small" />
                    <strong>{info.name}</strong>
                    <span>{info.country}</span>
                    <em>#{info.jersey_number}</em>
                    {taken && <b className="taken-tag">TAKEN</b>}
                    {selected && <b className="chosen-tag">✓ YOURS</b>}
                  </button>
                )
              })}
            </div>
          ) : (
            <div className="customizer">
              <div className="customizer-preview">
                <BatsmanAvatar person={custom} size="large" />
                <strong>{custom.name || 'Your Batsman'}</strong>
                <span>{custom.country} · #{custom.jersey_number ?? 18}</span>
              </div>
              <div className="customizer-form">
                <label className="field compact"><span>Name</span>
                  <input maxLength={24} value={String(custom.name || '')}
                    onChange={e => setCustom(c => ({ ...c, name: e.target.value }))} placeholder="e.g. The Boundary King" />
                </label>
                <label className="field compact"><span>Country / team</span>
                  <select value={String(custom.country || 'Custom')}
                    onChange={e => setCustom(c => ({ ...c, country: e.target.value }))}>
                    {(config?.custom_countries || ['Custom']).map(country =>
                      <option key={country} value={country}>{country}</option>)}
                  </select>
                </label>
                <div className="field-row">
                  <label className="field compact"><span>Jersey number</span>
                    <input type="number" min={0} max={999} value={Number(custom.jersey_number ?? 18)}
                      onChange={e => setCustom(c => ({ ...c, jersey_number: Number(e.target.value) }))} />
                  </label>
                  <label className="field compact"><span>Jersey colour</span>
                    <input type="color" value={String(custom.jersey_color || '#22c55e')}
                      onChange={e => setCustom(c => ({ ...c, jersey_color: e.target.value }))} />
                  </label>
                </div>
                <div className="swatch-row">
                  {JERSEY_COLORS.map(color => (
                    <button key={color} className={`swatch ${custom.jersey_color === color ? 'selected' : ''}`}
                      style={{ background: color }} onClick={() => setCustom(c => ({ ...c, jersey_color: color }))} />
                  ))}
                </div>
                <div className="field"><span>Icon</span>
                  <div className="mini-grid">
                    {AVATARS.map(a => (
                      <button key={a} className={custom.avatar === a ? 'selected' : ''}
                        onClick={() => setCustom(c => ({ ...c, avatar: a }))}>{a}</button>
                    ))}
                  </div>
                </div>
                <div className="field"><span>Skin</span>
                  <div className="swatch-row">
                    {(config?.custom_skin_options || ['#fde3c8', '#f1c27d', '#d8a06a', '#a9653c', '#6b3f24']).map(color => (
                      <button key={color} className={`swatch ${custom.skin === color ? 'selected' : ''}`}
                        style={{ background: color }} onClick={() => setCustom(c => ({ ...c, skin: color }))} />
                    ))}
                  </div>
                </div>
                <div className="field-row">
                  <label className="field compact"><span>Hairstyle</span>
                    <select value={String(custom.hair || 'short')}
                      onChange={e => setCustom(c => ({ ...c, hair: e.target.value }))}>
                      {(config?.custom_hair_options || ['short', 'spiky', 'long', 'curly', 'bald']).map(h =>
                        <option key={h} value={h}>{h}</option>)}
                    </select>
                  </label>
                  <label className="field compact"><span>Hair colour</span>
                    <input type="color" value={String(custom.hair_color || '#2d1b0e')}
                      onChange={e => setCustom(c => ({ ...c, hair_color: e.target.value }))} />
                  </label>
                </div>
                <label className="field compact"><span>Expression</span>
                  <select value={String(custom.face || 'smile')}
                    onChange={e => setCustom(c => ({ ...c, face: e.target.value }))}>
                    {(config?.custom_face_options || ['smile', 'grin', 'focused', 'determined']).map(f =>
                      <option key={f} value={f}>{f}</option>)}
                  </select>
                </label>
                <button className="btn primary large" onClick={submitCustom}>Use this batsman</button>
              </div>
            </div>
          )}

          <div className="draft-footer">
            {isHost ? (
              <button className="btn gold large" disabled={!enoughPlayers || !humansSelected}
                onClick={() => { sound.play('victory'); send('start') }}>
                Start match →
              </button>
            ) : (
              <div className="waiting-note">Waiting for the host to start the match…</div>
            )}
            {!enoughPlayers && <p className="hint">At least 2 managers are needed.</p>}
            {!humansSelected && <p className="hint">Each human manager must choose an opening batsman.</p>}
          </div>
        </section>
      </div>
    </div>
  )
}
