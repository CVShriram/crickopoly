// Production serves the built React app from the same FastAPI process, so all
// API and WebSocket calls stay on the current origin. Vite dev can override it.
export const API_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
export const WS_URL = (import.meta.env.VITE_WS_URL
  || (API_URL ? API_URL.replace(/^http/, 'ws') : `${wsProtocol}://${window.location.host}`)).replace(/\/$/, '')

async function request<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail || data.message || 'Request failed')
  return data as T
}

export interface CreateRoomBody {
  name: string
  avatar: string
  color: string
  settings?: Record<string, unknown>
}

const FG = '/api/fg'

export const api = {
  gamedata: () => request<import('./types').GameData>(`${FG}/gamedata`),
  saved: () => request<import('./types').SavedRoom[]>(`${FG}/saved`),
  createRoom: (body: CreateRoomBody) =>
    request<{ room_id: string; code: string; player_id: string; state: any }>(`${FG}/rooms`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  joinRoom: (code: string, name: string, avatar: string, color: string) =>
    request<{ room_id: string; code: string; player_id: string; state: any }>(`${FG}/rooms/join`, {
      method: 'POST', body: JSON.stringify({ code, name, avatar, color }),
    }),
  getRoom: (code: string) => request<any>(`${FG}/rooms/${encodeURIComponent(code)}`),
  startRoom: (code: string, playerId: string) =>
    request<any>(`${FG}/rooms/${encodeURIComponent(code)}/start`, {
      method: 'POST', body: JSON.stringify({ player_id: playerId }),
    }),
  addBots: (code: string, playerId: string, count: number, difficulty: string) =>
    request<any>(`${FG}/rooms/${encodeURIComponent(code)}/bots`, {
      method: 'POST', body: JSON.stringify({ player_id: playerId, count, difficulty }),
    }),
  updateSettings: (code: string, playerId: string, settings: Record<string, unknown>) =>
    request<any>(`${FG}/rooms/${encodeURIComponent(code)}/settings`, {
      method: 'POST', body: JSON.stringify({ player_id: playerId, settings }),
    }),
  quickMatch: (body: CreateRoomBody) =>
    request<{ room_id: string; code: string; player_id: string; state: any }>(`${FG}/quick`, {
      method: 'POST', body: JSON.stringify(body),
    }),
}
