import React, { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useApp } from '../store'
import { timeAgo } from '../utils'
import type {
  LobbyMember, PlayerData, StrategyContest, StrategyFranchise, StrategyGameData,
  StrategyLobby, StrategyLastContest, StrategyPending, StrategyPlan, StrategyShot,
  StrategyStanding, StrategyState, Tile,
} from '../types'
import { Badge, Button, Empty, Modal, Panel, Tabs } from './UI'

const AVATARS = ['🦁', '🦅', '🐯', '🐋', '🦘', '🦓', '🦉', '🐊']
const COLORS = ['#c8a24b', '#4fd1c5', '#f56565', '#68d391', '#b794f4', '#f6ad55', '#63b3ed', '#fc8181']
const LAP_OPTIONS = [2, 3, 4]
const PLAYER_OPTIONS = [2, 3, 4, 5, 6]
const UPGRADE_BASE = 60
const UPGRADE_STEP = 40
const MAX_LEVEL = 4

const SHOTS: Array<{ id: StrategyShot; label: string; icon: string; runs: string; risk: string }> = [
  { id: 'attack', label: 'ATTACK', icon: '⚡', runs: 'most runs', risk: 'high risk' },
  { id: 'steady', label: 'STEADY', icon: '⚖️', runs: 'balanced runs', risk: 'medium risk' },
  { id: 'defend', label: 'DEFEND', icon: '🛡️', runs: 'fewest runs', risk: 'safest' },
]

const PLANS: Array<{ id: StrategyPlan; label: string; icon: string; runs: string; risk: string }> = [
  { id: 'yorker', label: 'YORKER', icon: '🎯', runs: 'fewer runs', risk: 'more wickets' },
  { id: 'length', label: 'LENGTH', icon: '📏', runs: 'balanced runs', risk: 'balanced wickets' },
  { id: 'spin', label: 'SPIN', icon: '🌀', runs: 'more runs', risk: 'fewer wickets' },
]

const HELP_LINES = [
  'Roll and move around the 52-square board; buy any unowned square you land on with FC.',
  'Land on a rival’s player market to play a ball instead of paying fixed rent — you bat or bowl against the owner.',
  'Pick SHOT (ATTACK / STEADY / DEFEND) or PLAN (YORKER / LENGTH / SPIN). Choices stay hidden until both are locked.',
  'Your best signed batter’s BAT, the market star’s BOWL and your upgrades decide runs and wicket risk.',
  'A wicketkeeper contest makes you miss your next turn; your first ground is your home ground.',
  'Trade one square for one rival square. Own BAT, BOWL, WK and a ground to unlock upgrades. Most runs after 3 laps wins.',
]

const EVENT_ICONS: Record<string, string> = {
  roll: '🎲', buy: '🏟️', decline: '⏭️', auction: '🔨', sign: '🤝', charge: '💸',
  rent: '🏟️', upgrade: '⬆️', trade: '🔁', shot: '🏏', plan: '🎯', contest: '🏏',
  wicket: '🥵', lap: '🔄', skip: '⏭️', final: '🏆',
}

const num = (value: unknown): number => {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

const txt = (value: unknown): string => String(value ?? '').trim()

const shortName = (value?: string): string =>
  txt(value).replace(/^the\s+/i, '').split(/[·—–-]/)[0].trim() || '—'

const pad2 = (value: number): string => String(Math.max(0, Math.trunc(value))).padStart(2, '0')

const shortenText = (value: string): string => txt(value)
  .replace(/\s+/g, ' ')
  .replace(/^(season|round|turn)\s+\d+\s*[—–-]\s*/i, '')
  .slice(0, 120)

/** 52 squares around a 14×14 ring; corners live at 0, 13, 26 and 39. */
function tileCell(position: number): { gridRow: number; gridColumn: number } {
  const p = ((Math.trunc(position) % 52) + 52) % 52
  if (p <= 13) return { gridRow: 14, gridColumn: p + 1 }
  if (p <= 26) return { gridRow: 27 - p, gridColumn: 14 }
  if (p <= 39) return { gridRow: 1, gridColumn: 40 - p }
  return { gridRow: p - 38, gridColumn: 1 }
}

export function StrategyMonopolyScreen() {
  const { app, dispatch, send, setSession } = useApp()
  const state = app.state as unknown as StrategyState | null
  const lobby = state && !state.started ? state as unknown as StrategyLobby : null
  const [helpOpen, setHelpOpen] = useState(false)
  const [tradeOpen, setTradeOpen] = useState(false)
  const [tradeGive, setTradeGive] = useState('')
  const [tradeTarget, setTradeTarget] = useState('')
  const [tradeTake, setTradeTake] = useState('')

  const you = state?.you || app.session?.playerId || ''
  const gamedata = (state?.gamedata || app.gamedata) as unknown as StrategyGameData | undefined
  const countries: Record<string, { name?: string; flag?: string; color?: string; [key: string]: unknown }> =
    (gamedata?.countries || {}) as Record<string, { name?: string; flag?: string; color?: string; [key: string]: unknown }>

  const countryMeta = (country?: string) => {
    if (!country) return undefined
    const key = String(country)
    if (countries[key]) return countries[key]
    const lower = key.toLowerCase()
    return Object.entries(countries).find(([metaKey, meta]) =>
      metaKey.toLowerCase() === lower || txt(meta?.name).toLowerCase() === lower)?.[1]
  }

  const tileColor = (tile?: Tile): string => {
    if (!tile) return '#8f7439'
    if (tile.kind === 'corner') return '#f1cf7c'
    if (tile.kind === 'stadium') return '#52ecd0'
    if (tile.kind === 'event') return '#63b3ed'
    if (tile.country) return countryMeta(tile.country)?.color || '#b794f4'
    return '#d4af5f'
  }

  const rawTiles: Tile[] = state?.board?.length ? state.board : (app.gamedata?.board || [])
  const tiles = [...rawTiles].sort((a, b) => num(a.position) - num(b.position))
  const tileMap = new Map(tiles.map(tile => [String(tile.id), tile] as const))
  const tileByPosition = new Map(tiles.map(tile => [num(tile.position), tile] as const))
  const tileAt = (position: unknown): Tile | undefined => tileByPosition.get(num(position))
  // Properties use string ids (e.g. "india_batsman") while contests expose the
  // numeric board position. Accept both so the result card names the right tile.
  const findTile = (id: unknown): Tile | undefined => {
    const key = txt(id)
    if (!key) return undefined
    return tileMap.get(key) || (/^\d+$/.test(key) ? tileByPosition.get(Number(key)) : undefined)
  }
  const tileName = (id: unknown): string => {
    const tile = findTile(id)
    return tile?.name || (txt(id) ? `Square ${txt(id)}` : 'a square')
  }

  const propertyFor = (tile?: Tile) => tile ? state?.properties?.[String(tile.id)] : undefined
  const ownerFor = (tile?: Tile): StrategyFranchise | undefined => {
    const ownerId = propertyFor(tile)?.owner
    return ownerId ? state?.franchises?.[String(ownerId)] : undefined
  }
  const managerName = (pid?: string | number | null): string => {
    const manager = pid !== undefined && pid !== null && txt(pid) !== ''
      ? state?.franchises?.[String(pid)] : undefined
    return manager?.name || 'Manager'
  }
  const managerOf = (pid?: string | number | null): StrategyFranchise | undefined =>
    pid !== undefined && pid !== null && txt(pid) !== '' ? state?.franchises?.[String(pid)] : undefined

  const playerMap = new Map((gamedata?.players || [])
    .map(player => [String(player.id), player] as const))

  const myFranchise: StrategyFranchise | undefined = you ? state?.franchises?.[you] : undefined
  const managers: StrategyFranchise[] = (() => {
    const entries = Object.values(state?.franchises || {})
    if (!state?.order?.length) return entries
    const byId = new Map(entries.map(franchise => [String(franchise.id), franchise] as const))
    return state.order.map(id => byId.get(String(id))).filter((f): f is StrategyFranchise => Boolean(f))
  })()

  const standings: StrategyStanding[] = (() => {
    const rows = state?.standings?.length ? state.standings : managers.map((f, index) => ({
      id: f.id, name: f.name, avatar: f.avatar, color: f.color,
      runs: num(f.runs), fc: num(f.fc), wickets: num(f.wickets),
      laps: num(f.laps), rank: index + 1,
    }))
    return [...rows].sort((a, b) => num(a.rank) - num(b.rank))
  })()

  const currentFranchise = state?.current_player_id
    ? state.franchises?.[String(state.current_player_id)]
    : undefined
  const isMyTurn = Boolean(state?.started && !state.finished && state.phase !== 'over'
    && you && state.current_player_id === you)

  const pending: StrategyPending | null = state?.pending || null
  const contest: StrategyContest | null = state?.contest || null
  const lastContest: StrategyLastContest | null = state?.last_contest || null
  const rolled = Boolean(state?.rolled)

  const leaderLaps = managers.reduce((best, f) => Math.max(best, num(f.laps)), 0)
  const targetLaps = num(state?.settings?.laps ?? gamedata?.rules?.laps ?? state?.laps ?? 3) || 3
  const maxWickets = num(myFranchise?.max_wickets) > 0 ? num(myFranchise?.max_wickets) : 3

  const unlocked = Boolean(myFranchise?.unlocked)
  const homeGround = myFranchise?.home_ground !== undefined && myFranchise.home_ground !== null
    && txt(myFranchise.home_ground) !== '' ? String(myFranchise.home_ground) : ''
  const homeTile = homeGround ? findTile(homeGround) : undefined
  const myTile = tileAt(myFranchise?.pos)
  const myTileOwner = ownerFor(myTile)

  const propertiesOf = (pid: string) => Object.entries(state?.properties || {})
    .filter(([, property]) => Boolean(property?.owner) && String(property.owner) === String(pid))
    .map(([id, property]) => {
      const tile = tileMap.get(String(id))
      return { id, tile, name: tile?.name || String(id), price: num(property?.price ?? tile?.price) }
    })
    .sort((a, b) => a.name.localeCompare(b.name))

  const ownedTiles = propertiesOf(you).map(item => {
    const level = Math.min(MAX_LEVEL, num(state?.properties?.[String(item.id)]?.level))
    const cost = UPGRADE_BASE + level * UPGRADE_STEP
    return {
      tileId: item.id,
      tile: item.tile,
      level,
      cost,
      upgradeId: item.id,
      canUpgrade: isMyTurn && !pending && !contest && unlocked && level < MAX_LEVEL
        && num(myFranchise?.fc) >= cost,
    }
  })

  const rivals = managers.filter(manager => String(manager.id) !== String(you))
  const canTrade = isMyTurn && !rolled && !pending && !contest
    && ownedTiles.length > 0 && rivals.length > 0

  // A fresh result is shown briefly in the board centre and in the log. There
  // is deliberately no acknowledgement action; the next roll simply moves on.
  const resultKey = lastContest ? JSON.stringify(lastContest) : ''
  const [resultFlash, setResultFlash] = useState<StrategyLastContest | null>(null)
  // Seed with the current snapshot so a stale result from a reloaded room does
  // not replay as if it had just happened.
  const seenResult = useRef<string>(resultKey)
  useEffect(() => {
    if (!resultKey) {
      seenResult.current = ''
      setResultFlash(null)
      return
    }
    if (resultKey === seenResult.current) return
    seenResult.current = resultKey
    setResultFlash(lastContest)
    const timer = window.setTimeout(() => setResultFlash(null), 7000)
    return () => window.clearTimeout(timer)
  }, [resultKey, lastContest])

  const eventLog: Array<{ type: string; text: string }> = (() => {
    const source: unknown[] = [
      ...(Array.isArray(state?.log) ? state.log : []),
      ...(Array.isArray(state?.events) ? state.events : []),
      ...(app.events || []),
      ...(state?.last_event?.text ? [state.last_event] : []),
      ...(resultFlash?.text ? [{ type: 'contest', text: resultFlash.text }] : []),
    ]
    const seen = new Set<string>()
    return source
      .map(item => {
        const row = (item && typeof item === 'object' ? item : {}) as Record<string, unknown>
        return { type: txt(row.type || row.kind || 'update'), text: shortenText(txt(row.text)) }
      })
      .filter(entry => {
        if (!entry.text || seen.has(entry.text)) return false
        seen.add(entry.text)
        return true
      })
      .slice(-3)
      .reverse()
  })()

  /* Contest visibility: the holder only ever sees their own selection. */
  const iBat = Boolean(contest && you && String(contest.visitor) === String(you))
  const iBowl = Boolean(contest && you && String(contest.owner) === String(you))
  const myShot = txt(contest?.visitor_shot).toLowerCase()
  const myPlan = txt(contest?.owner_plan).toLowerCase()
  const batterLocked = Boolean(contest?.visitor_shot)
  const bowlerLocked = Boolean(contest?.owner_plan)
  const opponentText = iBat
    ? (bowlerLocked ? 'Bowler: choice locked' : 'Bowler: thinking…')
    : iBowl
      ? (batterLocked ? 'Batter: choice locked' : 'Batter: thinking…')
      : `Batter: ${batterLocked ? 'choice locked' : 'thinking…'} · Bowler: ${bowlerLocked ? 'choice locked' : 'thinking…'}`

  const pendingTile = pending?.tile_id !== undefined ? findTile(pending.tile_id) : undefined
  const pendingPlayer: PlayerData | undefined = typeof pending?.player_id === 'string'
    ? playerMap.get(String(pending.player_id))
    : undefined
  const pendingPrice = num(pending?.price ?? pendingTile?.price)
  const pendingName = pendingPlayer?.name || pendingTile?.name || 'this property'

  const pendingTrade = pending?.type === 'trade' ? pending : null
  const tradeForMe = Boolean(pendingTrade && String(pendingTrade.target) === String(you))
  const tradeByMe = Boolean(pendingTrade && String(pendingTrade.pid) === String(you))
  const tradeTargetName = managerName(pendingTrade?.target)
  const targetTiles = propertiesOf(tradeTarget)

  let prompt = 'Open the game to join a room'
  let hint = 'Create a room, join with a code, or jump into quick play.'
  if (!app.session) {
    prompt = 'Open the game to join a room'
  } else if (!state) {
    prompt = 'Connecting to the strategy league…'
    hint = 'Your franchise is loading from the room.'
  } else if (state.finished || state.phase === 'over') {
    prompt = 'League complete — see the final table'
    hint = 'Most runs after the laps takes the title.'
  } else if (!state.started || lobby) {
    prompt = 'Waiting for the host to start the league…'
    hint = 'Share the room code, add bots, then roll out.'
  } else if (tradeForMe) {
    prompt = `Trade offer from ${managerName(pendingTrade?.pid)}`
    hint = 'Accept or decline — you can answer between turns.'
  } else if (tradeByMe) {
    prompt = `Trade offer sent — waiting for ${tradeTargetName}`
    hint = 'Bots answer automatically.'
  } else if (contest) {
    if (iBat && !myShot) {
      prompt = 'Play the ball — pick your shot'
      hint = 'ATTACK for most runs, DEFEND for safety.'
    } else if (iBowl && !myPlan) {
      prompt = 'Play the ball — pick your bowling plan'
      hint = 'YORKER for wickets, SPIN to concede fewer runs.'
    } else if (iBat) {
      prompt = 'Shot locked — waiting for the bowler'
      hint = 'The owner’s plan stays hidden until both choices are in.'
    } else if (iBowl) {
      prompt = 'Plan locked — waiting for the batter'
      hint = 'The batter’s shot stays hidden until both choices are in.'
    } else {
      prompt = 'Play the ball — managers are choosing'
      hint = 'Both choices stay hidden until they are locked.'
    }
  } else if (pending?.type === 'buy') {
    prompt = `Buy ${pendingName} for ${pendingPrice} FC?`
    hint = 'Skip if you would rather save your FC.'
  } else if (pending?.type === 'auction') {
    prompt = `Player auction — sign ${pendingPlayer?.name || 'a cricketer'}?`
    hint = 'Signing adds a player to your squad and can add a wicket.'
  } else if (isMyTurn && rolled) {
    prompt = 'Rolled — resolving'
    hint = 'Charges and bonuses are being applied.'
  } else if (isMyTurn) {
    prompt = 'Your turn — roll the dice'
    hint = 'Upgrade or trade a square first, then roll.'
  } else if (currentFranchise) {
    prompt = `Waiting for ${currentFranchise.name}…`
    hint = currentFranchise.is_bot ? 'Bot turns resolve automatically.' : 'The dice pass around the board.'
  }

  const exit = () => {
    setSession(null)
    dispatch({ type: 'STATE', state: null })
    dispatch({ type: 'JOIN_CODE', code: null })
  }

  const openTrade = () => {
    const give = String(ownedTiles[0]?.tileId ?? '')
    const target = String(rivals[0]?.id ?? '')
    setTradeGive(give)
    setTradeTarget(target)
    setTradeTake(String(propertiesOf(target)[0]?.id ?? ''))
    setTradeOpen(true)
  }

  const selectTradeTarget = (pid: string) => {
    setTradeTarget(pid)
    setTradeTake(String(propertiesOf(pid)[0]?.id ?? ''))
  }

  const submitTrade = () => {
    if (!tradeGive || !tradeTarget || !tradeTake) return
    send('trade', {
      target: tradeTarget,
      give_tile: tradeGive,
      take_tile: tradeTake,
    })
    setTradeOpen(false)
  }

  return (
    <div className="app-shell strat-shell">
      <header className="topbar slim-header strat-header">
        <div className="brand">
          <span className="brand-mark">🏏</span>
          <span>
            <strong>CRICKET STRATEGY LEAGUE</strong>
            <small>CRICKOPOLY · RULES {num(state?.ruleset || 8)}</small>
          </span>
        </div>
        <div className="strat-header-meta">
          <Badge tone="gold" icon="#">{state?.code || app.session?.code || '—'}</Badge>
          <Badge tone="blue" icon="🔢">Turn {Math.max(1, num(state?.turn))}</Badge>
          <Badge icon="🔄">Laps {leaderLaps}/{targetLaps}</Badge>
          <Badge icon="🎲">{state?.dice?.length ? state.dice.join(' · ') : '—'}</Badge>
          <Badge tone="green" icon="💰">{num(myFranchise?.fc).toLocaleString()} FC</Badge>
          <Badge tone="gold" icon="🏏">{num(myFranchise?.runs)} runs</Badge>
          <Badge icon="🥵">{num(myFranchise?.wickets)}/{maxWickets} wkts</Badge>
        </div>
        <div className="top-actions">
          <span className={`conn ${app.connected ? 'online' : 'offline'}`}
            title={app.connected ? 'Live connection' : 'Reconnecting…'} />
          <Button variant="subtle" small onClick={() => setHelpOpen(true)}>? Help</Button>
          {app.session && <Button variant="subtle" small onClick={exit}>Exit</Button>}
        </div>
      </header>

      {myFranchise && (
        <section className="strat-whereami" aria-label="Where am I?">
          <div className="strat-where-location">
            <span className="strat-where-kicker">📍 WHERE AM I?</span>
            <strong><span className="strat-where-number">#{pad2(num(myFranchise.pos))}</span>{myTile?.name || 'Unknown square'}</strong>
            <small>{myTile?.country ? `${countryMeta(myTile.country)?.flag || ''} ${myTile.country}` : (myTile?.kind || 'square')}</small>
          </div>
          <div className="strat-where-owner" style={{ '--owner': myTileOwner?.color || '#8f7439' } as React.CSSProperties}>
            <span className="strat-where-avatar">{myTileOwner?.avatar || '🏦'}</span>
            <span className="strat-where-owner-copy">
              <small>OWNER</small>
              <b>{myTileOwner ? myTileOwner.name : 'Unowned / Bank'}</b>
            </span>
            {myTileOwner && <span className="strat-where-swatch" />}
          </div>
          <div className="strat-where-stats">
            <span><small>FC</small><b>{num(myFranchise.fc).toLocaleString()}</b></span>
            <span><small>RUNS</small><b>{num(myFranchise.runs)}</b></span>
            <span><small>WKTS</small><b>{num(myFranchise.wickets)}/{maxWickets}</b></span>
            <span><small>LAPS</small><b>{num(myFranchise.laps)}/{targetLaps}</b></span>
          </div>
        </section>
      )}

      <main className="strat-main">
        <section className="strat-board-wrap" aria-label="Cricket Strategy League board">
          <div className="strat-board">
            {tiles.map(tile => {
              const position = num(tile.position)
              const cell = tileCell(position)
              const property = propertyFor(tile)
              const owner = ownerFor(tile)
              const level = Math.min(MAX_LEVEL, num(property?.level))
              const price = num(property?.price ?? tile.price)
              const tokens = managers.filter(f => num(f.pos) === position)
              const isCurrent = Boolean(currentFranchise && num(currentFranchise.pos) === position)
              const isYou = Boolean(myFranchise && num(myFranchise.pos) === position)
              const isHome = Boolean(homeGround && String(tile.id) === homeGround)
              const style = {
                gridRow: cell.gridRow,
                gridColumn: cell.gridColumn,
                '--tile': tileColor(tile),
                '--owner': owner?.color || 'transparent',
              } as React.CSSProperties
              return (
                <div key={`${tile.id}-${position}`} style={style}
                  className={`strat-tile strat-kind-${tile.kind || 'event'} ${isCurrent ? 'is-current' : ''} ${isYou ? 'is-you' : ''} ${isHome ? 'is-home' : ''} ${owner ? 'is-owned' : ''} ${tokens.length > 0 ? 'has-tokens' : ''}`}
                  title={`#${position} ${tile.name || 'Tile'}${owner ? ` · ${owner.name}` : price > 0 ? ` · ${price} FC` : ''}${level ? ` · level ${level}` : ''}`}>
                  <span className="strat-tile-head">
                    <b className="strat-tile-icon">{tile.icon || '•'}</b>
                    <span className="strat-tile-name">{shortName(tile.short || tile.name)}</span>
                  </span>
                  {(tile.kind === 'market' || tile.kind === 'stadium') ? (
                    <span className="strat-pips strat-tile-pips" aria-label={`Level ${level}`}>
                      {[0, 1, 2, 3].map(index => <i key={index} className={index < level ? 'on' : ''} />)}
                    </span>
                  ) : <span className="strat-tile-gap" />}
                  {owner ? (
                    <span className="strat-tile-owner" style={{ '--owner': owner.color || '#c8a24b' } as React.CSSProperties}>
                      <b>{owner.avatar || '🏏'}</b>{shortName(owner.name)}
                    </span>
                  ) : price > 0 ? (
                    <span className="strat-tile-price">{price} FC</span>
                  ) : <span className="strat-tile-gap" />}
                  {tokens.length > 0 && (
                    <span className="strat-tile-tokens">
                      <span className="strat-token" title={tokens[0].name}
                        style={{ '--token': tokens[0].color || '#c8a24b' } as React.CSSProperties}>
                        {tokens[0].avatar || '🏏'}
                      </span>
                      {tokens.length > 1 && <span className="strat-token strat-token-count">+{tokens.length - 1}</span>}
                    </span>
                  )}
                </div>
              )
            })}

            <div className="strat-center">
              <div className="strat-center-mark">🏏</div>
              <h2>CRICKET STRATEGY LEAGUE</h2>
              <small>ROLL · BUY · PLAY THE BALL</small>
              <div className="strat-dice" aria-label={`Dice: ${(state?.dice || []).join(', ') || 'not rolled'}`}>
                {(state?.dice?.length ? state.dice : [null, null]).map((face, index) => (
                  <span key={index} className={face ? 'rolled' : ''}>{face ?? '·'}</span>
                ))}
              </div>

              {contest ? (
                <div className="strat-contest" aria-label="Play the ball">
                  <span className="strat-contest-kicker">⚡ PLAY THE BALL ⚡</span>
                  <strong className="strat-contest-tile">{tileName(contest.tile_id)}</strong>
                  <div className="strat-contest-sides">
                    <span style={{ '--team': managerOf(contest.visitor)?.color || '#c8a24b' } as React.CSSProperties}>
                      <b>{managerOf(contest.visitor)?.avatar || '🏏'} {managerName(contest.visitor)}</b>
                      <small>BATTER · BAT {num(contest.visitor_bat)}</small>
                    </span>
                    <em>vs</em>
                    <span style={{ '--team': managerOf(contest.owner)?.color || '#c8a24b' } as React.CSSProperties}>
                      <b>{managerOf(contest.owner)?.avatar || '🏏'} {managerName(contest.owner)}</b>
                      <small>BOWLER · BOWL {num(contest.owner_bowl)}</small>
                    </span>
                  </div>

                  {iBat && (
                    myShot ? (
                      <div className="strat-choice-locked">Shot locked — waiting for the bowler
                        <small>Your shot is hidden until both choices are in.</small>
                      </div>
                    ) : (
                      <div className="strat-choice-grid">
                        {SHOTS.map(shot => (
                          <button key={shot.id} type="button" className="strat-choice strat-choice-shot"
                            onClick={() => send('shot', { shot: shot.id })}>
                            <span>{shot.icon}</span><strong>{shot.label}</strong>
                            <small>{shot.runs}</small><em>{shot.risk}</em>
                          </button>
                        ))}
                      </div>
                    )
                  )}

                  {iBowl && (
                    myPlan ? (
                      <div className="strat-choice-locked">Plan locked — waiting for the batter
                        <small>Your plan is hidden until both choices are in.</small>
                      </div>
                    ) : (
                      <div className="strat-choice-grid">
                        {PLANS.map(plan => (
                          <button key={plan.id} type="button" className="strat-choice strat-choice-plan"
                            onClick={() => send('plan', { plan: plan.id })}>
                            <span>{plan.icon}</span><strong>{plan.label}</strong>
                            <small>{plan.runs}</small><em>{plan.risk}</em>
                          </button>
                        ))}
                      </div>
                    )
                  )}

                  {!iBat && !iBowl && (
                    <div className="strat-choice-locked">Managers are choosing…
                      <small>Your view stays hidden — no choice needed from you.</small>
                    </div>
                  )}
                  <span className="strat-contest-hidden">🔒 {opponentText}</span>
                </div>
              ) : resultFlash ? (
                <StrategyResultCard result={resultFlash} />
              ) : (
                <>
                  <div className="strat-center-lines">
                    <span><small>SEASON LAPS</small><b>{leaderLaps} / {targetLaps}</b></span>
                    <span><small>MANAGERS</small><b>{managers.length}</b></span>
                  </div>
                  <p className="strat-center-hint">Land on a rival’s player market to play a ball.</p>
                </>
              )}
              {contest && resultFlash && <StrategyResultCard result={resultFlash} compact />}
            </div>
          </div>
        </section>

        <aside className="strat-side">
          <Panel title="YOU" subtitle={myFranchise ? myFranchise.name : 'No franchise yet'} icon="⭐"
            className="strat-you-panel"
            action={isMyTurn ? <Badge tone="gold" icon="🎲">YOUR TURN</Badge> : <Badge>MANAGER</Badge>}>
            {myFranchise ? (
              <>
                <div className="strat-you-head" style={{ '--token': myFranchise.color } as React.CSSProperties}>
                  <span className="strat-you-avatar">{myFranchise.avatar || '🏏'}</span>
                  <div>
                    <strong>{myFranchise.name}</strong>
                    <small>{myFranchise.is_bot ? 'BOT' : 'MANAGER'} · POS {pad2(num(myFranchise.pos))}</small>
                  </div>
                </div>
                <div className="strat-you-stats">
                  <span><small>SQUAD</small><b>{Array.isArray(myFranchise.squad) ? myFranchise.squad.length : num(myFranchise.squad)}</b></span>
                  <span><small>WICKETS</small><b>{num(myFranchise.wickets)}/{maxWickets}</b></span>
                  <span><small>UPGRADES</small><b>{unlocked ? 'OPEN' : 'LOCKED'}</b></span>
                </div>
                <div className="strat-wickets" aria-label={`${num(myFranchise.wickets)} wickets remaining`}>
                  {Array.from({ length: Math.min(6, maxWickets) }, (_, index) => (
                    <span key={index} className={index < num(myFranchise.wickets) ? 'alive' : ''}>🏏</span>
                  ))}
                </div>
                <div className="strat-you-flags">
                  <Badge tone={unlocked ? 'green' : 'default'}>{unlocked ? 'FULL SET OWNED' : 'FULL SET NEEDED'}</Badge>
                  {homeGround && <Badge tone="gold">★ {shortName(homeTile?.name)}</Badge>}
                </div>
                {Boolean(myFranchise.skipped) && !myFranchise.injured && (
                  <p className="strat-status-line">⏭️ Wicketkeeper charge — next turn skipped.</p>
                )}
                {Boolean(myFranchise.injured) && (
                  <p className="strat-status-line">🚑 Injury reserve — out for two turns.</p>
                )}
                {myFranchise.out && <p className="strat-status-line danger">⛔ All out — waiting for the league to end.</p>}
              </>
            ) : <Empty title="No franchise yet" text="Join a room to take your seat on the board." />}
          </Panel>

          <Panel title="Your properties"
            subtitle={unlocked ? `${ownedTiles.length} owned · upgrade before rolling` : `${ownedTiles.length} owned · upgrades locked`}
            icon="🏟️" className="strat-owned-panel">
            {!unlocked && (
              <p className="strat-upgrade-lock">Upgrade locked: own a batsman, bowler, wicketkeeper and a ground.</p>
            )}
            {unlocked && homeGround && (
              <p className="strat-home-note">HOME GROUND: +50% FC rent · +100 FC &amp; +50 runs when you land on it</p>
            )}
            <div className="strat-owned-list">
              {ownedTiles.length === 0 ? (
                <Empty title="Nothing owned yet" text="Buy a ground or player square when you land on it." />
              ) : ownedTiles.map(item => (
                <div key={item.tileId} className="strat-owned-row">
                  <span className="strat-owned-icon" style={{ '--tile': tileColor(item.tile) } as React.CSSProperties}>
                    {item.tile?.icon || '•'}
                  </span>
                  <div className="strat-owned-info">
                    <strong>
                      {item.tile?.name || String(item.tileId)}
                      {homeGround && String(item.tileId) === homeGround && <em className="strat-home-tag">HOME</em>}
                    </strong>
                    <small>
                      {countryMeta(item.tile?.country)?.flag} {item.tile?.country || item.tile?.kind || 'property'}
                      {item.tile?.role ? ` · ${item.tile.role}` : ''}
                    </small>
                    <span className="strat-pips">
                      {[0, 1, 2, 3].map(index => <i key={index} className={index < item.level ? 'on' : ''} />)}
                    </span>
                  </div>
                  <Button small variant="subtle" disabled={!item.canUpgrade}
                    title={!unlocked ? 'Upgrade locked until you own BAT + BOWL + WK + a ground'
                      : item.level >= MAX_LEVEL ? 'Maximum upgrade reached'
                        : `Upgrade for ${item.cost} FC`}
                    onClick={() => send('upgrade', { tile_id: item.upgradeId })}>
                    {item.level >= MAX_LEVEL ? 'MAX' : `↑ ${item.cost}`}
                  </Button>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Standings" subtitle="Most runs wins the league" icon="🏆" className="strat-standings-panel">
            <div className="strat-table-scroll">
              <table className="data-table strat-standings-table">
                <thead><tr><th>#</th><th>Manager</th><th>Square</th><th>Runs</th><th>FC</th><th>Wk</th><th>Lap</th></tr></thead>
                <tbody>
                  {standings.map(row => {
                    const manager = state?.franchises?.[String(row.id)]
                    const position = num(manager?.pos ?? row.pos)
                    const square = tileAt(position)
                    return (
                      <tr key={row.id} className={String(row.id) === String(you) ? 'is-me' : ''}>
                        <td><span className={`rank ${num(row.rank) === 1 ? 'rank-1' : ''}`}>{num(row.rank)}</span></td>
                        <td><span className="team-color" style={{ background: row.color }} />{row.name}</td>
                        <td className="strat-square-cell"><b>#{pad2(position)}</b><small>{shortName(square?.short || square?.name)}</small></td>
                        <td><b>{num(row.runs)}</b></td>
                        <td>{num(row.fc)}</td>
                        <td>{num(row.wickets)}</td>
                        <td>{num(row.laps)}</td>
                      </tr>
                    )
                  })}
                  {standings.length === 0 && (
                    <tr><td colSpan={7}><Empty title="No standings yet" /></td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title="Event log" subtitle="Latest three updates" icon="📢" className="strat-log-panel">
            <div className="strat-log-list">
              {eventLog.length === 0 ? (
                <Empty title="No events yet" text="Rolls, contests and trades appear here." />
              ) : eventLog.map((event, index) => (
                <div key={`${event.text}-${index}`} className="strat-log-row">
                  <span className="strat-log-dot" title={event.type}>{EVENT_ICONS[event.type] || '•'}</span>
                  <p>{event.text}</p>
                </div>
              ))}
            </div>
          </Panel>
        </aside>
      </main>

      <div className="strat-actionbar">
        <div className="strat-action-copy">
          <strong>{prompt}</strong>
          <small>{hint}</small>
        </div>
        <div className="strat-action-buttons">
          {app.session && state && !state.finished && state.phase !== 'over' && (
            contest ? (
              <span className="strat-action-status">PLAY THE BALL — CHOOSE ABOVE</span>
            ) : pendingTrade ? (
              tradeForMe ? (
                <span className="strat-action-status">Trade offer — choose below</span>
              ) : (
                <span className="strat-action-status">Trade offer sent — waiting for {tradeTargetName}</span>
              )
            ) : pending?.type === 'buy' ? (
              <>
                <Button variant="gold" className="strat-action-primary"
                  onClick={() => send('buy', {})}>BUY · {pendingPrice} FC</Button>
                <Button variant="subtle" className="strat-action-secondary"
                  onClick={() => send('decline', {})}>SKIP</Button>
              </>
            ) : pending?.type === 'auction' ? (
              <>
                <Button variant="gold" className="strat-action-primary"
                  onClick={() => send('auction_buy', {})}>SIGN PLAYER · +1 WICKET</Button>
                <Button variant="subtle" className="strat-action-secondary"
                  onClick={() => send('auction_skip', {})}>SKIP</Button>
              </>
            ) : isMyTurn && !rolled ? (
              <>
                <Button variant="gold" className="strat-action-primary"
                  onClick={() => send('roll', {})}>🎲 ROLL DICE</Button>
                {canTrade && (
                  <Button variant="subtle" className="strat-action-trade" onClick={openTrade}>🔁 TRADE</Button>
                )}
              </>
            ) : (
              <span className="strat-action-status">
                {isMyTurn ? 'RESOLVING…' : currentFranchise?.is_bot ? 'BOT PLAYING…' : 'WAITING…'}
              </span>
            )
          )}
          {(!app.session || !state || state.finished || state.phase === 'over') && (
            <span className="strat-action-status">{state?.finished || state?.phase === 'over' ? 'FINISHED' : 'STANDBY'}</span>
          )}
        </div>
      </div>

      {helpOpen && <StrategyHelpModal onClose={() => setHelpOpen(false)} />}
      {tradeOpen && state && !state.finished && state.phase !== 'over' && (
        <Modal title="Trade a square" subtitle="Swap one property for one rival’s — no money"
          width="540px" onClose={() => setTradeOpen(false)}>
          <div className="strat-trade-form">
            <p className="strat-trade-note">Swap one property for one property — no money changes hands.</p>
            <label className="field">
              <span>1 · Your square to give</span>
              <select value={tradeGive} onChange={e => setTradeGive(e.target.value)}>
                {ownedTiles.map(item => (
                  <option key={item.tileId} value={item.tileId}>{item.tile?.name || String(item.tileId)}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>2 · Rival manager</span>
              <select value={tradeTarget} onChange={e => selectTradeTarget(e.target.value)}>
                {rivals.map(manager => (
                  <option key={manager.id} value={manager.id}>
                    {manager.avatar || '🏏'} {manager.name}{manager.is_bot ? ' (bot)' : ''}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>3 · Their square to receive</span>
              <select value={tradeTake} onChange={e => setTradeTake(e.target.value)} disabled={!targetTiles.length}>
                {targetTiles.length === 0 ? <option value="">Rival owns no squares</option> : targetTiles.map(item => (
                  <option key={item.id} value={item.id}>{item.name}</option>
                ))}
              </select>
            </label>
            <div className="strat-trade-summary">
              <span className="strat-trade-card"><small>YOU GIVE</small><b>{tileName(tradeGive)}</b></span>
              <span className="strat-trade-arrow">⇄</span>
              <span className="strat-trade-card rival"><small>YOU GET</small><b>{tileName(tradeTake)}</b></span>
            </div>
            <div className="strat-trade-actions">
              <Button variant="subtle" onClick={() => setTradeOpen(false)}>Cancel</Button>
              <Button variant="gold" disabled={!tradeGive || !tradeTarget || !tradeTake || !targetTiles.length}
                onClick={submitTrade}>Send offer</Button>
            </div>
          </div>
        </Modal>
      )}
      {tradeForMe && pendingTrade && state && !state.finished && state.phase !== 'over' && (
        <Modal title="Trade offer for you" subtitle="Answer any time — it is not tied to your turn"
          width="520px" onClose={() => send('decline_trade', {})}>
          <div className="strat-offer">
            <div className="strat-offer-head" style={{ '--token': managerOf(pendingTrade.pid)?.color || '#c8a24b' } as React.CSSProperties}>
              <span className="strat-offer-avatar">{managerOf(pendingTrade.pid)?.avatar || '🏏'}</span>
              <div><strong>{managerName(pendingTrade.pid)} proposes a swap</strong><small>No money — one square each.</small></div>
            </div>
            <p className="strat-offer-line">
              {managerName(pendingTrade.pid)} offers <b>{tileName(pendingTrade.give_tile)}</b> for your{' '}
              <b>{tileName(pendingTrade.take_tile)}</b>.
            </p>
            <div className="strat-trade-summary">
              <span className="strat-trade-card rival"><small>THEY GIVE</small><b>{tileName(pendingTrade.give_tile)}</b></span>
              <span className="strat-trade-arrow">⇄</span>
              <span className="strat-trade-card"><small>YOU GIVE</small><b>{tileName(pendingTrade.take_tile)}</b></span>
            </div>
            <div className="strat-trade-actions">
              <Button variant="subtle" onClick={() => send('decline_trade', {})}>DECLINE</Button>
              <Button variant="success" onClick={() => send('accept_trade', {})}>ACCEPT</Button>
            </div>
          </div>
        </Modal>
      )}
      {!app.session && <StrategyLandingModal />}
      {app.session && !state && (
        <Modal title="Cricket Strategy League" subtitle="Loading your league…" onClose={() => {}}>
          <Empty title="Connecting to the room" text="The 52-square board appears as soon as the lobby loads." />
        </Modal>
      )}
      {app.session && lobby && <StrategyLobbyModal lobby={lobby} />}
      {app.session && state && (state.finished || state.phase === 'over') && (
        <StrategyFinishModal state={state} standings={standings}
          canRestart={app.session.playerId === state.host_id}
          onRestart={() => send('restart', {})} />
      )}
    </div>
  )
}

/* -------------------------------------------------------------------------- */
 /* Contest result                                                             */
 /* -------------------------------------------------------------------------- */

function StrategyResultCard({ result, compact = false }: { result: StrategyLastContest; compact?: boolean }) {
  const totalRuns = num(result.runs) + num(result.extra_runs)
  const wicket = Boolean(result.wicket)
  const skip = Boolean(result.skip)
  return (
    <div className={`strat-result ${compact ? 'is-compact' : ''} ${wicket ? 'is-wicket' : ''}`}
      role="status" aria-live="polite">
      <span className="strat-result-kicker">BALL RESULT</span>
      <strong className="strat-result-runs">+{totalRuns} runs</strong>
      <div className="strat-result-flags">
        {wicket && <b className="strat-flag-wicket">WICKET!</b>}
        {skip && <b className="strat-flag-skip">miss next turn</b>}
      </div>
      {num(result.extra_runs) > 0 && <small>including +{num(result.extra_runs)} extra runs</small>}
      {txt(result.text) && <p>{txt(result.text)}</p>}
    </div>
  )
}

/* -------------------------------------------------------------------------- */
 /* Help                                                                       */
 /* -------------------------------------------------------------------------- */

function StrategyHelpModal({ onClose }: { onClose: () => void }) {
  return (
    <Modal title="How to play" subtitle="Cricket Strategy League in six lines" width="680px" onClose={onClose}>
      <ol className="strat-help-list">
        {HELP_LINES.map(line => <li key={line}>{line}</li>)}
      </ol>
      <div className="strat-help-foot">
        <small>Virtual FC and runs only. No deposits, wagering, photos, logos or league branding — player names are factual data.</small>
      </div>
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */
 /* Landing                                                                    */
 /* -------------------------------------------------------------------------- */

function StrategyLandingModal() {
  const { app, create, join, quick, continueRoom, dispatch, refreshSaved, joinCode } = useApp()
  const [tab, setTab] = useState<'new' | 'join' | 'quick'>(() => joinCode ? 'join' : 'new')
  const [name, setName] = useState(() => localStorage.getItem('fg-name') || 'Manager')
  const [avatar, setAvatar] = useState(() => localStorage.getItem('fg-avatar') || '🦁')
  const [color, setColor] = useState(() => localStorage.getItem('fg-color') || '#c8a24b')
  const [code, setCode] = useState(() => joinCode || '')
  const [laps, setLaps] = useState(3)
  const [maxPlayers, setMaxPlayers] = useState(4)
  const [difficulty, setDifficulty] = useState('medium')

  const profile = { name: name.trim() || 'Manager', avatar, color }
  const settings = {
    ruleset: 8,
    game: 'cricket-strategy-league',
    laps,
    max_players: maxPlayers,
    difficulty,
    ai_difficulty: difficulty,
  }
  const saveProfile = () => {
    localStorage.setItem('fg-name', profile.name)
    localStorage.setItem('fg-avatar', avatar)
    localStorage.setItem('fg-color', color)
  }
  const switchTab = (next: string) => {
    setTab(next as 'new' | 'join' | 'quick')
    if (joinCode) dispatch({ type: 'JOIN_CODE', code: null })
  }

  return (
    <Modal title="Cricket Strategy League" subtitle="Buy squares. Play the ball. Score the most runs." width="940px"
      onClose={() => {}}>
      <div className="strat-landing-grid">
        <Panel title="Start or join" subtitle="New room, room code, or instant match" icon="🚀">
          <div className="profile-row">
            <div className="avatar-picker">
              {AVATARS.map(option => (
                <button key={option} type="button" className={avatar === option ? 'active' : ''}
                  onClick={() => setAvatar(option)}>{option}</button>
              ))}
            </div>
            <div className="color-picker">
              {COLORS.map(option => (
                <button key={option} type="button" style={{ background: option }}
                  className={color === option ? 'active' : ''}
                  onClick={() => setColor(option)} aria-label={`Colour ${option}`} />
              ))}
            </div>
          </div>
          <label className="field">
            <span>Manager name</span>
            <input value={name} maxLength={24} onChange={e => setName(e.target.value)}
              placeholder="Your manager name" />
          </label>
          <Tabs active={tab} onChange={switchTab} tabs={[
            { id: 'new', label: 'New room' },
            { id: 'join', label: 'Join code' },
            { id: 'quick', label: 'Quick play' },
          ]} />

          {tab === 'new' && (
            <div className="settings-grid strat-landing-settings">
              <label className="field"><span>Season laps</span>
                <select value={laps} onChange={e => setLaps(Number(e.target.value))}>
                  {LAP_OPTIONS.map(option => <option key={option} value={option}>{option} laps</option>)}
                </select>
              </label>
              <label className="field"><span>Max players</span>
                <select value={maxPlayers} onChange={e => setMaxPlayers(Number(e.target.value))}>
                  {PLAYER_OPTIONS.map(option => <option key={option} value={option}>{option} managers</option>)}
                </select>
              </label>
              <label className="field"><span>AI difficulty</span>
                <select value={difficulty} onChange={e => setDifficulty(e.target.value)}>
                  <option value="easy">Easy</option>
                  <option value="medium">Medium</option>
                  <option value="hard">Hard</option>
                </select>
              </label>
            </div>
          )}

          {tab === 'join' && (
            <>
              {joinCode && (
                <div className="callout">
                  <strong>Invite code: {joinCode}</strong>
                  <p>Enter your manager name and join with this code. Code-only invites — no links or logins.</p>
                </div>
              )}
              <label className="field">
                <span>Room code</span>
                <input className="code-input" value={code} maxLength={8} placeholder="ABCDE"
                  onChange={e => setCode(e.target.value.toUpperCase())} />
              </label>
            </>
          )}

          {tab === 'quick' && (
            <div className="callout">
              <strong>Instant league</strong>
              <p>Three managers, {laps} laps and two bot rivals. Straight to the board, no lobby wait.</p>
            </div>
          )}

          <div className="button-row">
            {tab === 'new' && <Button onClick={() => { saveProfile(); create({ ...profile, settings }) }}
              disabled={app.busy}>Create room →</Button>}
            {tab === 'join' && <Button onClick={() => {
              saveProfile()
              join(code.trim().toUpperCase(), profile.name, avatar, color)
              dispatch({ type: 'JOIN_CODE', code: null })
            }} disabled={app.busy || code.trim().length < 4}>Join room →</Button>}
            {tab === 'quick' && <Button onClick={() => {
              saveProfile()
              quick({ ...profile, settings: { ...settings, max_players: 3 } })
            }} disabled={app.busy}>Start quick play →</Button>}
          </div>
        </Panel>

        <Panel title="Continue a saved league" subtitle="Progress is saved on the server" icon="💾"
          action={<Button variant="subtle" small onClick={refreshSaved}>Refresh</Button>}>
          {app.saved.length === 0 ? (
            <div className="empty"><span>💾</span><strong>No saved leagues yet</strong>
              <p>Create a room and it will appear here.</p></div>
          ) : (
            <div className="saved-list">
              {app.saved.slice(0, 8).map(row => (
                <button key={row.room_id} type="button" className="saved-row" onClick={() => continueRoom(row)}>
                  <span className="saved-icon">{row.finished ? '🏆' : '🏏'}</span>
                  <span className="saved-info">
                    <strong>{row.winner_name || row.franchises.join(' vs ') || row.code}</strong>
                    <small>{row.code} · Turn {num(row.round)} · {row.franchises.length} managers</small>
                  </span>
                  <span className="saved-time">{timeAgo(row.updated_at)}</span>
                </button>
              ))}
            </div>
          )}
        </Panel>
      </div>
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */
 /* Lobby                                                                      */
 /* -------------------------------------------------------------------------- */

function StrategyLobbyModal({ lobby }: { lobby: StrategyLobby }) {
  const { app, dispatch } = useApp()
  const [count, setCount] = useState(2)
  const [copied, setCopied] = useState(false)
  const members: LobbyMember[] = Array.isArray(lobby.members)
    ? lobby.members
    : Object.values((lobby.members || {}) as unknown as Record<string, LobbyMember>)
  const isHost = lobby.host_id === app.session?.playerId
    || members.some(member => member.is_host && member.id === app.session?.playerId)
  const maxPlayers = num(lobby.settings?.max_players) || 4
  const laps = num(lobby.settings?.laps) || 3
  const difficulty = txt(lobby.settings?.difficulty || lobby.settings?.ai_difficulty || 'medium')
  const settings = {
    ruleset: 8,
    game: 'cricket-strategy-league',
    laps,
    max_players: maxPlayers,
    difficulty,
    ai_difficulty: difficulty,
  }

  const run = async (call: () => Promise<unknown>) => {
    if (!app.session) return
    dispatch({ type: 'BUSY', busy: true })
    try {
      const next = await call()
      if (next && typeof next === 'object') dispatch({ type: 'STATE', state: next as any })
    } catch (error: any) {
      dispatch({ type: 'ERROR', error: error?.message || 'Lobby update failed' })
    } finally {
      dispatch({ type: 'BUSY', busy: false })
    }
  }
  const patch = (next: Record<string, unknown>) =>
    run(() => api.updateSettings(lobby.code, app.session!.playerId, { ...settings, ...next }))
  const copyCode = () => {
    navigator.clipboard?.writeText(lobby.code).then(() => {
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    }).catch(() => dispatch({ type: 'ERROR', error: `Room code: ${lobby.code}` }))
  }

  return (
    <Modal title="Strategy League lobby" subtitle="Invite managers, add bots, then start the league"
      width="900px" onClose={() => {}}>
      <div className="strat-lobby-grid">
        <Panel title="Managers" subtitle={`${members.length}/${maxPlayers} seats filled`} icon="🏏">
          <div className="strat-code-display">
            <small>ROOM CODE</small>
            <strong>{lobby.code}</strong>
            <span>Share the code only — no links or logins needed.</span>
            <Button variant="subtle" small onClick={copyCode}>{copied ? '✓ Copied code' : 'Copy code'}</Button>
          </div>
          <div className="member-list">
            {members.map(member => (
              <div key={member.id} className="member-row">
                <span className="strat-lobby-avatar"
                  style={{ '--token': member.color || '#c8a24b' } as React.CSSProperties}>
                  {member.avatar || '🏏'}
                </span>
                <div className="member-name"><strong>{member.name}</strong>
                  <small>{member.is_bot ? `${member.difficulty || difficulty} AI manager` : 'Human manager'}</small></div>
                {member.is_host && <Badge tone="gold">HOST</Badge>}
                {member.is_bot && <Badge tone="blue">BOT</Badge>}
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Host settings" subtitle={isHost ? 'Only the host can edit these' : 'Waiting for the host'} icon="⚙️">
          <div className="two-col">
            <label className="field"><span>Season laps</span>
              <select disabled={!isHost || app.busy} value={laps}
                onChange={e => patch({ laps: Number(e.target.value) })}>
                {LAP_OPTIONS.map(option => <option key={option} value={option}>{option} laps</option>)}
              </select>
            </label>
            <label className="field"><span>Max players</span>
              <select disabled={!isHost || app.busy} value={maxPlayers}
                onChange={e => patch({ max_players: Number(e.target.value) })}>
                {PLAYER_OPTIONS.map(option => <option key={option} value={option}>{option} managers</option>)}
              </select>
            </label>
          </div>
          <label className="field"><span>AI difficulty</span>
            <select disabled={!isHost || app.busy} value={difficulty}
              onChange={e => patch({ difficulty: e.target.value, ai_difficulty: e.target.value })}>
              <option value="easy">Easy</option>
              <option value="medium">Medium</option>
              <option value="hard">Hard</option>
            </select>
          </label>
          <div className="bot-setup">
            <label className="field"><span>How many bots?</span>
              <input type="number" min={1} max={Math.max(1, maxPlayers - members.length)} value={count}
                onChange={e => setCount(Math.max(1, Math.min(maxPlayers, num(e.target.value))))} />
            </label>
            <Button variant="subtle" block disabled={!isHost || app.busy || members.length >= maxPlayers}
              onClick={() => run(() => api.addBots(lobby.code, app.session!.playerId, count, difficulty))}>
              ＋ Add bots
            </Button>
          </div>
          {isHost && (
            <div className="start-block">
              {members.length < 2 && <small>Add at least one more manager or bot.</small>}
              <Button variant="gold" block disabled={app.busy || members.length < 2}
                onClick={() => run(() => api.startRoom(lobby.code, app.session!.playerId))}>
                🏏 Start league
              </Button>
            </div>
          )}
        </Panel>
      </div>
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */
 /* Finish                                                                     */
 /* -------------------------------------------------------------------------- */

function StrategyFinishModal({ state, standings, canRestart, onRestart }: {
  state: StrategyState
  standings: StrategyStanding[]
  canRestart: boolean
  onRestart: () => void
}) {
  const championId = state.winner_id || standings[0]?.id
  const champion = standings.find(row => String(row.id) === String(championId))
    || (championId ? state.franchises?.[String(championId)] : undefined)
  const championName = champion?.name || 'Champion'
  const championRuns = num(champion?.runs)
  const championLaps = num(champion?.laps)

  return (
    <Modal title="League complete" subtitle="The manager with the most runs takes the title"
      width="760px" onClose={() => {}}>
      <div className="strat-champion">
        <span>🏆</span>
        <small>CHAMPION</small>
        <h2>{championName}</h2>
        <p>{championRuns} runs · {championLaps} laps · most runs after the full league</p>
      </div>
      <div className="strat-table-scroll">
        <table className="data-table strat-result-table">
          <thead><tr><th>#</th><th>Manager</th><th>Runs</th><th>FC</th><th>Wkts</th><th>Laps</th></tr></thead>
          <tbody>
            {standings.map(row => (
              <tr key={row.id} className={String(row.id) === String(championId) ? 'champion' : ''}>
                <td><span className={`rank ${num(row.rank) === 1 ? 'rank-1' : ''}`}>{num(row.rank)}</span></td>
                <td><span className="team-color" style={{ background: row.color }} />{row.name}</td>
                <td><b>{num(row.runs)}</b></td>
                <td>{num(row.fc)}</td>
                <td>{num(row.wickets)}</td>
                <td>{num(row.laps)}</td>
              </tr>
            ))}
            {standings.length === 0 && (
              <tr><td colSpan={6}><Empty title="No final table" text="Standings arrive with the final snapshot." /></td></tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="strat-modal-foot">
        <small>{canRestart ? 'Play again starts a fresh league for every manager.'
          : 'Only the host can start a new league.'}</small>
        <Button variant="gold" onClick={onRestart} disabled={!canRestart}>Play again</Button>
      </div>
    </Modal>
  )
}
