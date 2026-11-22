import type { Condition, Franchise, GameState, PlayerData } from './types'

export const money = (value: number | undefined | null) => `${Math.round(value || 0).toLocaleString()} FC`

export const signed = (value: number | undefined | null) =>
  `${value! >= 0 ? '+' : ''}${Math.round(value || 0).toLocaleString()} FC`

export const pct = (value: number) => `${Math.round(value)}%`

export const titleCase = (value: string) =>
  value.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())

export const timeAgo = (ts: number) => {
  const seconds = Math.max(0, Math.floor((Date.now() - ts * 1000) / 1000))
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

export const conditionOf = (f: Franchise | undefined, pid: string): Condition => ({
  fatigue: 0, form: 50, confidence: 50, fitness: 80,
  injury: null, matches_played: 0, training: [],
  ...(f?.conditions?.[pid] || {}),
})

export const effective = (player: PlayerData, cond: Condition, attr: keyof PlayerData) =>
  Number((cond.trained_attrs as any)?.[attr as string] ?? (player as any)[attr] ?? 0)

export const initials = (name: string) => name.split(' ').map(p => p[0]).join('').slice(0, 2).toUpperCase()

export const roleClass = (role: string) => `role-${role}`

export const tierClass = (tier: string) => `tier-${tier}`

export const isMyTurn = (state: GameState | null) =>
  Boolean(state?.started && state.current_player_id === state.you)

export const ownerName = (state: GameState | null, fid: string | undefined | null) =>
  (fid && state?.franchises?.[fid]?.name) || 'Unowned'

export const playerLabel = (state: GameState | null, pid: string | null | undefined) => {
  if (!pid) return '—'
  const p = state?.gamedata?.players?.find(x => x.id === pid)
  return p?.name || pid
}

export const safeNumber = (value: any, fallback = 0) => {
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

export const boardKindLabel = (kind: string) => ({
  market: 'Player Market', stadium: 'Stadium', event: 'Special Event', corner: 'Corner',
}[kind] || kind)
