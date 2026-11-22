import React, { useState } from 'react'
import { useApp } from '../store'
import type { GameModal, PlayerData, TycoonLobby, TycoonState } from '../types'
import { money, titleCase } from '../utils'
import { ActionBar } from './ActionBar'
import { BoardGrid } from './BoardGrid'
import { ModalHost } from './ModalHost'
import { Badge, Button, Empty, Panel, Stat } from './UI'

const emptyRatings = { bat: 0, bowl: 0, field: 0 }

function squadRatings(squad: string[], players?: PlayerData[]) {
  const byId = new Map((players || []).map(p => [p.id, p]))
  const list = squad.map(id => byId.get(id)).filter((p): p is PlayerData => Boolean(p))
  const best = (items: PlayerData[], key: 'batting' | 'bowling' | 'fielding', count: number) => {
    const values = items.map(p => p[key]).sort((a, b) => b - a).slice(0, count)
    return values.length ? Math.round(values.reduce((a, b) => a + b, 0) * count / values.length) : 0
  }
  const batters = list.filter(p => p.role === 'batsman' || p.role === 'allrounder')
  const bowlers = list.filter(p => p.role === 'bowler' || p.role === 'allrounder')
  const keepers = list.filter(p => p.role === 'wicketkeeper')
  return {
    bat: best(batters, 'batting', 4),
    bowl: best(bowlers, 'bowling', 4),
    field: best(list, 'fielding', 4) + Math.floor(best(keepers, 'fielding', 1) / 5),
  }
}

export function GameScreen() {
  const { app, dispatch, setSession } = useApp()
  const state = app.state as unknown as TycoonState | null
  const lobby = state && !state.started ? state as unknown as TycoonLobby : null
  const [manual, setManual] = useState<GameModal>(null)

  const you = state?.you
  const me = you && state ? state.franchises?.[you] : undefined
  const ratings = me ? squadRatings(me.squad || [], state?.gamedata?.players) : emptyRatings
  const pitch = state?.pitch || 'flat'
  const effects = (state?.gamedata?.rules?.pitch_effects || app.gamedata?.rules?.pitch_effects || {}) as
    Record<string, { runs?: number; wickets?: number; note?: string }>
  const effect = effects[pitch] || { note: 'Standard conditions' }
  const standings = state?.standings || []
  const grounds = state && me
    ? (state.board || []).filter(t =>
      state.ownership?.[String(t.position)] === you
      || (me.stadiums || []).some(id => String(id) === String(t.id) || String(id) === String(t.position)))
    : []
  const log = [...(state?.log || [])].slice(-6).reverse()
  const isHost = Boolean(state?.host_id && state.host_id === app.session?.playerId)

  const exit = () => {
    setSession(null)
    dispatch({ type: 'STATE', state: null })
    dispatch({ type: 'JOIN_CODE', code: null })
    setManual(null)
  }

  return (
    <div className="app-shell">
      <header className="topbar slim-header">
        <div className="brand">
          <span className="brand-mark">🏏</span>
          <span><strong>CRICKOPOLY</strong><small>STADIUM TYCOON</small></span>
        </div>
        <div className="header-meta">
          <Badge tone="gold" icon="🏠">{app.session?.code || state?.code || '—'}</Badge>
          <Badge>R{state?.round || 1} · {titleCase(state?.phase || 'lobby')}</Badge>
          <Badge tone="blue" icon="🌱">{titleCase(pitch)}</Badge>
        </div>
        <div className="top-actions">
          <span className={`conn ${app.connected ? 'online' : 'offline'}`}
            title={app.connected ? 'Live connection' : 'Reconnecting…'} />
          {me && <Badge tone="green" icon="💰">{money(me.balance)}</Badge>}
          <Button variant="subtle" small onClick={() => setManual('guide')}>? Help</Button>
          {app.session && <Button variant="subtle" small onClick={exit}>Exit</Button>}
        </div>
      </header>

      <main className="main-content board-page">
        <div className="board-layout">
          <Panel className="board-panel" title="Stadium Tycoon board"
            subtitle="Roll, buy grounds, sign cricketers, win duels — all from this screen"
            icon="🗺️" action={<div className="board-legend">
              <span><i className="legend-market" />Market</span><span><i className="legend-stadium" />Ground</span>
              <span><i className="legend-event" />Event</span><span><i className="legend-corner" />Corner</span>
            </div>}>
            <BoardGrid state={state} gamedata={app.gamedata} />
          </Panel>

          <aside className="rail-stack">
            <Panel title="Your franchise" subtitle={me ? me.name : 'Waiting for a room'} icon="📊">
              <div className="rail-stats">
                <Stat label="Cash" value={money(me?.balance)} tone="gold" />
                <Stat label="BAT" value={ratings.bat} />
                <Stat label="BOWL" value={ratings.bowl} tone="blue" />
                <Stat label="FIELD" value={ratings.field} tone="green" />
              </div>
              <div className="pitch-badge mt-12">
                <span>🌱</span>
                <div><small>CURRENT PITCH EFFECT</small>
                  <strong>{titleCase(pitch)}</strong>
                  <small>{effect.note || 'Standard conditions'}</small>
                </div>
              </div>
              <div className="button-row mt-12">
                <Button variant="subtle" small onClick={() => setManual('assets')}>Squad & cards</Button>
                <Button variant="subtle" small onClick={() => setManual('history')}>History</Button>
                {isHost && <Button variant="subtle" small onClick={() => setManual('studio')}>Studio</Button>}
              </div>
            </Panel>

            <Panel title="Brand value" subtitle="Live standings" icon="🏆">
              {standings.length === 0 ? <Empty title="Table opens at kickoff" /> : (
                <table className="data-table">
                  <thead><tr><th>#</th><th>Franchise</th><th>Brand</th><th>Duels</th></tr></thead>
                  <tbody>
                    {[...standings].sort((a, b) => a.rank - b.rank).map(row => (
                      <tr key={row.id} className={row.id === you ? 'mine' : ''}>
                        <td>{row.rank}</td>
                        <td><span className="team-color" style={{ background: row.color }} />{row.name}</td>
                        <td><strong>{money(row.brand_value)}</strong></td>
                        <td>{row.duels_won}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Panel>

            <Panel title="Owned grounds" subtitle={`${grounds.length} stadiums`} icon="🏟️">
              {grounds.length === 0 ? <Empty title="No grounds yet" text="Buy one when you land on it." /> : (
                <div className="venue-list">
                  {grounds.map(t => (
                    <div key={t.position} className="venue-row"><div>
                      <strong>{t.name}</strong><small>Ground {t.position} · {money(t.price || 0)}</small>
                    </div></div>
                  ))}
                </div>
              )}
            </Panel>

            <Panel title="Recent log" subtitle="Latest board activity" icon="⚡">
              {log.length === 0 ? <Empty title="No activity yet" /> : (
                <div className="event-feed">
                  {log.map((entry, i) => (
                    <div key={i} className="feed-row"><span className="feed-dot" />
                      <div><p>{entry.text}</p><small>R{entry.round || '—'} · {entry.kind || 'info'}</small></div>
                    </div>
                  ))}
                </div>
              )}
              {lobby && <div className="callout"><strong>Room {lobby.code}</strong>
                <p>Share the code — invite links never contain tokens.</p></div>}
            </Panel>
          </aside>
        </div>
      </main>

      <ActionBar state={state} onOpen={setManual} />
      <ModalHost state={state} lobby={lobby} manual={manual} onClose={() => setManual(null)} />
    </div>
  )
}
