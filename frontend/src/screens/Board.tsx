import React, { useMemo, useState } from 'react'
import { useApp } from '../store'
import type { Tile } from '../types'
import { Avatar, Badge, Button, Empty, Meter, Modal, Panel, Stat } from '../components/UI'
import { boardKindLabel, isMyTurn, money, ownerName, playerLabel } from '../utils'

function tileGridPosition(pos: number): { gridRow: number; gridColumn: number } {
  if (pos <= 13) return { gridRow: 14, gridColumn: pos + 1 }
  if (pos <= 25) return { gridRow: 14 - (pos - 13), gridColumn: 14 }
  if (pos <= 38) return { gridRow: 1, gridColumn: 14 - (pos - 26) }
  return { gridRow: 2 + (pos - 39), gridColumn: 1 }
}

export function Board() {
  const { app, send, dispatch } = useApp()
  const state = app.state!
  const myF = state.you ? state.franchises[state.you] : undefined
  const current = state.current_player_id ? state.franchises[state.current_player_id] : undefined
  const myTurn = isMyTurn(state)
  const blocked = Boolean(state.pending || state.auction)
  const currentTile = myF ? state.board?.[myF.pos] : undefined

  // Show the season-start tile once when a manager first reaches the board,
  // then honour the close button permanently for this room.
  const introKey = `fg-tile-intro-${state.code}`
  const [inspect, setInspect] = useState<Tile | null>(() => {
    try {
      if (currentTile && !sessionStorage.getItem(introKey)) return currentTile
    } catch { /* storage unavailable */ }
    return null
  })
  const closeInspect = () => {
    setInspect(null)
    try { sessionStorage.setItem(introKey, '1') } catch { /* storage unavailable */ }
  }

  const pending = state.pending
  const canRoll = myTurn && !blocked && !state.finished
  const pendingPurchase = pending?.type === 'purchase' && pending.pid === state.you
    ? state.board?.[pending.pos] : null

  const valuation = useMemo(() => {
    if (!myF) return 0
    const players = Object.keys(myF.squad).reduce((sum, id) => {
      const p = state.gamedata?.players?.find(x => x.id === id)
      return sum + (p?.value || 50)
    }, 0)
    const assets = (state.board || []).filter(t =>
      myF.markets.includes(t.position) || String(t.position) in myF.stadiums
    ).reduce((sum, t) => sum + (t.price || 0), 0)
    return myF.balance + players + assets
  }, [myF, state.board, state.gamedata])

  const owned = (pos: number) => state.ownership?.[String(pos)]

  const roll = () => send('roll', { auto_buy: false })

  return (
    <div className="page board-page">
      <div className="board-head">
        <div>
          <small>ROUND {state.round} · {state.phase.toUpperCase()}</small>
          <h1>{myF?.name || 'Franchise'} command centre</h1>
          <p>{myTurn ? 'You are on the clock. Roll the dice to advance.' : `${current?.name || 'Opponent'} is taking their turn.`}</p>
        </div>
        <div className="turn-actions">
          {myTurn && !blocked && <Button variant="gold" onClick={roll} disabled={!canRoll}>🎲 Roll the dice</Button>}
          {myTurn && pendingPurchase && (
            <div className="purchase-prompt">
              <span><strong>{pendingPurchase.name}</strong> is unowned — {money(pendingPurchase.price || 0)}</span>
              <div>
                <Button variant="success" small onClick={() => send('buy_market', { pos: pendingPurchase.position })}
                  disabled={pendingPurchase.kind === 'stadium' ? false : (myF?.balance || 0) < (pendingPurchase.price || 0)}>
                  Buy {pendingPurchase.kind === 'stadium' ? 'venue' : 'market'}
                </Button>
                <Button variant="subtle" small onClick={() => send('skip', {})}>Pass</Button>
              </div>
            </div>
          )}
          {pending?.type === 'matchday' && (
            <Button variant="gold" onClick={() => dispatch({ type: 'VIEW', view: 'match' })}>🏏 Open matchday</Button>
          )}
          {pending?.type === 'match_setup' && (
            <Button variant="gold" onClick={() => dispatch({ type: 'VIEW', view: 'match' })}>🛡️ Submit tactics</Button>
          )}
          {state.auction && <Button variant="danger" onClick={() => dispatch({ type: 'VIEW', view: 'auction' })}>🔨 Live auction</Button>}
        </div>
      </div>

      <div className="dashboard-strip">
        <Stat label="Balance" value={money(myF?.balance)} sub="Available FC" tone="gold" icon="💰" />
        <Stat label="Valuation" value={money(valuation)} sub="Cash + squad + assets" icon="📈" />
        <Stat label="Squad" value={`${Object.keys(myF?.squad || {}).length}/15`} sub={`XI ${myF?.xi?.length || 0}/11`} icon="👥" />
        <Stat label="League pts" value={state.standings?.find(r => r.id === state.you)?.points || 0}
          sub={`Rank #${state.standings?.find(r => r.id === state.you)?.rank || '—'}`} tone="green" icon="🏆" />
        <Stat label="Record" value={`${myF?.record?.wins || 0}–${myF?.record?.losses || 0}`}
          sub={`NRR ${state.standings?.find(r => r.id === state.you)?.nrr || 0}`} icon="🏏" />
        <Stat label="Fatigue" value={`${myF?.fatigue || 0}%`} sub="Squad average" tone={(myF?.fatigue || 0) > 55 ? 'danger' : 'default'} icon="🔋" />
      </div>

      <div className="board-layout">
        <Panel className="board-panel" title="52-tile franchise board" subtitle="Click any tile to inspect owners, fees and available actions"
          icon="🗺️" action={<div className="board-legend">
            <span><i className="legend-market" />Market</span><span><i className="legend-stadium" />Stadium</span>
            <span><i className="legend-event" />Event</span><span><i className="legend-corner" />Corner</span>
          </div>}>
          <div className="board-wrap">
            <div className="board-grid">
              {(state.board || []).map(t => {
                const ownerId = owned(t.position)
                const owner = ownerId ? state.franchises[ownerId] : undefined
                const isMe = ownerId === state.you
                const here = myF?.pos === t.position
                const active = current?.pos === t.position
                return (
                  <button key={t.position} type="button"
                    style={{ ...tileGridPosition(t.position), '--tile-color': owner?.color || 'transparent' } as React.CSSProperties}
                    className={`board-tile tile-${t.kind} ${here ? 'here' : ''} ${active ? 'active' : ''} ${isMe ? 'mine' : ''}`}
                    onClick={() => setInspect(t)} title={`${t.position}: ${t.name}`}>
                    <span className="tile-pos">{t.position}</span>
                    <span className="tile-icon">{t.icon}</span>
                    <span className="tile-name">{t.short || t.name}</span>
                    {owner && <span className="tile-owner" style={{ background: owner.color }} />}
                  </button>
                )
              })}
              <div className="board-center">
                <span className="center-crest">🏏</span>
                <small>CRICKOPOLY</small>
                <strong>FRANCHISE LEAGUE</strong>
                <div className="dice-display">
                  <span>{state.dice?.[0] || '–'}</span><span>{state.dice?.[1] || '–'}</span>
                </div>
                <p>{current ? <><span style={{ color: current.color }}>{current.avatar} {current.name}</span> to roll</> : 'Season starting'}</p>
                {currentTile && <button type="button" onClick={() => setInspect(currentTile)}>Inspect current tile →</button>}
              </div>
            </div>
          </div>
        </Panel>

        <aside className="board-side">
          <Panel title="Your position" subtitle={currentTile?.name || '—'} icon="📍">
            {myF && <>
              <div className="position-row"><Avatar franchise={myF} /><div><strong>Tile {myF.pos}</strong>
                <small>{boardKindLabel(currentTile?.kind || '')} · {ownerName(state, owned(myF.pos))}</small></div></div>
              <div className="resource-bars">
                <div><span>Reputation</span><Meter value={myF.reputation} max={40} tone="gold" label={`${myF.reputation}`} /></div>
                <div><span>Markets</span><Meter value={myF.markets.length} max={32} label={`${myF.markets.length}`} /></div>
                <div><span>Venues</span><Meter value={Object.keys(myF.stadiums).length} max={8} tone="blue" label={`${Object.keys(myF.stadiums).length}`} /></div>
                <div><span>Cards</span><Meter value={myF.cards.length} max={6} tone="gold" label={`${myF.cards.length}`} /></div>
              </div>
              {myF.sponsors.length > 0 && <div className="chip-row">{myF.sponsors.map(s => <Badge key={s} tone="green">{s.replace(/_/g, ' ')}</Badge>)}</div>}
            </>}
          </Panel>
          <Panel title="Live activity" subtitle="Latest league events" icon="⚡">
            {app.events.length === 0 && (state.log || []).length === 0
              ? <Empty title="No activity yet" text="Actions will appear here in real time." />
              : <div className="event-feed">
                {[...(state.log || []).slice(-14)].reverse().map((entry: any, i: number) => (
                  <div key={i} className="feed-row"><span className="feed-dot" />
                    <div><p>{entry.text}</p><small>R{entry.round} · {entry.kind}</small></div>
                  </div>
                ))}
              </div>}
          </Panel>
        </aside>
      </div>

      {inspect && (
        <Modal title={`Tile ${inspect.position} · ${inspect.name}`} subtitle={boardKindLabel(inspect.kind)} onClose={closeInspect}>
          <div className="tile-inspect">
            <div className="inspect-icon">{inspect.icon}</div>
            <div className="inspect-body">
              <p>{inspect.desc}</p>
              <div className="inspect-grid">
                <span>Owner <strong>{ownerName(state, owned(inspect.position))}</strong></span>
                {inspect.price && <span>Purchase <strong>{money(inspect.price)}</strong></span>}
                {inspect.landing_fee && <span>Landing fee <strong>{money(inspect.landing_fee)}</strong></span>}
                {inspect.match_revenue && <span>Round revenue <strong>{money(inspect.match_revenue)}</strong></span>}
                {inspect.pitch && <span>Pitch <strong>{state.gamedata?.pitches?.[inspect.pitch]?.name || inspect.pitch}</strong></span>}
                {inspect.country && <span>Market <strong>{state.gamedata?.countries?.[inspect.country]?.name || inspect.country}</strong></span>}
                {inspect.role && <span>Role <strong>{state.gamedata?.role_labels?.[inspect.role] || inspect.role}</strong></span>}
              </div>
              {inspect.kind === 'event' && <div className="callout"><strong>Special tile</strong><p>{inspect.desc}</p></div>}
              <div className="button-row">
                {pendingPurchase?.position === inspect.position && (
                  <>
                    <Button variant="success" onClick={() => { send('buy_market', { pos: inspect.position }); closeInspect() }}>Buy for {money(inspect.price)}</Button>
                    <Button variant="subtle" onClick={() => { send('skip', {}); closeInspect() }}>Pass</Button>
                  </>
                )}
                <Button variant="subtle" onClick={closeInspect}>Close</Button>
              </div>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
