import { useState } from 'react'
import type { Batsman, Debt, GameConfig, GameState, Market, Pending, Player } from '../types'
import { useApp } from '../store'
import { activeBatsman } from '../types'
import { BatsmanAvatar } from './BatsmanAvatar'
import { sound } from '../sound'

interface Send {
  send: (action: string, payload?: Record<string, unknown>) => void
}

interface UpgradeProps extends Send {
  batsman: Batsman
  me: Player
  config: GameConfig | null
  onClose: () => void
}

export function UpgradeModal({ batsman, me, config, send, onClose }: UpgradeProps) {
  const maxLevel = config?.max_batsman_level ?? 5
  const perLevel = config?.six_runs_per_level ?? 6
  const cost = batsman.upgrade_cost
  const nextSix = (batsman.level + 1) * perLevel
  const canAfford = cost !== null && me.money >= cost
  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div className="modal-card" onMouseDown={e => e.stopPropagation()}>
        <button className="modal-x" onClick={onClose}>×</button>
        <span className="eyebrow">BATSMAN UPGRADE</span>
        <h2>Reach the next level</h2>
        <div className="upgrade-compare">
          <div className="upgrade-person">
            <BatsmanAvatar person={batsman} size="large" />
            <strong>{batsman.name}</strong>
          </div>
          <div className="upgrade-stats">
            <div><span>Level</span><b>{batsman.level} <i>→</i> {Math.min(maxLevel, batsman.level + 1)}</b></div>
            <div><span>Six reward</span><b>{batsman.six_runs} <i>→</i> {nextSix} runs</b></div>
            <div><span>Upgrade cost</span><b className="gold-text">{cost ?? 'MAX'}</b></div>
            <div><span>Your coins</span><b>{me.money}</b></div>
          </div>
        </div>
        <p className="muted">Wickets are never changed by an upgrade. Only the level and six-run reward improve.</p>
        <div className="modal-actions">
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn gold" disabled={cost === null || !canAfford} onClick={() => {
            sound.play('buy')
            send('upgrade_batsman', { batsman_id: batsman.id })
            onClose()
          }}>{cost === null ? 'Maximum level' : canAfford ? `Upgrade for ${cost}` : `Need ${cost - me.money} more`}</button>
        </div>
      </div>
    </div>
  )
}

interface MarketProps extends Send {
  market: Market
  me: Player
  config: GameConfig | null
}

export function MarketModal({ market, me, config, send }: MarketProps) {
  const full = me.batsmen.length >= (config?.max_batsmen ?? 5)
  const broke = me.money < market.price
  return (
    <div className="modal-backdrop strong">
      <div className="modal-card wide">
        <span className="eyebrow">BATSMAN RECRUITMENT</span>
        <h2>Transfer market</h2>
        <p className="muted">Sign a globally unique cricketer for {market.price} coins. Every option has identical stats: 3 wickets, level 1, unlimited upgrade potential.</p>
        <div className="market-options">
          {market.options.map(option => {
            const unavailable = full || broke || !option.available
            return (
              <div key={option.identity_id} className="market-option">
                <BatsmanAvatar person={{ ...option, skin: '#f1c27d', hair: 'short', face: 'smile' }} size="small" />
                <strong>{option.name}</strong>
                <span>{option.country} · #{option.jersey_number}</span>
                <div className="option-stats"><span>🏏 {option.wickets}</span><span>L{option.level}</span><span>💰 {option.price}</span></div>
                <button className="btn primary small" disabled={unavailable}
                  onClick={() => { sound.play('buy'); send('recruit', { identity_id: option.identity_id }) }}>
                  {full ? 'Roster full' : broke ? 'Not enough coins' : 'Sign player'}
                </button>
              </div>
            )
          })}
        </div>
        <div className="modal-actions">
          <button className="btn ghost" onClick={() => { sound.play('click'); send('decline_recruit') }}>Decline offer</button>
        </div>
      </div>
    </div>
  )
}

interface ActivateProps extends Send {
  pending: Pending
  me: Player
}

export function RecruitActivateModal({ pending, me, send }: ActivateProps) {
  const batsman = me.batsmen.find(b => b.id === pending.batsman_id)
  const active = activeBatsman(me)
  return (
    <div className="modal-backdrop strong">
      <div className="modal-card">
        <span className="eyebrow">SQUAD DECISION</span>
        <h2>New signing</h2>
        {batsman && (
          <div className="activate-person">
            <BatsmanAvatar person={batsman} size="large" />
            <div><strong>{batsman.name}</strong><span>{batsman.country} · Level {batsman.level} · {batsman.wickets} wickets</span></div>
          </div>
        )}
        {active && <p className="muted">Current active batsman: <b>{active.name}</b> ({active.wickets} wickets left).</p>}
        <div className="modal-actions stacked">
          <button className="btn gold" onClick={() => { sound.play('buy'); send('activate_recruit', { activate: true }) }}>
            Make {batsman?.name ?? 'new signing'} active
          </button>
          <button className="btn ghost" onClick={() => { sound.play('click'); send('activate_recruit', { activate: false }) }}>
            Keep in reserve
          </button>
        </div>
      </div>
    </div>
  )
}

interface DebtProps extends Send {
  me: Player
  debt: Debt
}

export function DebtModal({ me, debt, send }: DebtProps) {
  const receiverName = 'the creditor'
  const canPay = me.money >= debt.amount
  const saleable = me.assets.filter(a => a.space_id !== null)
  const downgradeRefund = (level: number, cost: number) =>
    Math.floor(cost * (1 + 0.5 * (level - 1)) * 0.6)
  return (
    <div className="modal-backdrop strong">
      <div className="modal-card wide debt-modal">
        <span className="eyebrow">DEBT RECOVERY</span>
        <h2>Settle before continuing</h2>
        <div className="debt-summary">
          <div><span>Original bill</span><b>{debt.original}</b></div>
          <div><span>Already paid</span><b>{debt.paid}</b></div>
          <div className="danger-text"><span>Still owed</span><b>{debt.amount}</b></div>
          <div><span>Your coins</span><b>{me.money}</b></div>
        </div>
        <p className="muted">Reason: {debt.reason}. Sell or downgrade a property to raise coins. Bankruptcy transfers your properties to {receiverName} and eliminates you.</p>
        {saleable.length > 0 && (
          <div className="recovery-list">
            {saleable.map(asset => {
              const refund = asset.sale_value ?? 0
              const downgrade = asset.level > 0 ? downgradeRefund(asset.level, asset.upgrade_cost ?? 0) : 0
              return (
                <div key={asset.id} className="recovery-row">
                  <div><strong>{asset.name}</strong><span>L{asset.level} · fee {asset.effective_fee ?? 0}</span></div>
                  <button className="mini-btn" disabled={asset.level <= 0} onClick={() => send('downgrade', { asset_id: asset.id })}>
                    Downgrade +{downgrade}
                  </button>
                  <button className="mini-btn gold" onClick={() => send('sell', { asset_id: asset.id })}>Sell +{refund}</button>
                </div>
              )
            })}
          </div>
        )}
        <div className="modal-actions">
          <button className="btn ghost danger-btn" onClick={() => { sound.play('out'); send('bankrupt') }}>Declare bankruptcy</button>
          <button className="btn gold" disabled={!canPay} onClick={() => { sound.play('money'); send('pay_debt') }}>
            {canPay ? `Pay ${debt.amount} coins` : `Need ${debt.amount - me.money} more`}
          </button>
        </div>
      </div>
    </div>
  )
}

interface GiftProps extends Send {
  state: GameState
  me: Player
  config: GameConfig | null
  onClose: () => void
}

export function GiftModal({ state, me, config, send, onClose }: GiftProps) {
  const min = config?.gift_min_coins ?? 50
  const max = config?.gift_max_coins ?? 500
  const reserve = config?.gift_reserve_coins ?? 100
  const recipients = state.players.filter(p =>
    p.id !== me.id && !p.eliminated && !p.debt)
  const [to, setTo] = useState(recipients[0]?.id ?? '')
  const [amount, setAmount] = useState(String(min))
  const affordableMax = Math.max(0, Math.min(max, me.money - reserve))
  const value = Number(amount)
  const valid = Boolean(to) && Number.isInteger(value) && value >= min
    && value <= max && value <= affordableMax

  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div className="modal-card gift-modal" onMouseDown={e => e.stopPropagation()}>
        <button className="modal-x" onClick={onClose}>×</button>
        <span className="eyebrow">MANAGER GIFT</span>
        <h2>Send coins</h2>
        <p className="muted">A bounded, server-validated transfer. One gift per round; keep {reserve} coins in reserve.</p>
        <div className="gift-wallet">
          <div><span>Your coins</span><b>💰 {me.money.toLocaleString()}</b></div>
          <div><span>Available to send</span><b>💸 {affordableMax.toLocaleString()}</b></div>
        </div>
        <label className="field">
          <span>Recipient</span>
          <select value={to} onChange={e => setTo(e.target.value)}>
            {recipients.length === 0 && <option value="">No eligible managers</option>}
            {recipients.map(p => (
              <option key={p.id} value={p.id}>{p.avatar} {p.name} · 💰 {p.money}</option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Amount ({min}–{Math.min(max, affordableMax)})</span>
          <input type="number" min={min} max={affordableMax} step="10" value={amount}
            onChange={e => setAmount(e.target.value)} />
        </label>
        <div className="quick-amounts">
          {[min, 100, 250, 500].filter(v => v >= min && v <= affordableMax
            && (v === min || v % min === 0)).map(v => (
            <button key={v} className={`chip ${value === v ? 'selected' : ''}`}
              onClick={() => setAmount(String(v))}>{v}</button>
          ))}
        </div>
        <div className="modal-actions">
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn gold" disabled={!valid} onClick={() => {
            sound.play('buy')
            send('gift_coins', { to_player_id: to, amount: value })
            onClose()
          }}>Send {valid ? value : '—'} coins</button>
        </div>
      </div>
    </div>
  )
}

interface ScoreboardProps {
  state: GameState
  meId: string
  onClose: () => void
}

export function ScoreboardModal({ state, meId, onClose }: ScoreboardProps) {
  const { app } = useApp()
  const perTurn = app.config?.no_ball_runs_per_turn ?? 6
  const rows = [...state.players].sort((a, b) => {
    if (a.eliminated !== b.eliminated) return a.eliminated ? 1 : -1
    if (b.runs !== a.runs) return b.runs - a.runs
    return b.money - a.money
  })
  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div className="modal-card wide scoreboard-modal" onMouseDown={e => e.stopPropagation()}>
        <button className="modal-x" onClick={onClose}>×</button>
        <span className="eyebrow">LIVE SCOREBOARD</span>
        <h2>Tournament standings</h2>
        <p className="muted">Round {state.round} · ranked by runs, then coins. Every figure comes from the authoritative server state.</p>
        <div className="live-table">
          <div className="live-head">
            <span>#</span><span>Manager</span><span>Coins</span><span>Runs</span>
            <span>Wickets</span><span>Batmen</span><span>Props</span><span>No-ball</span>
          </div>
          {rows.map((p, i) => {
            const usable = p.batsmen.filter(b => b.usable)
            const wickets = usable.reduce((s, b) => s + b.wickets, 0)
            const active = activeBatsman(p)
            return (
              <div key={p.id}
                className={`live-row ${p.id === meId ? 'me' : ''} ${p.id === state.current_player_id ? 'current' : ''} ${p.eliminated ? 'out' : ''}`}>
                <span className="live-rank">{i + 1}</span>
                <span className="live-name"><i style={{ background: p.color }} />{p.avatar} {p.name}
                  {p.id === meId && <em>YOU</em>}
                  <small>{active ? `🏏 ${active.name} · L${active.level}` : 'No active batsman'}</small>
                </span>
                <span className="gold-text">💰 {p.money.toLocaleString()}</span>
                <span className="green-text">{p.runs}</span>
                <span className={wickets === 0 ? 'danger-text' : ''}>{wickets}</span>
                <span>{p.active_batsmen}</span>
                <span>{p.property_count}</span>
                <span>+{p.no_ball_turns * perTurn}</span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

interface VictoryProps {
  state: GameState
  onClose: () => void
  onResults: () => void
  onNewMatch: () => void
}

export function VictoryOverlay({ state, onClose, onResults, onNewMatch }: VictoryProps) {
  const winner = state.players.find(p => p.id === state.winner_id)
  const victoryEvent = [...state.log].reverse().find(e => e.type === 'victory')
  const reason = victoryEvent?.payload?.reason || 'Tournament complete'
  const ranking = state.ranking.length ? state.ranking : state.players.map(p => ({
    player_id: p.id, name: p.name, avatar: p.avatar, runs: p.runs, money: p.money,
    batsmen: p.active_batsmen, wickets: p.batsmen.filter(b => b.usable).reduce((s, b) => s + b.wickets, 0),
    properties: p.property_count, upgrades: p.assets.reduce((s, a) => s + a.level, 0), eliminated: p.eliminated,
  }))
  return (
    <div className="modal-backdrop strong victory-backdrop">
      <div className="modal-card victory-card">
        <button className="modal-x" onClick={onClose}>×</button>
        <span className="eyebrow">TOURNAMENT COMPLETE</span>
        <div className="winner-hero" style={{ ['--accent' as any]: winner?.color || '#f4bd4a' }}>
          <div className="winner-avatar">{winner?.avatar || '🏆'}</div>
          <h1>{winner?.name ?? 'Winner'} wins!</h1>
          <p>{reason}</p>
        </div>
        <div className="ranking-table">
          <div className="ranking-head"><span>#</span><span>Manager</span><span>Runs</span><span>Batmen</span><span>Wickets</span><span>Coins</span></div>
          {ranking.map((row, i) => (
            <div key={row.player_id} className={`ranking-row ${row.player_id === state.winner_id ? 'winner' : ''}`}>
              <span>{i + 1}</span><span>{row.avatar} {row.name}</span><span>{row.runs}</span>
              <span>{row.batsmen}</span><span>{row.wickets}</span><span>{row.money}</span>
            </div>
          ))}
        </div>
        <div className="modal-actions">
          <button className="btn ghost" onClick={onResults}>Full results</button>
          <button className="btn gold" onClick={onNewMatch}>New match</button>
        </div>
      </div>
    </div>
  )
}
