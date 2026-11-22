import React from 'react'
import { useApp } from '../store'
import type { GameModal, TycoonState } from '../types'
import { money } from '../utils'
import { Button } from './UI'

type Mode = 'roll' | 'buy' | 'sign' | 'tactic' | 'auction' | 'pass' | 'continue' | 'waiting'

export function ActionBar({ state, onOpen }: {
  state: TycoonState | null
  onOpen: (modal: GameModal) => void
}) {
  const { send } = useApp()
  const you = state?.you
  const pending = state?.pending
  const auction = state?.auction
  const current = state?.current_player_id && state ? state.franchises?.[state.current_player_id] : undefined
  const me = you && state ? state.franchises?.[you] : undefined

  const isDuelSide = pending?.type === 'duel' && Boolean(
    you && (pending.pid === you || pending.defender === you),
  )
  const isResultViewer = pending?.type === 'result' && Boolean(
    you && (pending.pid === you || pending.viewers?.includes(you)),
  )

  let mode: Mode = 'waiting'
  if (state?.started) {
    if (state.finished) mode = 'continue'
    else if (auction) mode = auction.has_passed ? 'pass' : 'auction'
    else if (pending?.type === 'duel') mode = isDuelSide ? 'tactic' : 'waiting'
    else if (pending?.type === 'sign_player') mode = pending.pid === you ? 'sign' : 'waiting'
    else if (pending?.type === 'buy_stadium') mode = pending.pid === you ? 'buy' : 'waiting'
    else if (pending?.type === 'result') mode = isResultViewer ? 'continue' : 'waiting'
    else if (state.current_player_id === you) mode = 'roll'
  }

  const title = {
    roll: 'Your turn — roll the dice',
    buy: `Unowned ground — ${pending?.title || 'Stadium'}`,
    sign: `Player market — ${pending?.title || 'Signing'}`,
    tactic: `Match duel — ${pending?.label || 'Pick a card'}`,
    auction: 'Sealed auction is live',
    pass: 'You passed this lot',
    continue: state?.finished ? 'Season complete' : 'Resolve and continue',
    waiting: current ? `Waiting for ${current.name}` : 'Waiting for the room',
  }[mode]

  const sub = {
    roll: 'Move 1–6 tiles, then handle the ground you land on.',
    buy: `${money(pending?.price)} · buy the ground or pass it up.`,
    sign: `Pick one of three real cricketers for ${money(pending?.price)}.`,
    tactic: 'Lock one card. Your opponent’s choice stays hidden until the result.',
    auction: 'Bid the base price, +20 or +50 — or pass.',
    pass: 'The remaining managers must settle before the star is revealed.',
    continue: state?.finished ? 'See the final Brand Value table.' : 'Read the scorecard, then hand over the turn.',
    waiting: 'The action bar unlocks automatically when it is your turn.',
  }[mode]

  const continueAction = () => {
    if (pending?.pid === you) send('next', {})
    else send('skip', {})
  }

  return (
    <div className="sticky-action" role="region" aria-label="Next action">
      <div className="sticky-action-copy">
        <strong>{title}</strong>
        <small>{sub}</small>
      </div>
      <div className="sticky-action-buttons">
        {mode === 'roll' && (
          <Button variant="gold" className="action-primary" onClick={() => send('roll', {})}>🎲 ROLL DICE</Button>
        )}
        {mode === 'buy' && <>
          <Button variant="success" className="action-primary" disabled={(me?.balance || 0) < (pending?.price || 0)}
            onClick={() => send('buy_stadium', { pos: pending?.pos })}>🏟️ BUY FOR {money(pending?.price)}</Button>
          <Button variant="subtle" onClick={() => send('skip', {})}>PASS</Button>
        </>}
        {mode === 'sign' && (
          <Button variant="gold" className="action-primary" onClick={() => onOpen('market')}>👥 SIGN A PLAYER</Button>
        )}
        {mode === 'tactic' && (
          <Button variant="gold" className="action-primary" onClick={() => onOpen('duel')}>🛡️ CHOOSE TACTIC</Button>
        )}
        {mode === 'auction' && (
          <Button variant="gold" className="action-primary" onClick={() => onOpen('auction')}>🔨 BID OR PASS</Button>
        )}
        {mode === 'pass' && <Button disabled>⏳ WAITING FOR REVEAL</Button>}
        {mode === 'continue' && state?.finished && (
          <Button variant="gold" className="action-primary" onClick={() => onOpen('results')}>🏆 VIEW RESULTS</Button>
        )}
        {mode === 'continue' && !state?.finished && (
          <Button variant="gold" className="action-primary" onClick={continueAction}>➜ CONTINUE</Button>
        )}
        {mode === 'waiting' && <Button disabled>⏳ WAITING</Button>}
      </div>
    </div>
  )
}
