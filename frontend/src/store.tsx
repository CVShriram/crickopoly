import React, { createContext, useContext, useEffect, useMemo, useReducer, useRef } from 'react'
import { api, type CreateRoomBody } from './api'
import { GameSocket } from './net/socket'
import type { GameData, GameEvent, GameState, SavedRoom, Session, Toast } from './types'

export type View = 'landing' | 'lobby' | 'draft' | 'board' | 'squad' | 'auction'
  | 'markets' | 'match' | 'tournament' | 'ledger' | 'admin' | 'results' | 'howto'

interface AppState {
  session: Session | null
  sessions: Session[]
  view: View
  state: GameState | null
  gamedata: GameData | null
  saved: SavedRoom[]
  connected: boolean
  busy: boolean
  error: string | null
  toasts: Toast[]
  events: any[]
}

type Action =
  | { type: 'SESSION'; session: Session | null }
  | { type: 'VIEW'; view: View }
  | { type: 'STATE'; state: GameState | null }
  | { type: 'GAMEDATA'; data: GameData }
  | { type: 'SAVED'; rows: SavedRoom[] }
  | { type: 'CONNECTED'; connected: boolean }
  | { type: 'BUSY'; busy: boolean }
  | { type: 'ERROR'; error: string | null }
  | { type: 'EVENTS'; events: any[] }
  | { type: 'DISMISS'; id: number }

const SESSION_KEY = 'fg-session'
const SESSIONS_KEY = 'fg-sessions'

function readSessions(): Session[] {
  try { return JSON.parse(localStorage.getItem(SESSIONS_KEY) || '[]') } catch { return [] }
}

function writeSessions(sessions: Session[]) {
  try { localStorage.setItem(SESSIONS_KEY, JSON.stringify(sessions.slice(0, 12))) } catch { /* ignore */ }
}

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
      color: p.get('color') || '#c8a24b',
    }
    const all = readSessions().filter(s => s.code !== session.code)
    writeSessions([session, ...all])
    localStorage.setItem(SESSION_KEY, JSON.stringify(session))
    return session
  } catch { return null }
})()

const initial: AppState = {
  session: urlSession || (() => {
    try { return JSON.parse(localStorage.getItem(SESSION_KEY) || 'null') } catch { return null }
  })(),
  sessions: readSessions(),
  view: urlSession ? 'board' : 'landing',
  state: null,
  gamedata: null,
  saved: [],
  connected: false,
  busy: false,
  error: null,
  toasts: [],
  events: [],
}

let toastId = 1

function toastFor(event: any): Toast | null {
  const p = event.payload || {}
  const t = (title: string, text: string, tone: Toast['tone'], icon: string): Toast =>
    ({ id: toastId++, title, text, tone, icon })
  switch (event.type) {
    case 'roll': return t('DICE ROLLED', `${(p.dice || []).join(' + ')} → tile ${p.to}`, 'info', '🎲')
    case 'purchase': return t('ASSET SIGNED', p.payload?.price ? `${p.payload.price} FC` : 'Purchase complete', 'green', '🏟️')
    case 'event': return t('SPECIAL TILE', String(p.type || p.name || 'Event resolved'), 'gold', '✨')
    case 'tile_event': return t('EVENT RESOLVED', String(p.result?.type || p.event || 'Board effect applied'), 'gold', '✨')
    case 'auction_won': return t('AUCTION WON', `${p.player_name || p.player_id} · ${p.price} FC`, 'gold', '🔨')
    case 'auction_unsold': return t('LOT UNSOLD', 'No qualifying bid', 'info', '🔨')
    case 'match': return t('MATCH COMPLETE', p.winner_name ? `${p.winner_name} win` : 'Result recorded', 'gold', '🏏')
    case 'trade_offered': return t('TRADE RECEIVED', 'A two-sided offer awaits confirmation', 'info', '🤝')
    case 'trade_completed': return t('TRADE COMPLETE', 'Contracts and FC exchanged', 'green', '🤝')
    case 'training': return t('TRAINING DONE', `${p.attr} improved to ${p.after}`, 'green', '🏋️')
    case 'champion': return t('CHAMPION CROWNED', String(p.winner_name || 'Season complete'), 'gold', '🏆')
    default: return null
  }
}

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'SESSION': {
      if (action.session) {
        localStorage.setItem(SESSION_KEY, JSON.stringify(action.session))
        const all = [action.session, ...state.sessions.filter(s => s.code !== action.session!.code)]
        writeSessions(all)
        return { ...state, session: action.session, sessions: all }
      }
      localStorage.removeItem(SESSION_KEY)
      return { ...state, session: null }
    }
    case 'VIEW': return { ...state, view: action.view, error: null }
    case 'STATE': {
      const s = action.state as any
      if (!s) return { ...state, state: null }
      let view = state.view
      if (s.started && ['landing', 'lobby'].includes(view)) {
        view = s.phase === 'draft' ? 'draft' : 'board'
      } else if (s.started && view === 'draft' && s.phase !== 'draft') {
        view = s.phase === 'over' ? 'results' : 'board'
      } else if (!s.started && ['draft', 'board', 'squad', 'auction', 'markets', 'match',
        'tournament', 'ledger', 'admin', 'results'].includes(view)) {
        view = 'lobby'
      }
      return {
        ...state, state: s, view,
        gamedata: s.gamedata || state.gamedata,
      }
    }
    case 'GAMEDATA': return { ...state, gamedata: action.data }
    case 'SAVED': return { ...state, saved: action.rows }
    case 'CONNECTED': return { ...state, connected: action.connected }
    case 'BUSY': return { ...state, busy: action.busy }
    case 'ERROR': return { ...state, error: action.error, busy: false }
    case 'EVENTS': {
      const toasts = action.events.map(toastFor).filter((x): x is Toast => x !== null).slice(0, 4)
      return {
        ...state, events: [...state.events, ...action.events].slice(-200),
        toasts: [...state.toasts, ...toasts].slice(-5),
      }
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
  setSession: (session: Session | null) => void
  create: (body: CreateRoomBody) => Promise<void>
  join: (code: string, name: string, avatar: string, color: string) => Promise<void>
  quick: (body: CreateRoomBody) => Promise<void>
  continueRoom: (row: SavedRoom) => Promise<void>
  refreshSaved: () => Promise<void>
}

const StoreContext = createContext<Ctx | null>(null)

export function StoreProvider({ children }: { children: React.ReactNode }) {
  const [app, dispatch] = useReducer(reducer, initial)
  const socketRef = useRef<GameSocket | null>(null)
  const sessionRef = useRef<Session | null>(app.session)
  sessionRef.current = app.session

  const refreshSaved = async () => {
    try { dispatch({ type: 'SAVED', rows: await api.saved() }) } catch { /* offline */ }
  }

  useEffect(() => {
    api.gamedata().then(data => dispatch({ type: 'GAMEDATA', data })).catch(() => {})
    refreshSaved()
  }, [])

  const connect = (session: Session) => {
    socketRef.current?.close()
    const socket = new GameSocket(
      session.code, session.playerId,
      message => {
        if (message.type === 'update') {
          dispatch({ type: 'STATE', state: message.state })
          const events: GameEvent[] = message.events || []
          if (events.length) dispatch({ type: 'EVENTS', events })
          if (message.you && sessionRef.current && sessionRef.current.playerId !== message.you) {
            // Server is authoritative about identity; keep the session in sync.
          }
        } else if (message.type === 'error') {
          dispatch({ type: 'ERROR', error: message.message })
        }
      },
      connected => dispatch({ type: 'CONNECTED', connected }),
    )
    socketRef.current = socket
    socket.connect()
    return socket
  }

  const disconnect = () => {
    socketRef.current?.close()
    socketRef.current = null
    dispatch({ type: 'CONNECTED', connected: false })
  }

  const sessionCode = app.session?.code
  const sessionPlayer = app.session?.playerId
  useEffect(() => {
    if (!sessionCode || !sessionPlayer) return
    connect({ code: sessionCode, playerId: sessionPlayer,
              name: app.session!.name, avatar: app.session!.avatar, color: app.session!.color })
    return () => { socketRef.current?.close(); socketRef.current = null }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionCode, sessionPlayer])

  const setSession = (session: Session | null) => {
    dispatch({ type: 'SESSION', session })
    if (session) {
      // The session-change effect below owns the socket. Calling connect here
      // too opens a second socket, and the stale socket's disconnect can drop
      // the live connection from the server's connection map.
      dispatch({ type: 'VIEW', view: 'lobby' })
    } else {
      disconnect()
      dispatch({ type: 'VIEW', view: 'landing' })
    }
  }

  const enterRoom = async (result: { code: string; player_id: string; state: any }) => {
    const session: Session = {
      code: result.code, playerId: result.player_id,
      name: app.session?.name || 'Manager',
      avatar: app.session?.avatar || '🏏',
      color: app.session?.color || '#c8a24b',
    }
    dispatch({ type: 'STATE', state: result.state })
    setSession(session)
    if (result.state?.started) {
      dispatch({ type: 'VIEW', view: result.state.phase === 'draft' ? 'draft' : 'board' })
    }
    await refreshSaved()
  }

  const create = async (body: CreateRoomBody) => {
    dispatch({ type: 'BUSY', busy: true })
    try { await enterRoom(await api.createRoom(body)) }
    catch (e: any) { dispatch({ type: 'ERROR', error: e.message }) }
    finally { dispatch({ type: 'BUSY', busy: false }) }
  }

  const join = async (code: string, name: string, avatar: string, color: string) => {
    dispatch({ type: 'BUSY', busy: true })
    try { await enterRoom(await api.joinRoom(code.trim().toUpperCase(), name, avatar, color)) }
    catch (e: any) { dispatch({ type: 'ERROR', error: e.message }) }
    finally { dispatch({ type: 'BUSY', busy: false }) }
  }

  const quick = async (body: CreateRoomBody) => {
    dispatch({ type: 'BUSY', busy: true })
    try { await enterRoom(await api.quickMatch(body)) }
    catch (e: any) { dispatch({ type: 'ERROR', error: e.message }) }
    finally { dispatch({ type: 'BUSY', busy: false }) }
  }

  const continueRoom = async (row: SavedRoom) => {
    dispatch({ type: 'BUSY', busy: true })
    try {
      const remote = await api.getRoom(row.code)
      const known = app.sessions.find(s => s.code === row.code)
      const token = known?.playerId || remote.host_id || row.host_id
      const session: Session = {
        code: row.code, playerId: token,
        name: known?.name || remote.franchises?.[token]?.name || 'Manager',
        avatar: known?.avatar || remote.franchises?.[token]?.avatar || '🏏',
        color: known?.color || remote.franchises?.[token]?.color || '#c8a24b',
      }
      dispatch({ type: 'STATE', state: remote })
      setSession(session)
      dispatch({ type: 'VIEW', view: remote.started ? (remote.phase === 'draft' ? 'draft' : 'board') : 'lobby' })
    } catch (e: any) {
      dispatch({ type: 'ERROR', error: e.message })
    } finally { dispatch({ type: 'BUSY', busy: false }) }
  }

  const send = (action: string, payload: Record<string, unknown> = {}) => {
    let socket = socketRef.current
    if (!socket && app.session) socket = connect(app.session)
    if (!socket) {
      dispatch({ type: 'ERROR', error: 'Join a room before sending actions.' })
      return
    }
    socket.send(action, payload)
  }

  const value = useMemo(() => ({
    app, dispatch, send, connect, disconnect, setSession,
    create, join, quick, continueRoom, refreshSaved,
  }), [app])

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>
}

export function useApp() {
  const ctx = useContext(StoreContext)
  if (!ctx) throw new Error('useApp must be used inside StoreProvider')
  return ctx
}
