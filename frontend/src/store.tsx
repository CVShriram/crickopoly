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
  joinCode: string | null
}

type Action =
  | { type: 'SESSION'; session: Session | null }
  | { type: 'JOIN_CODE'; code: string | null }
  | { type: 'VIEW'; view: View }
  | { type: 'STATE'; state: GameState | null }
  | { type: 'GAMEDATA'; data: GameData }
  | { type: 'SAVED'; rows: SavedRoom[] }
  | { type: 'CONNECTED'; connected: boolean }
  | { type: 'BUSY'; busy: boolean }
  | { type: 'ERROR'; error: string | null }
  | { type: 'STALE_SESSION'; message: string }
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

const urlInfo = (() => {
  try {
    const p = new URLSearchParams(window.location.search)
    return { code: p.get('code') }
  } catch { return { code: null } }
})()

// Any room link is an invitation. Legacy links may still carry a token; it is
// never reused as a login identity, so a stale token cannot trap the opener in
// a broken session.
const urlJoinCode: string | null = urlInfo.code ? urlInfo.code.toUpperCase() : null

const storedSession: Session | null = (() => {
  try { return JSON.parse(localStorage.getItem(SESSION_KEY) || 'null') } catch { return null }
})()
if (urlJoinCode) {
  try { localStorage.removeItem(SESSION_KEY) } catch { /* ignore */ }
}

const initial: AppState = {
  session: urlJoinCode ? null : storedSession,
  sessions: readSessions(),
  view: 'landing',
  state: null,
  gamedata: null,
  saved: [],
  connected: false,
  busy: false,
  error: null,
  toasts: [],
  events: [],
  joinCode: urlJoinCode,
}

let toastId = 1

function toastFor(event: any): Toast | null {
  const text = String(event?.text || '').trim()
  if (!text) return null
  const labels: Record<string, [string, string, Toast['tone']]> = {
    roll: ['DICE ROLLED', '🎲', 'info'],
    buy: ['GROUND BOUGHT', '🏟️', 'green'],
    sign: ['PLAYER SIGNED', '🤝', 'green'],
    auction: ['AUCTION', '🔨', 'gold'],
    bid: ['SEALED BID', '🔨', 'info'],
    match: ['MATCH RESULT', '🏏', 'gold'],
    transfer: ['GROUND TRANSFER', '🏟️', 'danger'],
    skip: ['PASSED', '⏭️', 'info'],
    round: ['ROUND UPDATE', '📅', 'info'],
    final: ['CHAMPION', '🏆', 'gold'],
  }
  const [title, icon, tone] = labels[event.type] || ['UPDATE', '✨', 'info']
  return { id: toastId++, title, text, tone, icon }
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
    case 'JOIN_CODE': return { ...state, joinCode: action.code }
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
    case 'STALE_SESSION':
      localStorage.removeItem(SESSION_KEY)
      return {
        session: null, sessions: state.sessions, view: 'landing', state: null,
        gamedata: state.gamedata, saved: state.saved, connected: false,
        busy: false, error: action.message, toasts: state.toasts,
        events: state.events, joinCode: null,
      }
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
  joinCode: string | null
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
          const text = String(message.message || '')
          if (/invalid room link|room not found|forbidden/i.test(text)) {
            socketRef.current?.close()
            dispatch({
              type: 'STALE_SESSION',
              message: 'That room is no longer available. Start a new game or join with a fresh code.',
            })
            return
          }
          dispatch({ type: 'ERROR', error: text })
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

  const enterRoom = async (
    result: { code: string; player_id: string; state: any },
    identity?: { name: string; avatar: string; color: string },
  ) => {
    const session: Session = {
      code: result.code, playerId: result.player_id,
      name: identity?.name || app.session?.name || 'Manager',
      avatar: identity?.avatar || app.session?.avatar || '🏏',
      color: identity?.color || app.session?.color || '#c8a24b',
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
    try { await enterRoom(await api.createRoom(body), body) }
    catch (e: any) { dispatch({ type: 'ERROR', error: e.message }) }
    finally { dispatch({ type: 'BUSY', busy: false }) }
  }

  const join = async (code: string, name: string, avatar: string, color: string) => {
    dispatch({ type: 'BUSY', busy: true })
    try { await enterRoom(await api.joinRoom(code.trim().toUpperCase(), name, avatar, color), { name, avatar, color }) }
    catch (e: any) { dispatch({ type: 'ERROR', error: e.message }) }
    finally { dispatch({ type: 'BUSY', busy: false }) }
  }

  const quick = async (body: CreateRoomBody) => {
    dispatch({ type: 'BUSY', busy: true })
    try { await enterRoom(await api.quickMatch(body), body) }
    catch (e: any) { dispatch({ type: 'ERROR', error: e.message }) }
    finally { dispatch({ type: 'BUSY', busy: false }) }
  }

  const continueRoom = async (row: SavedRoom) => {
    dispatch({ type: 'BUSY', busy: true })
    try {
      const remote = await api.getRoom(row.code)
      const known = app.sessions.find(s => s.code === row.code)
      const memberIds: string[] = remote.members?.map((m: any) => m.id) || []
      const ids = [known?.playerId, remote.host_id, row.host_id].filter(Boolean) as string[]
      const token = ids.find(id => remote.franchises?.[id] || memberIds.includes(id))
        || remote.host_id || row.host_id
      const session: Session = {
        code: row.code, playerId: token,
        name: known && known.playerId === token ? known.name : remote.franchises?.[token]?.name || 'Manager',
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
    joinCode: app.joinCode,
  }), [app])

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>
}

export function useApp() {
  const ctx = useContext(StoreContext)
  if (!ctx) throw new Error('useApp must be used inside StoreProvider')
  return ctx
}
