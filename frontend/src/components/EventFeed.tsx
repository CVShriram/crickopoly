import type { GameEvent, GameState } from '../types'

function describe(event: GameEvent, state: GameState): string {
  const p = event.payload || {}
  const name = (id?: string) => state.players.find(x => x.id === id)?.name ?? 'Player'
  switch (event.type) {
    case 'game_started': return 'The match begins. Good luck, managers!'
    case 'turn_start': return `${name(p.player_id)} — Round ${p.round}: your turn.`
    case 'turn_wait': return `Waiting for ${name(p.player_id)} — Round ${p.round}.`
    case 'auto_roll': return `${name(p.player_id)} was timed out and rolled automatically.`
    case 'dice': return `${name(p.player_id)} rolled ${p.dice?.join(' + ')} = ${p.total}${p.is_double ? ' (doubles!)' : ''}.`
    case 'salary': return `${name(p.player_id)} collected ${p.amount} salary + sponsorship.`
    case 'fee': return `${name(p.player_id)} paid ${p.amount} coins at ${p.name}.`
    case 'runs': return `${name(p.player_id)} scored ${p.amount} runs${p.reason ? ` (${p.reason})` : ''}.`
    case 'six': return `${name(p.player_id)} hit SIX for ${p.runs} runs at level ${p.level}!`
    case 'no_ball': return `${name(p.player_id)}: ${p.text} — extra turn + wicket protection.`
    case 'milestone': return `${name(p.player_id)} reached ${p.threshold} runs! +${p.reward} coins.`
    case 'scoring': return `${name(p.player_id)} scored ${p.runs} runs at ${p.label}.`
    case 'purchase': return `${name(p.player_id)} bought ${p.asset?.name}.`
    case 'auction_won': return `${name(p.player_id)} won ${p.asset?.name} for ${p.price}.`
    case 'auction_bid': return `${name(p.player_id)} bid ${p.amount}.`
    case 'event_card': return `${p.card?.name}: ${p.card?.text}`
    case 'challenge': return `${p.challenge?.name}: ${p.success ? 'success!' : 'failed.'}`
    case 'wicket': return `WICKET! ${name(p.player_id)} lost a wicket — ${p.name} now ${p.wickets}/${p.max_wickets}.`
    case 'batsman_retired': return `${p.name} is OUT of wickets.`
    case 'batsman_switched': return `${name(p.player_id)} brought ${p.name} to the crease.`
    case 'batsman_auto_switched': return `${p.name} replaced the outgoing batsman.`
    case 'batsman_upgraded': return `${name(p.player_id)} upgraded ${p.batsman_id?.slice(-6)} to level ${p.level}.`
    case 'batsman_recruited': return `${name(p.player_id)} signed ${p.batsman?.name} for ${p.price} coins.`
    case 'bowler_attack': return `${p.name} attacked ${name(p.player_id)} — fee ${p.fee}.`
    case 'keeper_penalty': return `${name(p.player_id)} lost ${p.runs_lost} runs at the wicketkeeper.`
    case 'wicket_protected': return `${name(p.player_id)}: no-ball protection absorbed the wicket.`
    case 'wicket_blocked': return `${name(p.player_id)}: ${p.text ?? 'wicket blocked'}`
    case 'debt_incurred': return `${name(p.player_id)} owes ${p.amount} coins (${p.reason}).`
    case 'debt_paid': return `${name(p.player_id)} settled ${p.amount} coins of debt.`
    case 'bankrupt': return `${name(p.player_id)} was declared bankrupt.`
    case 'downgrade': return `${name(p.player_id)} downgraded a property for ${p.refund} coins.`
    case 'eliminated': return `${name(p.player_id)} eliminated (${p.reason}).`
    case 'victory': return `${name(p.winner_id)} wins the tournament! (${p.reason})`
    case 'trade_completed': return 'A trade was completed between managers.'
    case 'upgrade': return `${name(p.player_id)} upgraded an asset to level ${p.level}.`
    case 'sold': return `${name(p.player_id)} sold an asset for ${p.refund}.`
    case 'free_hit': return `${name(p.player_id)} gained a Free Hit.`
    case 'rest': return `${name(p.player_id)} rested at the Pavilion.`
    case 'achievement': return `${name(p.player_id)} unlocked: ${p.text}`
    case 'injury': return `${name(p.player_id)}'s ${p.name ?? 'batsman'} is injured.`
    case 'market_offer': return `${name(p.player_id)} opened the recruitment market.`
    case 'market_closed': return `The recruitment market closed for ${name(p.player_id)}.`
    case 'recruit_required': return `${name(p.player_id)} must recruit a batsman.`
    case 'victory_settings': return `Victory set to ${p.mode} (${p.turn_limit || '—'} rounds).`
    default: return event.type.replace(/_/g, ' ')
  }
}

export function EventFeed({ state }: { state: GameState }) {
  const items = [...state.log].reverse().slice(0, 40)
  return (
    <section className="event-feed">
      <div className="panel-heading">
        <span className="eyebrow">LIVE FEED</span>
        <h3>Match commentary</h3>
      </div>
      <div className="feed-list">
        {items.length === 0 && <p className="muted">No events yet. Roll the dice to begin.</p>}
        {items.map((entry, i) => (
          <div key={i} className={`feed-item feed-${entry.type}`}>
            <span className="feed-round">R{entry.round}</span>
            <span>{describe(entry, state)}</span>
          </div>
        ))}
      </div>
    </section>
  )
}
