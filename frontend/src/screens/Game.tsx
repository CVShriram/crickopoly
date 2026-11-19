import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useApp } from '../store'
import { Board } from '../components/Board'
import { Dice } from '../components/Dice'
import { PlayerRail } from '../components/PlayerRail'
import { ActionPanel } from '../components/ActionPanel'
import { EventFeed } from '../components/EventFeed'
import { RosterPanel } from '../components/RosterPanel'
import { DebtModal, MarketModal, RecruitActivateModal, ScoreboardModal, UpgradeModal, VictoryOverlay } from '../components/Modals'
import { BatsmanAvatar } from '../components/BatsmanAvatar'
import { activeBatsman, type Batsman, type GameState, type Player, type Space } from '../types'
import { sound } from '../sound'

const IMPACT_EVENTS: Record<string, { text: string; cls: string; icon: string }> = {
  six: { text: 'SIX!', cls: 'impact-six', icon: '🚀' },
  no_ball: { text: 'NO BALL!', cls: 'impact-noball', icon: '🚫' },
  wicket: { text: 'WICKET!', cls: 'impact-wicket', icon: '🏏' },
  batsman_retired: { text: 'BATSMAN OUT!', cls: 'impact-wicket', icon: '❌' },
  purchase: { text: 'SIGNED!', cls: 'impact-buy', icon: '💳' },
  batsman_recruited: { text: 'NEW SIGNING!', cls: 'impact-buy', icon: '🏏' },
  batsman_upgraded: { text: 'UPGRADED!', cls: 'impact-buy', icon: '⬆️' },
  coins_gifted: { text: 'COINS SENT!', cls: 'impact-buy', icon: '💸' },
  milestone: { text: 'MILESTONE!', cls: 'impact-six', icon: '⭐' },
  victory: { text: 'MATCH WON!', cls: 'impact-buy', icon: '🏆' },
}

export function Game() {
  const { app, dispatch, send, disconnect } = useApp()
  const state = app.state
  const meId = app.session?.playerId || null
  const [rolling, setRolling] = useState(false)
  const [space, setSpace] = useState<Space | null>(null)
  const [inspect, setInspect] = useState<Player | null>(null)
  const [upgrade, setUpgrade] = useState<Batsman | null>(null)
  const [showScoreboard, setShowScoreboard] = useState(false)
  const [showVictory, setShowVictory] = useState(false)
  const [impact, setImpact] = useState<{ key: number; text: string; cls: string; icon: string } | null>(null)
  const eventCountRef = useRef(app.events.length)

  useEffect(() => {
    const phase = state?.phase
    if (phase === 'over') setShowVictory(true)
    else setShowVictory(false)
  }, [state?.phase])

  useEffect(() => {
    if (app.events.length <= eventCountRef.current) { eventCountRef.current = app.events.length; return }
    eventCountRef.current = app.events.length
    const last = app.events[app.events.length - 1]
    const fx = last && IMPACT_EVENTS[last.type]
    if (!fx) return
    setImpact({ key: Date.now(), ...fx })
    const timer = window.setTimeout(() => setImpact(null), 1400)
    return () => window.clearTimeout(timer)
  }, [app.events.length])

  if (!state || !meId) return <div className="screen-bg loading-screen">Connecting to the match…</div>

  const current = state.players.find(p => p.id === state.current_player_id)
  const me = state.players.find(p => p.id === meId)
  const lastEvent = state.log[state.log.length - 1]
  const active = activeBatsman(me)

  const roll = () => {
    if (rolling) return
    setRolling(true)
    sound.play('dice')
    send('roll')
    window.setTimeout(() => setRolling(false), 700)
  }

  const leave = () => {
    disconnect()
    dispatch({ type: 'SESSION', session: null })
    dispatch({ type: 'STATE', state: null })
    dispatch({ type: 'VIEW', view: 'landing' })
  }

  const newMatch = async () => {
    if (!app.session) return leave()
    try {
      const result = await api.quickMatch(app.session.name, 2, 'smart')
      sound.play('victory')
      dispatch({ type: 'SESSION', session: { ...app.session, code: result.code, playerId: result.player_id } })
      dispatch({ type: 'STATE', state: null })
      dispatch({ type: 'VIEW', view: 'game' })
    } catch { /* stay on results */ }
  }

  return (
    <div className="screen-bg game-screen">
      <header className="screen-topbar">
        <div className="brand-mark small"><span className="brand-ball">🏏</span> CRICKET <b>MONOPOLY</b></div>
        <div className="topbar-center">
          <span className="room-chip">ROOM <b>{state.code}</b></span>
          <span className="round-chip">ROUND <b>{state.round}</b>{state.victory_mode === 'turn_limit' ? ` / ${state.turn_limit}` : ''}</span>
          <span className="wallet-chip">💰 <b>{me?.money.toLocaleString() ?? 0}</b></span>
          <span className="runs-chip">🏏 <b>{me?.runs ?? 0}</b> runs</span>
          {current && <span className="turn-chip" style={{ borderColor: current.color }}>
            <i style={{ background: current.color }} /> {current.name}'s turn
          </span>}
        </div>
        <nav className="topbar-nav">
          <button className="scoreboard-link" onClick={() => setShowScoreboard(true)}>Scoreboard</button>
          <button onClick={() => dispatch({ type: 'VIEW', view: 'squad' })}>Squad</button>
          <button onClick={() => dispatch({ type: 'VIEW', view: 'profile' })}>Profile</button>
          <button onClick={() => dispatch({ type: 'VIEW', view: 'results' })}>Results</button>
          <button className="mute-link" onClick={() => { sound.setMuted(!sound.muted); sound.play('click') }}>
            {sound.muted ? '🔇' : '🔊'}
          </button>
          <button onClick={leave}>Leave</button>
        </nav>
      </header>

      <div className="game-layout">
        <aside className="side-col left-col">
          <PlayerRail state={state} meId={meId} onInspect={setInspect} />
          <RosterPanel state={state} meId={meId} send={send} onUpgrade={setUpgrade} />
        </aside>

        <main className="board-col">
          <Board board={app.board} state={state} currentPlayerId={state.current_player_id}
            onSelect={setSpace}>
            <div className="center-hud">
              <div className="center-logo">
                <span className="logo-ball">🏏</span>
                <div><span>CRICKET</span><strong>MONOPOLY</strong></div>
              </div>
              <div className="center-round">ROUND {state.round} <span>·</span> OVER {state.phase === 'over' ? 'COMPLETE' : 'IN PROGRESS'}</div>
              <div className="center-current">
                <small>ON STRIKE</small>
                <strong style={{ color: current?.color || '#fff' }}>{current?.name ?? '—'}</strong>
                {active && current?.id === meId && <span className="center-batsman">{active.name} · L{active.level}</span>}
              </div>
              <Dice dice={state.dice} rolling={rolling} />
              <div className="center-announce">
                {impact ? <span className={`impact-banner ${impact.cls}`} key={impact.key}>{impact.icon} {impact.text}</span>
                  : lastEvent ? lastEvent.type.replace(/_/g, ' ').toUpperCase() : 'ROLL THE DICE TO BEGIN'}
              </div>
              {state.phase === 'over' && (
                <button className="btn gold" onClick={() => setShowVictory(true)}>🏆 Final ranking</button>
              )}
            </div>
          </Board>
        </main>

        <aside className="side-col right-col">
          <ActionPanel state={state} board={app.board} meId={meId} send={send}
            rolling={rolling} onRoll={roll} />
          <EventFeed state={state} />
        </aside>
      </div>

      {space && <SpaceModal space={space} state={state} onClose={() => setSpace(null)} />}
      {showScoreboard && <ScoreboardModal state={state} meId={meId} onClose={() => setShowScoreboard(false)} />}
      {inspect && <InspectModal player={inspect} onClose={() => setInspect(null)} />}
      {upgrade && me && (
        <UpgradeModal batsman={upgrade} me={me} config={app.config} send={send}
          onClose={() => setUpgrade(null)} />
      )}
      {state.market?.player_id === meId && me && (
        <MarketModal market={state.market} me={me} config={app.config} send={send} />
      )}
      {state.pending?.type === 'recruit_activate' && state.pending.player_id === meId && me && (
        <RecruitActivateModal pending={state.pending} me={me} send={send} />
      )}
      {me?.debt && <DebtModal me={me} debt={me.debt} send={send} />}
      {state.phase === 'over' && showVictory && (
        <VictoryOverlay state={state} onClose={() => setShowVictory(false)}
          onResults={() => { setShowVictory(false); dispatch({ type: 'VIEW', view: 'results' }) }}
          onNewMatch={newMatch} />
      )}
    </div>
  )
}

function SpaceModal({ space, state, onClose }: { space: Space; state: GameState; onClose: () => void }) {
  const owner = state.players.find(p => p.assets.some(a => a.space_id === space.id))
  const asset = owner?.assets.find(a => a.space_id === space.id)
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>×</button>
        <span className="eyebrow">{space.type.replace(/_/g, ' ').toUpperCase()} SPACE #{space.id + 1}</span>
        <h2>{space.name}</h2>
        <p>{space.description}</p>
        <div className="modal-stats">
          {space.price > 0 && <div><span>Price</span><strong>{space.price}</strong></div>}
          {asset && <div><span>Owner</span><strong style={{ color: owner?.color }}>{owner?.name}</strong></div>}
          {asset && <div><span>Level</span><strong>{asset.level + 1}</strong></div>}
          {asset && asset.kind !== 'stadium' && <div><span>Fee</span><strong>{asset.effective_fee ?? 0}</strong></div>}
          {asset?.kind === 'keeper' && <div><span>Run penalty</span><strong>{asset.run_penalty ?? 0}</strong></div>}
        </div>
      </div>
    </div>
  )
}

function InspectModal({ player, onClose }: { player: Player; onClose: () => void }) {
  const active = activeBatsman(player)
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal wide" onClick={e => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>×</button>
        <div className="inspect-head">
          <div className="lobby-avatar large" style={{ background: player.color }}>{player.avatar}</div>
          <div><span className="eyebrow">MANAGER PROFILE</span><h2>{player.name}</h2></div>
        </div>
        <div className="modal-stats four">
          <div><span>Money</span><strong>{player.money}</strong></div>
          <div><span>Runs</span><strong>{player.runs}</strong></div>
          <div><span>Properties</span><strong>{player.property_count}</strong></div>
          <div><span>Wickets left</span><strong>{player.batsmen.filter(b => b.usable).reduce((s, b) => s + b.wickets, 0)}</strong></div>
        </div>
        <h3 className="section-title">Batsmen</h3>
        <div className="mini-asset-list">
          {player.batsmen.map(b => (
            <div key={b.id} className={`mini-asset ${!b.usable ? 'out' : ''}`}>
              <BatsmanAvatar person={b} size="tiny" showNumber={false} />
              <span>{b.name}</span>
              <strong>{b.wickets}/{b.max_wickets} wickets · L{b.level}{b.id === active?.id ? ' · ACTIVE' : ''}</strong>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
