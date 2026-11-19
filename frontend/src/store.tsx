import React, { createContext, useContext, useEffect, useMemo, useReducer, useRef } from 'react'
import { api } from './api'
import type { GameConfig, GameEvent, GameState, Session, Space } from './types'
import { GameSocket } from './net/socket'
import { sound } from './sound'

export type View = 'landing' | 'lobby' | 'game' | 'squad' | 'profile' | 'results' | 'howto' | 'leaderboard'

export interface Toast {
  id: number
  title: string
  text: string
  tone: 'gold' | 'green' | 'danger' | 'info'
  icon: string
}

interface AppState {
  session: Session | null
  view: View
  state: GameState | null
  board: Space[]
  config: GameConfig | null
  connected: boolean
  error: string | null
  toasts: Toast[]
  events: GameEvent[]
}

type Action =
  | { type: 'SESSION'; session: Session | null }
  | { type: 'VIEW'; view: View }
  | { type: 'STATE'; state: GameState | null }
  | { type: 'BOARD'; board: Space[] }
  | { type: 'CONFIG'; config: GameConfig }
  | { type: 'CONNECTED'; connected: boolean }
  | { type: 'ERROR'; error: string | null }
  | { type: 'EVENTS'; events: GameEvent[] }
  | { type: 'DISMISS'; id: number }

const urlSession: Session | null = (() => {
  try {
    const p = new URLSearchParams(window.location.search)
    const code = p.get('code')
    const token = p.get('token')
    if (!code || !token) return null
    const session: Session = {
      code: code.toUpperCase(), playerId: token,
      name: p.get('name') || 'Manager',
      avatar: p.get('avatar') || '🏏',
      color: p.get('color') || '#22c55e',
    }
    localStorage.setItem('cm-session', JSON.stringify(session))
    return session
  } catch { return null }
})()

const initial: AppState = {
  session: urlSession || (() => {
    try { return JSON.parse(localStorage.getItem('cm-session') || 'null') } catch { return null }
  })(),
  view: urlSession ? 'game' : 'landing',
  state: null,
  board: [],
  config: null,
  connected: false,
  error: null,
  toasts: [],
  events: [],
}

let toastId = 1

function toastFor(event: GameEvent): Toast | null {
  const p = event.payload || {}
  const t = (title: string, text: string, tone: Toast['tone'], icon: string): Toast =>
    ({ id: toastId++, title, text, tone, icon })
  switch (event.type) {
    case 'wicket': return t('WICKET!', `${p.name ?? 'Batsman'} loses a wicket`, 'danger', '🏏')
    case 'batsman_retired': return t('BATSMAN RETIRED', `${p.name ?? 'Batsman'} is out of wickets`, 'danger', '❌')
    case 'batsman_auto_switched': return t('NEW BATSMAN', `${p.name ?? 'Batsman'} takes the crease`, 'info', '🔁')
    case 'batsman_switched': return t('BATSMAN SWITCHED', `${p.name ?? 'Batsman'} is now active`, 'info', '🔁')
    case 'six': return t('SIX!', `+${p.runs ?? 0} runs at level ${p.level ?? 1}`, 'gold', '🚀')
    case 'no_ball': return t('NO BALL!', `${p.text ?? `+${p.bonus ?? 0} bonus runs`} · extra turn`, 'gold', '🚫')
    case 'scoring': return t(p.label ?? 'RUNS', `+${p.runs ?? 0} runs`, 'gold', '🏏')
    case 'milestone': return t('MILESTONE', `${p.threshold} runs reached! +${p.reward} coins`, 'gold', '⭐')
    case 'purchase': case 'auction_won':
      return t(p.type === 'purchase' ? 'PROPERTY SIGNED' : 'AUCTION WON',
        `${p.asset?.name ?? 'Property'} · ${p.price ?? 0} coins`, 'green', '💳')
    case 'fee': return t('FEES PAID', `${p.amount ?? 0} coins at ${p.name ?? 'property'}`, 'info', '💰')
    case 'keeper_penalty': return t('WICKETKEEPER', `${p.runs_lost ?? 0} runs deducted`, 'danger', '🧤')
    case 'wicket_protected': return t('PROTECTED!', p.text ?? 'No-ball protection absorbed the wicket', 'green', '🛡️')
    case 'bowler_attack': return t('BOWLER ATTACK', `${p.name ?? 'Bowler'} strikes — fee paid`, 'danger', '🎯')
    case 'debt_incurred': return t('DEBT!', `${p.amount ?? 0} coins owed — sell or downgrade to recover`, 'danger', '⚠️')
    case 'debt_paid': return t('DEBT CLEARED', `${p.amount ?? 0} coins settled`, 'green', '✅')
    case 'bankrupt': return t('BANKRUPT', 'A manager could not settle their debt', 'danger', '💀')
    case 'batsman_recruited': return t('SIGNED!', `${p.batsman?.name ?? 'New batsman'} joined the squad`, 'green', '🏏')
    case 'batsman_upgraded': return t('BATSMAN UPGRADED', `Level ${p.level} · six now ${p.six_runs_after} runs`, 'gold', '⬆️')
    case 'coins_gifted': return t('COINS SENT', `${p.amount} coins → ${p.to_name ?? 'manager'}`, 'green', '💸')
    case 'upgrade': return t('PROPERTY UPGRADED', `Now level ${p.level}`, 'green', '⬆️')
    case 'downgrade': return t('PROPERTY DOWNGRADED', `+${p.refund ?? 0} emergency coins`, 'info', '⬇️')
    case 'market_offer': return t('RECRUITMENT MARKET', `${p.options?.length ?? 0} batsmen available`, 'info', '🛒')
    case 'recruit_required': return t('RECRUIT A BATSMAN', 'No usable batsman — sign one before rolling', 'danger', '🛒')
    case 'eliminated': return t('ELIMINATED', 'A manager has left the tournament', 'danger', '💀')
    case 'victory': return t('MATCH WON', 'The tournament is complete!', 'gold', '🏆')
    case 'event_card': return t(p.card?.name ?? 'EVENT', p.card?.text ?? '', p.card?.kind === 'bad' ? 'danger' : 'gold', '🎴')
    case 'challenge': return t(p.challenge?.name ?? 'CHALLENGE', p.success ? 'Challenge completed!' : 'Challenge failed', p.success ? 'green' : 'danger', '🎯')
    case 'achievement': return t('ACHIEVEMENT', p.text ?? '', 'gold', '🏅')
    case 'trade_completed': return t('TRADE DONE', 'Assets exchanged', 'green', '🤝')
    case 'free_hit': return t('FREE HIT', 'Next attack is nullified', 'info', '🛡️')
    case 'wicket_blocked': return t('SAVED!', p.text ?? 'Wicket blocked', 'green', '🛡️')
    case 'injury': return t('INJURY', `${p.name ?? 'Batsman'} is out for ${p.rounds ?? 2} rounds`, 'danger', '🩹')
    default: return null
  }
}

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'SESSION':
      if (action.session) localStorage.setItem('cm-session', JSON.stringify(action.session))
      else localStorage.removeItem('cm-session')
      return { ...state, session: action.session }
    case 'VIEW': return { ...state, view: action.view, error: null }
    case 'STATE': {
      const enterGame = !!action.state?.started && (state.view === 'lobby' || state.view === 'landing')
      const enterLobby = !!action.state && !action.state.started && state.view === 'game'
      return { ...state, state: action.state, view: enterGame ? 'game' : enterLobby ? 'lobby' : state.view }
    }
    case 'BOARD': return { ...state, board: action.board }
    case 'CONFIG': return { ...state, config: action.config }
    case 'CONNECTED': return { ...state, connected: action.connected }
    case 'ERROR': return { ...state, error: action.error }
    case 'EVENTS': {
      const toasts = action.events.map(toastFor).filter((x): x is Toast => x !== null).slice(0, 4)
      return { ...state, events: [...state.events, ...action.events].slice(-200), toasts: [...state.toasts, ...toasts].slice(-5) }
    }
    case 'DISMISS': return { ...state, toasts: state.toasts.filter(t => t.id !== action.id) }
    default: return state
  }
}

interface Ctx {
  app: AppState
  dispatch: React.Dispatch<Action>
  send: (action: string, payload?: Record<string, unknown>) => void
  connect: (session: Session) => void
  disconnect: () => void
}

const StoreContext = createContext<Ctx | null>(null)

export function StoreProvider({ children }: { children: React.ReactNode }) {
  const [app, dispatch] = useReducer(reducer, initial)
  const socketRef = useRef<GameSocket | null>(null)

  useEffect(() => {
    api.config().then(config => dispatch({ type: 'CONFIG', config })).catch(() => { /* defaults still work */ })
  }, [])

  const connect = (session: Session) => {
    socketRef.current?.close()
    const socket = new GameSocket(
      session.code, session.playerId,
      message => {
        if (message.type === 'update') {
          dispatch({ type: 'STATE', state: message.state })
          if (message.board) dispatch({ type: 'BOARD', board: message.board })
          const events: GameEvent[] = message.events || []
          if (events.length) {
            dispatch({ type: 'EVENTS', events })
            for (const e of events) {
              const p = e.payload || {}
              if (e.type === 'dice') sound.play('dice')
              else if (e.type === 'move') sound.play('move')
              else if (e.type === 'wicket' || e.type === 'bowler_attack') sound.play('wicket')
              else if (e.type === 'batsman_retired' || e.type === 'eliminated' || e.type === 'bankrupt') sound.play('out')
              else if (e.type === 'six' || e.type === 'no_ball') sound.play('sixer')
              else if (e.type === 'scoring') sound.play(p.runs >= 4 ? 'boundary' : 'runs')
              else if (e.type === 'runs') sound.play('runs')
              else if (e.type === 'purchase' || e.type === 'auction_won' || e.type === 'batsman_recruited' || e.type === 'batsman_upgraded' || e.type === 'coins_gifted') sound.play('buy')
              else if (e.type === 'fee' || e.type === 'debt_paid' || e.type === 'salary' || e.type === 'milestone') sound.play('money')
              else if (e.type === 'debt_incurred' || e.type === 'recruit_required') sound.play('wicket')
              else if (e.type === 'event_card' || e.type === 'challenge' || e.type === 'wicket_protected') sound.play('card')
              else if (e.type === 'victory') sound.play('victory')
            }
          }
        } else if (message.type === 'error') {
          dispatch({ type: 'ERROR', error: message.message })
        }
      },
      connected => dispatch({ type: 'CONNECTED', connected }),
    )
    socketRef.current = socket
    socket.connect()
  }

  const disconnect = () => {
    socketRef.current?.close()
    socketRef.current = null
  }

  const sessionCode = app.session?.code
  const sessionPlayer = app.session?.playerId
  useEffect(() => {
    if (!sessionCode || !sessionPlayer) return
    connect({ code: sessionCode, playerId: sessionPlayer,
              name: app.session!.name, avatar: app.session!.avatar, color: app.session!.color })
    return () => {
      socketRef.current?.close()
      socketRef.current = null
    }
  }, [sessionCode, sessionPlayer])

  const send = (action: string, payload: Record<string, unknown> = {}) => {
    if (!socketRef.current?.send(action, payload)) {
      dispatch({ type: 'ERROR', error: 'Reconnecting to server…' })
    }
  }

  const value = useMemo(() => ({ app, dispatch, send, connect, disconnect }), [app])
  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>
}

export function useApp() {
  const ctx = useContext(StoreContext)
  if (!ctx) throw new Error('useApp must be used inside StoreProvider')
  return ctx
}
