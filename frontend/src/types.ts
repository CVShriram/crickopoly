export interface Asset {
  id: string
  owner_id: string
  space_id: number | null
  kind: 'bowler' | 'keeper' | 'fielder' | 'stadium' | 'batsman'
  category: string
  name: string
  level: number
  wickets: number
  max_wickets: number
  runs: number
  active: boolean
  injured_until_round: number
  debuff_until_round: number
  config: Record<string, any>
  is_out?: boolean
  effective_fee?: number
  effective_rent?: number
  effective_reward?: number
  effective_block?: number
  effective_cut?: number
  effective_boost?: number
  run_penalty?: number
  purchase_value?: number
  upgrade_cost?: number
  sale_value?: number
}

export interface Batsman {
  id: string
  owner_id: string
  name: string
  identity_id: string | null
  country: string
  avatar: string
  jersey_color: string
  jersey_number: number
  skin: string
  hair: string
  face: string
  hair_color: string
  is_custom: boolean
  level: number
  wickets: number
  max_wickets: number
  retired: boolean
  runs: number
  injured_until_round: number
  six_runs: number
  upgrade_cost: number | null
  usable: boolean
}

export interface Debt {
  payer_id: string
  receiver_id: string | null
  amount: number
  reason: string
  paid: number
  original: number
  expires_at: number
}

export interface Selection {
  identity_id?: string | null
  is_custom?: boolean
  name?: string
  country?: string
  avatar?: string
  jersey_color?: string
  jersey_number?: number
  skin?: string
  hair?: string
  face?: string
  hair_color?: string
  [key: string]: any
}

export interface Player {
  id: string
  name: string
  avatar: string
  color: string
  money: number
  runs: number
  position: number
  connected: boolean
  ready: boolean
  is_host: boolean
  is_bot?: boolean
  bot_strategy?: string
  eliminated: boolean
  assets: Asset[]
  batsmen: Batsman[]
  active_batsman_id: string | null
  selection: Selection
  no_ball_turns: number
  no_ball_protection: number
  gift_round: number
  debt: Debt | null
  effects: Record<string, any>
  stats: Record<string, number>
  achievements: string[]
  property_count: number
  active_batsmen: number
}

export interface Space {
  id: number
  name: string
  type: string
  category: string | null
  kind: string | null
  price: number
  description: string
}

export interface GameEvent {
  type: string
  payload: Record<string, any>
}

export interface Pending {
  type: string
  player_id: string
  space_id?: number
  batsman_id?: string
  extra_roll?: boolean
  expires_at: number
  [key: string]: any
}

export interface MarketOption {
  identity_id: string
  name: string
  country: string
  avatar: string
  jersey_color: string
  jersey_number: number
  price: number
  wickets: number
  level: number
  available: boolean
}

export interface Market {
  player_id: string
  price: number
  options: MarketOption[]
  expires_at: number
}

export interface Auction {
  space_id: number
  space: Space
  started_by: string
  ends_at: number
  highest_bid: number
  highest_bidder: string | null
  bids: Array<{ player_id: string; amount: number }>
  extra_roll?: boolean
}

export interface RankingRow {
  player_id: string
  name: string
  avatar: string
  runs: number
  money: number
  batsmen: number
  wickets: number
  properties: number
  upgrades: number
  eliminated: boolean
}

export interface GameState {
  room_id: string
  code: string
  players: Player[]
  order: string[]
  current_player_id: string | null
  round: number
  phase: string
  started: boolean
  winner_id: string | null
  dice: number[]
  doubles_count: number
  log: Array<{ round: number; type: string; payload: Record<string, any> }>
  auction: Auction | null
  pending: Pending | null
  trades: Array<{
    id: string
    from: string
    to: string
    give_assets: string[]
    give_money: number
    want_assets: string[]
    want_money: number
    status: string
  }>
  transactions: Array<Record<string, any>>
  started_at: string
  finished_at: string
  viewer_id: string | null
  victory_mode: 'last_standing' | 'turn_limit'
  turn_limit: number
  extra_turn: boolean
  market: Market | null
  ranking: RankingRow[]
}

export interface GameConfig {
  starting_money: number
  salary: number
  batsmen: Record<string, any>
  bowlers: Record<string, any>
  wicket_keepers: Record<string, any>
  fielders: Record<string, any>
  stadiums: Record<string, any>
  achievements: Record<string, string>
  max_level: number
  famous_batsmen: Record<string, {
    name: string
    country: string
    avatar: string
    jersey_color: string
    jersey_number: number
  }>
  custom_defaults: Selection
  custom_skin_options: string[]
  custom_hair_options: string[]
  custom_face_options: string[]
  custom_countries: string[]
  batsman_starting_wickets: number
  max_batsmen: number
  max_batsman_level: number
  batsman_upgrade_costs: Record<string, number>
  six_runs_per_level: number
  no_ball_runs_per_turn: number
  recruitment_cost: number
  victory_modes: string[]
  default_turn_limit: number
  gift_min_coins: number
  gift_max_coins: number
  gift_reserve_coins: number
  gifts_per_round: number
}

export interface LeaderboardRow {
  player_key: string
  name: string
  avatar: string
  color: string
  matches_played: number
  wins: number
  runs: number
  best_runs: number
  coins: number
  wickets_taken: number
  wickets_lost: number
  properties: number
  upgrades: number
  gifts_sent: number
  gifts_received: number
  last_finished_at: string
}

export interface Session {
  code: string
  playerId: string
  name: string
  avatar: string
  color: string
}

export const activeBatsman = (player: Player | undefined | null): Batsman | null => {
  if (!player) return null
  return player.batsmen.find(b => b.id === player.active_batsman_id && b.usable)
    || player.batsmen.find(b => b.usable) || null
}
