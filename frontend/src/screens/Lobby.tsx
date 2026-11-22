import React, { useState } from 'react'
import { useApp } from '../store'
import type { LobbyState } from '../types'
import { Avatar, Badge, Button, Empty, Panel } from '../components/UI'

export function Lobby() {
  const { app, send, dispatch } = useApp()
  const lobby = app.state as unknown as LobbyState | null
  const [count, setCount] = useState(2)
  const [difficulty, setDifficulty] = useState('medium')
  const [copied, setCopied] = useState(false)
  if (!lobby) return <Empty title="Loading room…" />

  const members = lobby.members || []
  const isHost = lobby.host_id === app.session?.playerId
  const meMember = members.find(m => m.id === app.session?.playerId)
  const canStart = members.length >= 2 && members.every(m => m.is_bot || m.ready)

  const patch = (settings: Record<string, unknown>) => send('settings', { settings })
  const share = () => {
    // Share only the room code. Never put the host token in an invite link.
    const url = `${window.location.origin}${window.location.pathname}?code=${lobby.code}&join=1`
    navigator.clipboard?.writeText(url).then(() => {
      setCopied(true); window.setTimeout(() => setCopied(false), 1800)
    }).catch(() => dispatch({ type: 'ERROR', error: url }))
  }

  return (
    <div className="page lobby-page">
      <div className="page-head">
        <div><small>PRIVATE ROOM</small><h1>Franchise Lobby</h1><p>Invite managers, add AI rivals and tune the season before kickoff.</p></div>
        <Button variant="gold" onClick={share}>{copied ? '✓ Link copied' : '🔗 Copy invite link'}</Button>
      </div>

      <div className="lobby-grid">
        <Panel title="Room" subtitle={lobby.code} icon="🏟️" action={<Badge tone="gold">{members.length}/6 managers</Badge>}>
          <div className="code-display">
            <span>{lobby.code}</span>
            <small>Share this code so friends can join from the landing screen.</small>
          </div>
          <div className="member-list">
            {members.map((m, idx) => (
              <div key={m.id} className="member-row">
                <Avatar franchise={m as any} />
                <div className="member-name"><strong>{m.name}</strong>
                  <small>{m.is_bot ? `${m.difficulty} AI manager` : idx === 0 ? 'Room host' : 'Human manager'}</small></div>
                {m.is_host && <Badge tone="gold">HOST</Badge>}
                {m.is_bot ? <Badge tone="blue">BOT</Badge>
                  : <Badge tone={m.ready ? 'green' : 'danger'}>{m.ready ? 'READY' : 'NOT READY'}</Badge>}
              </div>
            ))}
          </div>
          {!meMember?.is_bot && (
            <Button variant={meMember?.ready ? 'subtle' : 'primary'} block
              onClick={() => send('ready', { ready: !meMember?.ready })}>
              {meMember?.ready ? 'Mark not ready' : 'I am ready'}
            </Button>
          )}
        </Panel>

        <Panel title="Season settings" subtitle={isHost ? 'Host controls' : 'Only the host can edit these'} icon="⚙️">
          <label className="field"><span>Game mode</span>
            <select disabled={!isHost} value={lobby.settings?.mode || 'standard'}
              onChange={e => patch({ mode: e.target.value })}>
              <option value="standard">Standard Season — 100-point final table</option>
              <option value="classic">Classic Survival — last franchise standing</option>
            </select>
          </label>
          <div className="two-col">
            <label className="field"><span>Franchises</span>
              <select disabled={!isHost} value={lobby.settings?.max_players || 6}
                onChange={e => patch({ max_players: Number(e.target.value) })}>
                {[2, 3, 4, 5, 6].map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            <label className="field"><span>League rounds</span>
              <select disabled={!isHost} value={lobby.settings?.season_rounds || 8}
                onChange={e => patch({ season_rounds: Number(e.target.value) })}>
                {[2, 4, 6, 8, 10, 12, 16].map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
          </div>
          <div className="two-col">
            <label className="field"><span>Starting balance</span>
              <select disabled={!isHost} value={lobby.settings?.starting_credits || 1500}
                onChange={e => patch({ starting_credits: Number(e.target.value) })}>
                {[1000, 1500, 2000, 2500].map(n => <option key={n} value={n}>{n} FC</option>)}
              </select>
            </label>
            <label className="field"><span>Opening pitch</span>
              <select disabled={!isHost} value={lobby.settings?.pitch || 'flat'}
                onChange={e => patch({ pitch: e.target.value })}>
                {Object.entries(app.gamedata?.pitches || { flat: { name: 'Flat' } }).map(([key, p]) =>
                  <option key={key} value={key}>{p.name}</option>)}
              </select>
            </label>
          </div>
          <div className="two-col">
            <label className="field"><span>AI difficulty</span>
              <select disabled={!isHost} value={lobby.settings?.ai_difficulty || 'medium'}
                onChange={e => { setDifficulty(e.target.value); patch({ ai_difficulty: e.target.value }) }}>
                <option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option>
              </select>
            </label>
            <label className="field"><span>Transfer window</span>
              <select disabled={!isHost} value={lobby.settings?.transfer_window_every ?? 3}
                onChange={e => patch({ transfer_window_every: Number(e.target.value) })}>
                <option value={0}>Always</option><option value={2}>Every 2 rounds</option>
                <option value={3}>Every 3 rounds</option><option value={4}>Every 4 rounds</option>
              </select>
            </label>
          </div>
        </Panel>

        <Panel title="AI managers" subtitle="Fill empty seats with automated rivals" icon="🤖">
          <div className="bot-setup">
            <label className="field"><span>How many bots?</span>
              <input type="number" min={1} max={6 - members.length} value={count}
                onChange={e => setCount(Math.max(1, Math.min(6, Number(e.target.value))))} />
            </label>
            <label className="field"><span>Difficulty</span>
              <select value={difficulty} onChange={e => setDifficulty(e.target.value)}>
                <option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option>
              </select>
            </label>
          </div>
          <Button variant="subtle" block disabled={!isHost || members.length >= 6}
            onClick={() => send('bots', { count, difficulty })}>＋ Add AI managers</Button>
          <div className="callout">
            <strong>How the draft works</strong>
            <p>Each franchise picks 15 players in snake order. Bronze costs 30 FC, Silver 50 FC and Gold 80 FC during the inaugural draft.</p>
          </div>
          {isHost && (
            <div className="start-block">
              {!canStart && <small>Add at least one more manager or bot, and ensure everyone is ready.</small>}
              <Button variant="gold" block disabled={!canStart} onClick={() => send('start', {})}>
                🏏 Kick off season
              </Button>
            </div>
          )}
        </Panel>
      </div>
    </div>
  )
}
