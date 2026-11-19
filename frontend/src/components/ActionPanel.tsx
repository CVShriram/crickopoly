import { useEffect, useState } from 'react'
import { activeBatsman, type GameState, type Space } from '../types'
import { useApp } from '../store'
import { sound } from '../sound'
import { GiftModal } from './Modals'

interface Props {
  state: GameState
  board: Space[]
  meId: string
  send: (action: string, payload?: Record<string, unknown>) => void
  rolling: boolean
  onRoll: () => void
}

export function ActionPanel({ state, board, meId, send, rolling, onRoll }: Props) {
  const { app } = useApp()
  const [, setTick] = useState(0)
  const [bid, setBid] = useState('')
  const [giftOpen, setGiftOpen] = useState(false)
  useEffect(() => {
    const id = window.setInterval(() => setTick(t => t + 1), 500)
    return () => window.clearInterval(id)
  }, [])

  const me = state.players.find(p => p.id === meId)
  const active = activeBatsman(me)
  const perTurn = app.config?.no_ball_runs_per_turn ?? 6
  const myTurn = state.current_player_id === meId && state.phase === 'await_roll'
  const purchase = state.pending?.type === 'purchase' && state.pending.player_id === meId ? state.pending : null
  const pendingSpace = purchase ? board.find(s => s.id === purchase.space_id) : null
  const auction = state.auction
  const secondsLeft = auction ? Math.max(0, Math.ceil((auction.ends_at * 1000 - Date.now()) / 1000)) : 0
  const incomingTrades = state.trades.filter(t => t.to === meId && t.status === 'pending')
  const minimumBid = auction ? Math.max(10, auction.highest_bid + 10) : 10

  const placeBid = (amount: number) => {
    if (!auction || amount < minimumBid) return
    sound.play('click')
    send('bid', { amount })
    setBid('')
  }

  return (
    <section className="action-panel">
      <div className="panel-heading">
        <span className="eyebrow">MANAGER ACTIONS</span>
        <h3>Your move</h3>
      </div>

      {state.phase === 'over' ? (
        <div className="action-block center">
          <div className="big-icon">🏆</div>
          <p>Match complete — see the final ranking.</p>
        </div>
      ) : purchase && pendingSpace ? (
        <div className="action-block offer">
          <div className="offer-head">
            <span className="badge-gold">PROPERTY OFFER</span>
            <h4>{pendingSpace.name}</h4>
            <p>{pendingSpace.description}</p>
          </div>
          <div className="offer-price"><span>Purchase price</span><strong>{pendingSpace.price}</strong></div>
          <div className="offer-actions">
            <button className="btn primary" disabled={(me?.money || 0) < pendingSpace.price}
              onClick={() => { sound.play('buy'); send('buy') }}>Buy property</button>
            <button className="btn ghost" onClick={() => { sound.play('click'); send('skip') }}>Skip</button>
            <button className="btn gold" onClick={() => { sound.play('click'); send('auction') }}>Auction</button>
          </div>
          {(me?.money || 0) < pendingSpace.price && <p className="hint danger">Not enough coins to buy.</p>}
        </div>
      ) : state.market?.player_id === meId ? (
        <div className="action-block center">
          <div className="big-icon">🛒</div>
          <p>The recruitment market is open — choose a signing.</p>
        </div>
      ) : me?.debt ? (
        <div className="action-block center">
          <div className="big-icon">⚠️</div>
          <p>Settle your debt to continue your turn.</p>
        </div>
      ) : auction ? (
        <div className="action-block auction">
          <div className="auction-head">
            <span className="badge-gold">LIVE AUCTION</span>
            <span className="countdown">{secondsLeft}s</span>
          </div>
          <h4>{auction.space.name}</h4>
          <p className="muted">Highest bid: <strong>{auction.highest_bid}</strong> coins</p>
          {auction.highest_bidder && <p className="muted">Leader: {state.players.find(p => p.id === auction.highest_bidder)?.name}</p>}
          <div className="bid-row">
            <input type="number" min={minimumBid} max={me?.money || 0}
              placeholder={`${minimumBid}`} value={bid}
              onChange={e => setBid(e.target.value)} />
            <button className="btn primary" disabled={!bid || Number(bid) < minimumBid || Number(bid) > (me?.money || 0)}
              onClick={() => placeBid(Number(bid))}>Bid</button>
          </div>
          <div className="quick-bids">
            {[minimumBid, minimumBid + 50, minimumBid + 100].filter((v, i, arr) => arr.indexOf(v) === i).map(v => (
              <button key={v} className="chip" disabled={v > (me?.money || 0)} onClick={() => placeBid(v)}>+{v}</button>
            ))}
          </div>
        </div>
      ) : incomingTrades.length > 0 ? (
        <div className="action-block">
          <span className="badge-gold">TRADE OFFER</span>
          {incomingTrades.map(trade => (
            <TradeOffer key={trade.id} trade={trade} state={state} send={send} />
          ))}
        </div>
      ) : myTurn ? (
        <div className="action-block center">
          {active ? (
            <div className="roll-batsman">
              <span className="eyebrow">BATTING</span>
              <strong>{active.name}</strong>
              <span>Level {active.level} · {active.wickets}/{active.max_wickets} wickets · 🚀 {active.six_runs}</span>
            </div>
          ) : (
            <p className="hint danger">You need an active batsman before rolling.</p>
          )}
          <p className="muted">Round {state.round} · Your turn{state.extra_turn ? ' · Extra turn' : ''}</p>
          <button className="btn roll-btn primary" disabled={rolling || !active} onClick={onRoll}>
            {rolling ? 'Rolling…' : '🎲  Roll Dice'}
          </button>
          {me && me.gift_round !== state.round && (
            <button className="btn gift-btn gold" onClick={() => { sound.play('click'); setGiftOpen(true) }}>
              💸 Gift coins
            </button>
          )}
          <p className="hint">No-ball cycle: {me?.no_ball_turns ?? 0} turns · +{(me?.no_ball_turns ?? 0) * perTurn} bonus runs</p>
        </div>
      ) : (
        <div className="action-block center">
          <div className="waiting-pulse" />
          <p className="muted">
            {state.phase === 'moving' || state.phase === 'resolving'
              ? 'Resolving the board…'
              : `Waiting for ${state.players.find(p => p.id === state.current_player_id)?.name ?? 'player'}…`}
          </p>
        </div>
      )}

      {me && !me.eliminated && (
        <div className="effects-row">
          {active && active.level > 1 && <span className="effect green">🏏 Level {active.level} · {active.six_runs} six</span>}
          {me.no_ball_protection > 0 && <span className="effect gold">🚫 Wicket protection ×{me.no_ball_protection}</span>}
          {me.effects.free_hit > 0 && <span className="effect green">🛡️ Free Hit ×{me.effects.free_hit}</span>}
          {me.effects.powerplay_rounds > 0 && <span className="effect gold">⚡ Powerplay {me.effects.powerplay_rounds}r</span>}
          {me.effects.poor_form_rounds > 0 && <span className="effect danger">📉 Poor form {me.effects.poor_form_rounds}r</span>}
        </div>
      )}
      {giftOpen && me && (
        <GiftModal state={state} me={me} config={app.config} send={send}
          onClose={() => setGiftOpen(false)} />
      )}
    </section>
  )
}

function TradeOffer({ trade, state, send }: {
  trade: GameState['trades'][number]; state: GameState
  send: (action: string, payload?: Record<string, unknown>) => void
}) {
  const from = state.players.find(p => p.id === trade.from)
  const name = (ids: string[]) => ids.map(id =>
    state.players.flatMap(p => p.assets).find(a => a.id === id)?.name ?? id).join(', ')
  return (
    <div className="trade-offer">
      <p><strong>{from?.name}</strong> offers:</p>
      <p className="muted">{name(trade.give_assets) || '—'} {trade.give_money ? `+ ${trade.give_money} coins` : ''}</p>
      <p>Wants: <span className="muted">{name(trade.want_assets) || '—'} {trade.want_money ? `+ ${trade.want_money} coins` : ''}</span></p>
      <div className="offer-actions">
        <button className="btn primary" onClick={() => { sound.play('buy'); send('trade_response', { trade_id: trade.id, accept: true }) }}>Accept</button>
        <button className="btn ghost" onClick={() => send('trade_response', { trade_id: trade.id, accept: false })}>Decline</button>
      </div>
    </div>
  )
}
