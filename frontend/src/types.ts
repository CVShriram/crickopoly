export type Role = 'batsman' | 'bowler' | 'wicketkeeper' | 'allrounder'
export type Tier = 'bronze' | 'silver' | 'gold'

export interface PlayerData {
  id: string
  name: string
  country: string
  flag: string
  role: Role
  tier: Tier
  overall: number
  batting: number
  bowling: number
  fielding: number
  fitness: number
  consistency: number
  form: number
  confidence: number
  abilities: Record<string, number>
  value: number
  portrait_hue: number
}

export interface Tile {
  position: number
  kind: 'market' | 'stadium' | 'event' | 'corner'
  id: string
  name: string
  icon: string
  desc: string
  country?: string
  role?: Role
  price?: number
  pitch?: string
  landing_fee?: number
  match_revenue?: number
  short?: string
}

export interface GameData {
  countries: Record<string, { name: string; flag: string; color: string }>
  roles: Role[]
  role_labels: Record<Role, string>
  role_short: Record<Role, string>
  tiers: Tier[]
  pitches: Record<string, { name: string; icon: string; desc: string }>
  board: Tile[]
  players: PlayerData[]
  stadiums: Record<string, any>
  stadium_upgrades: Record<string, { name: string; cost: number; desc: string }>
  events: Record<string, { name: string; icon: string; desc: string }>
  sponsors: Array<{ id: string; name: string; icon: string; per_round: number; reputation: number }>
  training: Record<string, { name: string; cost: number; attr: string; gain: number; icon: string }>
  injuries: Record<string, { name: string; matches: number; cost: number; icon: string }>
  tactical_cards: Record<string, {
    id: string; name: string; icon: string; desc: string; phase?: string
    kind?: string; run_mod?: number; bowl_mod?: number; risk?: number
    pitch?: string; pitch_run?: number; pitch_wicket?: number
  }>
  rules: Record<string, any>
}

export interface Condition {
  fatigue: number
  form: number
  confidence: number
  fitness: number
  injury: null | { type: string; severity: string; matches_left: number; cost: number; icon: string }
  matches_played: number
  training: string[]
  trained_attrs?: Record<string, number>
}

export interface Franchise {
  id: string
  name: string
  avatar: string
  color: string
  is_host?: boolean
  is_bot?: boolean
  difficulty?: string
  balance: number
  reputation: number
  pos: number
  squad: Record<string, { price: number; tier: Tier }>
  xi: string[]
  captain: string | null
  vice: string | null
  markets: number[]
  stadiums: Record<string, string[]>
  sponsors: string[]
  cards: string[]
  conditions: Record<string, Condition>
  record: {
    played: number; wins: number; losses: number; ties: number; points: number; bonus: number
    runs_for: number; runs_against: number; overs_for: number; overs_against: number
  }
  fatigue: number
  last_action: string
}

export interface StandingRow {
  id: string
  name: string
  color: string
  played: number
  wins: number
  losses: number
  ties: number
  points: number
  nrr: number
  runs_for: number
  record: string
  rank: number
}

export interface FinalRow {
  id: string
  name: string
  color: string
  championship: number
  finance: number
  squad: number
  infrastructure: number
  collections: number
  total: number
  league_points: number
  rank: number
  final_rank: number
}

export interface Trade {
  id: string
  from: string
  to: string
  give: { players: string[]; stadiums: number[]; sponsors: string[]; cards: string[]; cash: number }
  want: { players: string[]; stadiums: number[]; sponsors: string[]; cards: string[]; cash: number }
  message: string
  status: 'pending' | 'executed' | 'rejected' | 'cancelled'
  created_at: number
  round: number
}

export interface MatchRecord {
  id: string
  round: number
  a: string
  b: string
  a_name: string
  b_name: string
  a_runs: number
  a_wickets: number
  b_runs: number
  b_wickets: number
  winner: string | null
  winner_name: string
  pitch: string
  seed: number
  analysis: string
  player_of_match: string | null
  phases_a: any[]
  phases_b: any[]
  tactics: Record<string, any>
  playoff_stage?: string
}

export interface GameState {
  room_id: string
  code: string
  host_id?: string
  mode: 'standard' | 'classic'
  phase: 'draft' | 'season' | 'playoffs' | 'over' | 'lobby'
  season: number
  round: number
  current_player_id: string | null
  order: string[]
  started: boolean
  finished: boolean
  winner_id: string | null
  pitch: string
  settings: Record<string, any>
  franchises: Record<string, Franchise>
  players: PlayerData[]
  board: Tile[]
  ownership: Record<string, string>
  auctions: Record<string, any>
  auction: any | null
  pending: any | null
  matches: MatchRecord[]
  transactions: any[]
  log: any[]
  events: any[]
  dice: number[]
  playoff_bracket: any
  gamedata?: GameData
  standings?: StandingRow[]
  final_points?: FinalRow[]
  trade_offers?: Trade[]
  transfer_window?: { open: boolean; every: number; next_round: number; round: number }
  tactics_submissions?: Record<string, any>
  tactics_submitted?: string[]
  tactics_concealed?: boolean
  data_overrides?: Record<string, any>
  you?: string
}

export interface LobbyMember {
  id: string
  name: string
  avatar: string
  color: string
  is_bot: boolean
  difficulty: string
  is_host: boolean
  ready: boolean
}

export interface LobbyState {
  room_id: string
  code: string
  phase: 'lobby'
  started: false
  members: LobbyMember[]
  settings: Record<string, any>
  host_id: string
  you?: string
  gamedata: GameData
}

export interface SavedRoom {
  code: string
  room_id: string
  host_id: string
  created_at: number
  updated_at: number
  phase: string
  round: number
  mode: string
  finished: boolean
  winner_id: string | null
  winner_name?: string
  franchises: string[]
  matches: number
}

export interface Session {
  code: string
  playerId: string
  name: string
  avatar: string
  color: string
}

export interface Toast {
  id: number
  title: string
  text: string
  tone: 'gold' | 'green' | 'danger' | 'info'
  icon: string
}

export interface GameEvent {
  type: string
  payload?: any
  round?: number
  [key: string]: any
}

export const playerById = (state: GameState | null, id: string | null | undefined): PlayerData | undefined => {
  if (!state || !id) return undefined
  return (state.gamedata?.players || state.players || []).find(p => p.id === id)
}

export const me = (state: GameState | null): Franchise | undefined =>
  state?.you && state.franchises ? state.franchises[state.you] : undefined

/* ------------------------------------------------------------------------- *
 * Stadium Tycoon (ruleset 2) — additive view types.
 * The legacy interfaces above are intentionally untouched: old screens may
 * still import them, but the new single-screen UI reads the shapes below.
 * ------------------------------------------------------------------------- */

export interface TycoonFranchise {
  id: string
  name: string
  avatar: string
  color: string
  is_host?: boolean
  is_bot?: boolean
  difficulty?: string
  pos: number
  balance: number
  squad: string[]
  tactics: string[]
  stadiums: Array<string | number>
  duels_won: number
  last_action: string
}

export interface TycoonStanding {
  rank: number
  id: string
  name: string
  avatar?: string
  color: string
  brand_value: number
  cash: number
  stadiums: number
  players: number
  duels_won: number
}

export interface TycoonScorecardSide {
  id: string
  name: string
  runs: number
  wickets: number
  card: string
  icon?: string
}

export interface TycoonScorecard {
  challenger: TycoonScorecardSide
  defender: TycoonScorecardSide
}

/** Server descriptors. Optional members reflect the different pending phases. */
export interface TycoonPending {
  type: 'buy_stadium' | 'sign_player' | 'duel' | 'result' | string
  pid?: string
  pos?: number
  price?: number
  title?: string
  country?: string
  role?: string
  candidates?: string[]
  defender?: string
  rent?: number
  pot?: boolean
  cards?: Record<string, string>
  result?: unknown
  label?: string
  text?: string
  scorecard?: TycoonScorecard
  pitch?: string
  winner_id?: string | null
  paid?: number
  multiplier?: number
  viewers?: string[]
}

export interface TycoonAuction {
  id: string
  player_id: string
  base_price: number
  bids: Record<string, number>
  passed: string[]
  opened_by: string
  revealed: boolean
  my_bid?: number
  has_passed?: boolean
  player?: PlayerData
}

export interface TycoonLogEntry {
  text?: string
  kind?: string
  round?: number
}

export interface TycoonState {
  room_id: string
  code: string
  host_id?: string
  ruleset?: number
  started: boolean
  finished: boolean
  phase: string
  season?: number
  round: number
  mode?: string
  current_player_id: string | null
  order: string[]
  pitch: string
  settings?: Record<string, unknown>
  franchises: Record<string, TycoonFranchise>
  board: Tile[]
  ownership: Record<string, string>
  dice: number[]
  pending: TycoonPending | null
  auction: TycoonAuction | null
  standings: TycoonStanding[]
  gamedata: GameData
  you?: string
  log: TycoonLogEntry[]
  winner_id?: string | null
  data_overrides?: Record<string, unknown>
}

export interface TycoonLobby {
  room_id: string
  code: string
  host_id: string
  phase: 'lobby'
  started: false
  finished?: boolean
  ruleset?: number
  members: LobbyMember[]
  settings: Record<string, unknown>
  you?: string
  data_overrides?: Record<string, unknown>
  gamedata: GameData
}

/* ------------------------------------------------------------------------- *
 * Cricket Card Battle (ruleset 3) — additive view types.
 * Nothing above is removed: legacy screens keep their original contracts.
 * Fields that are masked or not always present are optional here.
 * ------------------------------------------------------------------------- */

export interface BattleFranchise {
  id: string
  name: string
  avatar: string
  color: string
  is_bot?: boolean
  is_host?: boolean
  hand: string[]
  points: number
  total_score: number
  played: number
}

export interface BattlePlay {
  player_id: string
  tactic_id: string
}

export interface BattleResultRow {
  pid: string
  name: string
  avatar?: string
  color?: string
  runs: number
  wickets: number
  score: number
  player_id: string
  tactic_id: string
  won?: boolean
}

export interface BattleResult {
  round: number
  pitch: string
  rows: BattleResultRow[]
  winner_id: string | null
}

export interface BattleTactic {
  id: string
  name: string
  icon?: string
  desc?: string
  phase?: string
  kind?: string
  run_mod?: number
  bowl_mod?: number
  risk?: number
  wicket_mod?: number
  pitch?: string
  pitch_run?: number
  pitch_wicket?: number
  [key: string]: any
}

export interface BattleStanding {
  id: string
  name: string
  avatar?: string
  color: string
  points: number
  total_score: number
  rank: number
}

export interface BattlePending {
  type: string
  viewers?: string[]
  [key: string]: any
}

export interface BattleState {
  room_id: string
  code: string
  host_id?: string
  ruleset?: number
  started: boolean
  finished: boolean
  phase: string
  round: number
  rounds?: number
  current_player_id: string | null
  order: string[]
  pitch: string
  settings?: Record<string, unknown>
  franchises: Record<string, BattleFranchise>
  plays?: Record<string, BattlePlay>
  revealed?: boolean
  pending: BattlePending | null
  last_result: BattleResult | null
  standings: BattleStanding[]
  gamedata: GameData
  you?: string
  winner_id?: string | null
}

export interface BattleLobby {
  room_id: string
  code: string
  host_id: string
  phase: 'lobby'
  started: false
  finished?: boolean
  ruleset?: number
  members: LobbyMember[]
  settings: Record<string, unknown>
  you?: string
  gamedata?: GameData
}

export type GameModal =
  | 'assets' | 'guide' | 'results' | 'history' | 'studio'
  | 'auction' | 'duel' | 'result' | 'market'
  | null

/* ------------------------------------------------------------------------- *
 * Wicket Rush (ruleset 4) — additive view types.
 * Nothing above is removed. These shapes describe the server snapshot that
 * the single-screen Rush UI consumes; optional members cover masked fields.
 * ------------------------------------------------------------------------- */

export interface RushLastCard {
  player_id: string
  name: string
  role: Role
  effect?: unknown
  owner_id?: string | null
  [key: string]: unknown
}

export interface RushPending {
  type: 'target' | string
  pid?: string
  effect?: unknown
  candidates?: string[]
  [key: string]: unknown
}

export interface RushFranchise {
  id: string
  name: string
  avatar: string
  color: string
  is_bot?: boolean
  is_host?: boolean
  /** Only present for the viewer; rivals expose hand_count instead. */
  hand?: string[]
  hand_count?: number
  runs: number
  wickets: number
  drawn?: number
  [key: string]: unknown
}

export interface RushStanding {
  id: string
  name: string
  avatar?: string
  color: string
  runs: number
  wickets: number
  cards: number
  score: number
  rank: number
}

export interface RushState {
  room_id: string
  code: string
  host_id?: string
  ruleset?: number
  started: boolean
  finished: boolean
  phase: string
  turn: number
  order: string[]
  current_player_id: string | null
  current_role: Role | null
  /** Set after a batsman: only a bowler or all-rounder may be played next. */
  forced_role?: Role | null
  direction: number
  last_card: RushLastCard | null
  deck_count: number
  franchises: Record<string, RushFranchise>
  pending: RushPending | null
  last_event: { type: string; text: string } | null
  standings: RushStanding[]
  gamedata: GameData
  settings?: Record<string, unknown>
  you?: string
  winner_id?: string | null
  [key: string]: unknown
}

export interface RushLobby {
  room_id: string
  code: string
  host_id: string
  phase: 'lobby'
  started: false
  finished?: boolean
  ruleset?: number
  members: LobbyMember[]
  settings: Record<string, unknown>
  you?: string
  gamedata?: GameData
  last_event?: { type: string; text: string } | null
  [key: string]: unknown
}

/* ------------------------------------------------------------------------- *
 * Cricket Monopoly (ruleset 5) — additive view types.
 * The legacy interfaces above are intentionally untouched. These shapes
 * describe the 52-square snapshot consumed by the MonopolyScreen UI.
 * ------------------------------------------------------------------------- */

export interface MonopolyCountryMeta {
  name?: string
  flag?: string
  color?: string
  [key: string]: unknown
}

export interface MonopolyGameData {
  players: PlayerData[]
  countries: Record<string, MonopolyCountryMeta>
  roles?: string[]
  rules?: Record<string, unknown>
  [key: string]: unknown
}

export interface MonopolyProperty {
  owner?: string | null
  level?: number
  price?: number
  [key: string]: unknown
}

export interface MonopolyPending {
  type: 'buy' | 'auction' | 'trade' | string
  pid?: string
  tile_id?: number | string
  price?: number
  /** v6 trade offers: proposer, target and the two swapped squares. */
  target?: string
  give_tile?: number | string
  take_tile?: number | string
  [key: string]: unknown
}

/** v6 pending variant: swap one property for one rival property, no money. */
export type MonopolyTradePending = MonopolyPending & {
  type: 'trade'
  pid: string
  target: string
  give_tile: number | string
  take_tile: number | string
}

export interface MonopolyFranchise {
  id: string
  name: string
  avatar: string
  color: string
  is_bot?: boolean
  is_host?: boolean
  difficulty?: string
  pos: number
  fc: number
  runs: number
  wickets: number
  max_wickets?: number
  laps: number
  squad: string[] | number
  skipped?: number | boolean
  injured?: number | boolean
  owned?: Array<string | number> | number
  out?: boolean
  /** v6: upgrades unlock when the manager holds BAT + BOWL + WK + a ground. */
  unlocked?: boolean
  /** v6: tile id of the first ground owned; enables the home-ground bonus. */
  home_ground?: string | number | null
  [key: string]: unknown
}

export interface MonopolyStanding {
  id: string
  name: string
  avatar?: string
  color: string
  runs: number
  fc: number
  wickets: number
  laps: number
  rank: number
  [key: string]: unknown
}

export interface MonopolyLastEvent {
  type: string
  text: string
  [key: string]: unknown
}

export interface MonopolyState {
  room_id?: string
  code: string
  host_id?: string
  ruleset?: number
  started: boolean
  finished: boolean
  phase: 'lobby' | 'play' | 'over' | string
  turn: number
  laps?: number
  order: string[]
  turn_index?: number
  current_player_id: string | null
  dice: number[]
  rolled?: boolean
  pending: MonopolyPending | null
  board: Tile[]
  properties: Record<string, MonopolyProperty>
  franchises: Record<string, MonopolyFranchise>
  last_event?: MonopolyLastEvent | null
  standings: MonopolyStanding[]
  gamedata: MonopolyGameData
  settings?: Record<string, unknown>
  you?: string
  winner_id?: string | null
  members?: LobbyMember[]
  log?: Array<{ text?: string; type?: string; [key: string]: unknown }>
  [key: string]: unknown
}

export interface MonopolyLobby {
  room_id?: string
  code: string
  host_id: string
  phase: 'lobby'
  started: false
  finished?: boolean
  ruleset?: number
  members: LobbyMember[]
  settings: Record<string, unknown>
  you?: string
  gamedata: MonopolyGameData
  [key: string]: unknown
}

/* ------------------------------------------------------------------------- *
 * Auction + Tournament (ruleset 7) — additive view types.
 * Nothing above is removed. These shapes describe the sealed-bid auction and
 * round-robin tournament snapshot consumed by AuctionTournamentScreen.
 * Optional / index-signature members cover fields that arrive only at certain
 * phases, or that the server masks until a lot is resolved.
 * ------------------------------------------------------------------------- */

export interface AuctionTournamentPlayer {
  id: string
  name: string
  country?: string
  flag?: string
  role?: string | Role
  tier?: string
  overall?: number
  /** Some data sets expose BAT/BOWL as `bat`/`bowl`, others as `batting`/`bowling`. */
  bat?: number
  bowl?: number
  batting?: number
  bowling?: number
  value?: number
  portrait_hue?: number
  [key: string]: unknown
}

export interface AuctionTournamentBid {
  player_id?: string
  amount?: number
  [key: string]: unknown
}

export interface AuctionTournamentFranchise {
  id: string
  name: string
  avatar: string
  color: string
  is_bot?: boolean
  fc: number
  squad: string[]
  captain: string | null
  tactic: string | null
  points: number
  total_score: number
  wins: number
  losses: number
  [key: string]: unknown
}

export interface AuctionTournamentStanding {
  id: string
  name: string
  avatar?: string
  color: string
  points: number
  total_score: number
  wins: number
  losses: number
  squad_size: number
  fc: number
  rank: number
  [key: string]: unknown
}

/** Fixtures arrive as objects; arrays of two ids are tolerated as well. */
export interface AuctionTournamentFixture {
  a?: string
  b?: string
  round?: number | string
  label?: string
  played?: boolean
  result?: unknown
  [key: string]: unknown
}

export interface AuctionTournamentResult {
  type: 'lot' | 'match' | string
  winner_id?: string | null
  winner?: string | null | { id?: string; name?: string }
  price?: number
  winning_bid?: number
  amount?: number
  player_id?: string
  bids?: Record<string, unknown> | Array<unknown>
  rows?: Array<Record<string, unknown>>
  a?: string
  b?: string
  a_score?: number
  b_score?: number
  [key: string]: unknown
}

export interface AuctionTournamentPending {
  type: string
  [key: string]: unknown
}

export interface AuctionTournamentGameData {
  players: AuctionTournamentPlayer[]
  rules?: Record<string, unknown>
  [key: string]: unknown
}

export interface AuctionTournamentState {
  room_id?: string
  code: string
  host_id?: string
  ruleset?: number
  started: boolean
  finished: boolean
  phase: 'auction' | 'tournament' | 'over' | string
  turn: number
  lot_index: number
  /** Lot count, or the ordered lot list when the server sends full players. */
  lots: number | string[]
  budget: number
  current_lot: AuctionTournamentPlayer | null
  bids: Record<string, AuctionTournamentBid | null>
  last_result: AuctionTournamentResult | null
  pending: AuctionTournamentPending | null
  franchises: Record<string, AuctionTournamentFranchise>
  fixtures: AuctionTournamentFixture[] | unknown[]
  match_index: number
  match_results: Array<Record<string, unknown>>
  standings: AuctionTournamentStanding[]
  gamedata: AuctionTournamentGameData
  settings?: Record<string, unknown>
  you?: string
  winner_id?: string | null
  members?: LobbyMember[]
  log?: Array<Record<string, unknown>>
  events?: Array<Record<string, unknown>>
  [key: string]: unknown
}

export interface AuctionTournamentLobby {
  room_id?: string
  code: string
  host_id: string
  phase: 'lobby'
  started: false
  finished?: boolean
  ruleset?: number
  members: LobbyMember[]
  settings: Record<string, unknown>
  you?: string
  gamedata: AuctionTournamentGameData
  [key: string]: unknown
}
