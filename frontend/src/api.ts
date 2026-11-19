// Empty by default: in production the FastAPI process also serves the built
// React app, so API and WebSocket calls stay on the same origin. Vite dev can
// still point at a separate backend by setting VITE_API_URL before `npm run dev`.
export const API_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
const sameOriginWs = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`
export const WS_URL = (import.meta.env.VITE_WS_URL
  || (API_URL ? API_URL.replace(/^http/, 'ws') : sameOriginWs)).replace(/\/$/, '')

async function request<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail || 'Request failed')
  return data as T
}

export const api = {
  board: () => request<any[]>('/api/board'),
  config: () => request<any>('/api/config'),
  history: () => request<any[]>('/api/history'),
  leaderboard: (limit = 50) => request<any[]>(`/api/leaderboard?limit=${limit}`),
  createRoom: (name: string, avatar: string, color: string) =>
    request<any>('/api/rooms', {
      method: 'POST', body: JSON.stringify({ name, avatar, color }),
    }),
  joinRoom: (code: string, name: string, avatar: string, color: string) =>
    request<any>('/api/rooms/join', {
      method: 'POST', body: JSON.stringify({ code, name, avatar, color }),
    }),
  setReady: (code: string, playerId: string, ready: boolean) =>
    request<any>(`/api/rooms/${code}/ready`, {
      method: 'POST', body: JSON.stringify({ player_id: playerId, ready }),
    }),
  startGame: (code: string, playerId: string) =>
    request<any>(`/api/rooms/${code}/start`, {
      method: 'POST', body: JSON.stringify({ player_id: playerId }),
    }),
  addBots: (code: string, count = 1, strategy = 'smart') =>
    request<any>(`/api/rooms/${code}/bots`, {
      method: 'POST', body: JSON.stringify({ count, strategy }),
    }),
  quickMatch: (name: string, bots = 2, strategy = 'smart',
    victoryMode = 'last_standing', turnLimit = 20) =>
    request<{ code: string; player_id: string; url: string }>('/api/test/match', {
      method: 'POST',
      body: JSON.stringify({ name, bots, strategy, victory_mode: victoryMode, turn_limit: turnLimit }),
    }),
}
