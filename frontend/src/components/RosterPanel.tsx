import { activeBatsman, type Batsman, type GameState } from '../types'
import { useApp } from '../store'
import { BatsmanAvatar } from './BatsmanAvatar'
import { sound } from '../sound'

interface Props {
  state: GameState
  meId: string
  send: (action: string, payload?: Record<string, unknown>) => void
  onUpgrade: (batsman: Batsman) => void
}

export function RosterPanel({ state, meId, send, onUpgrade }: Props) {
  const { app } = useApp()
  const perTurn = app.config?.no_ball_runs_per_turn ?? 6
  const me = state.players.find(p => p.id === meId)
  if (!me) return null
  const active = activeBatsman(me)
  const canSwitch = state.current_player_id === meId && state.phase === 'await_roll'
    && !state.pending && !state.market && !state.auction && !me.debt && !me.eliminated

  const switchTo = (id: string) => {
    sound.play('click')
    send('switch_batsman', { batsman_id: id })
  }

  return (
    <section className="panel roster-panel">
      <div className="panel-heading roster-heading">
        <div><span className="eyebrow">YOUR XI</span><h3>Active batsman</h3></div>
        <span className="roster-count">{me.batsmen.length}/5</span>
      </div>

      {active ? (
        <div className="active-batsman-card" style={{ ['--jersey' as any]: active.jersey_color }}>
          <BatsmanAvatar person={active} size="medium" />
          <div className="active-batsman-info">
            <strong>{active.name}</strong>
            <span>{active.country} · Level {active.level}</span>
            <div className="stat-line">
              <span title="Wickets remaining">🏏 {active.wickets}/{active.max_wickets}</span>
              <span title="Runs from 6 tile">🚀 {active.six_runs} runs</span>
            </div>
          </div>
          <div className="wicket-pips">
            {Array.from({ length: active.max_wickets }, (_, i) => (
              <i key={i} className={i < active.wickets ? 'alive' : ''} />
            ))}
          </div>
        </div>
      ) : (
        <div className="no-batsman-warning">
          <strong>No batsman available</strong>
          <span>Land on a recruitment tile or wait for the market to recover.</span>
        </div>
      )}

      <div className="no-ball-strip">
        <span>NO-BALL CYCLE</span>
        <strong>{me.no_ball_turns} turns</strong>
        <em>+{me.no_ball_turns * perTurn} bonus runs</em>
        <b title="Absorbs the next wicket loss">🛡️ {me.no_ball_protection}</b>
      </div>

      <div className="panel-heading small-heading"><h4>Roster</h4></div>
      <div className="roster-list">
        {me.batsmen.map(b => (
          <div key={b.id} className={`roster-row ${b.id === active?.id ? 'active' : ''} ${!b.usable ? 'retired' : ''}`}>
            <BatsmanAvatar person={b} size="tiny" showNumber={false} />
            <div className="roster-row-info">
              <strong>{b.name}</strong>
              <span>L{b.level} · {b.wickets}/{b.max_wickets} wickets · {b.six_runs} six</span>
            </div>
            <div className="roster-row-actions">
              {b.id !== active?.id && (
                <button className="mini-btn" disabled={!canSwitch || !b.usable}
                  onClick={() => switchTo(b.id)} title="Switch before rolling">Use</button>
              )}
              <button className="mini-btn gold" disabled={b.retired || b.level >= 5}
                onClick={() => { sound.play('click'); onUpgrade(b) }} title="Upgrade batsman">⬆</button>
            </div>
          </div>
        ))}
        {me.batsmen.length === 0 && <p className="muted">Your roster is empty.</p>}
      </div>
      <p className="roster-hint">Switch only on your turn before rolling. Upgrades are available any time.</p>
    </section>
  )
}
