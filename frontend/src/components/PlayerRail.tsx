import { activeBatsman, type GameState, type Player } from '../types'

interface Props {
  state: GameState
  meId: string | null
  onInspect: (player: Player) => void
}

export function PlayerRail({ state, meId, onInspect }: Props) {
  const sorted = [...state.players].sort((a, b) => {
    if (a.eliminated !== b.eliminated) return a.eliminated ? 1 : -1
    return b.runs - a.runs
  })
  return (
    <div className="player-rail">
      <div className="panel-heading">
        <span className="eyebrow">TOURNAMENT</span>
        <h3>Standings</h3>
      </div>
      <div className="player-list">
        {sorted.map((player, index) => {
          const usable = player.batsmen.filter(b => b.usable)
          const wickets = usable.reduce((sum, b) => sum + b.wickets, 0)
          const maxWickets = player.batsmen.reduce((sum, b) => sum + b.max_wickets, 0)
          const batsman = activeBatsman(player)
          const isCurrent = state.current_player_id === player.id
          return (
            <button
              key={player.id}
              className={`player-card ${isCurrent ? 'current' : ''} ${player.eliminated ? 'eliminated' : ''}`}
              style={{ ['--accent' as any]: player.color }}
              onClick={() => onInspect(player)}
            >
              <div className="player-rank">{index + 1}</div>
              <div className="player-avatar" style={{ borderColor: player.color }}>{player.avatar}</div>
              <div className="player-detail">
                <div className="player-name-row">
                  <strong>{player.name}</strong>
                  {player.id === meId && <span className="you-tag">YOU</span>}
                  {player.is_bot && <span className="bot-tag">BOT</span>}
                  {player.is_host && <span className="host-tag">HOST</span>}
                </div>
                <div className="player-metrics">
                  <span className="metric money">{player.money.toLocaleString()} <small>coins</small></span>
                  <span className="metric runs">{player.runs} <small>runs</small></span>
                  <span className={`metric wickets ${wickets === 0 ? 'danger' : ''}`}>
                    {wickets}/{maxWickets} <small>wkts</small>
                  </span>
                </div>
                <div className="player-sub">
                  <span>{batsman ? `🏏 ${batsman.name}` : 'No active batsman'}</span>
                  <span>{player.no_ball_protection > 0 ? `🚫 ${player.no_ball_protection}` : `${player.property_count} props`}</span>
                  <span className={player.connected ? 'online' : 'offline'}>
                    {player.connected ? '●' : '○'}
                  </span>
                </div>
              </div>
              {isCurrent && <span className="turn-flag">TURN</span>}
            </button>
          )
        })}
      </div>
    </div>
  )
}
