import React, { useState } from 'react'
import { useApp } from '../store'
import type {
  LobbyMember, MonopolyCountryMeta, MonopolyFranchise, MonopolyLobby,
  MonopolyPending, MonopolyStanding, MonopolyState, PlayerData, Tile,
} from '../types'
import { timeAgo } from '../utils'
import { Badge, Button, Empty, Modal, Panel, Tabs } from './UI'

const AVATARS = ['🦁', '🦅', '🐯', '🐋', '🦘', '🦓', '🦉', '🐊']
const COLORS = ['#c8a24b', '#4fd1c5', '#f56565', '#68d391', '#b794f4', '#f6ad55', '#63b3ed', '#fc8181']
const LAP_OPTIONS = [2, 3, 4]
const PLAYER_OPTIONS = [2, 3, 4, 5, 6]
const UPGRADE_BASE = 60
const UPGRADE_STEP = 40
const MAX_LEVEL = 4

const EVENT_ICONS: Record<string, string> = {
  roll: '🎲', buy: '🏟️', decline: '⏭️', auction: '🔨', sign: '🤝',
  charge: '💸', rent: '🏟️', upgrade: '⬆️', injury: '🚑', trade: '🔁',
  lap: '🔄', skip: '⏭️', final: '🏆',
}

const num = (value: unknown): number => {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

const collectionSize = (value: unknown): number =>
  Array.isArray(value) ? value.length : num(value)

const shortName = (value?: string): string =>
  String(value || '').replace(/^the\s+/i, '').split(/[·—–-]/)[0].trim() || '—'

const pad2 = (value: number): string => String(Math.max(0, Math.trunc(value))).padStart(2, '0')

const tileIdValue = (value: number | string): number | string => {
  const raw = String(value)
  return /^\d+$/.test(raw) ? Number(raw) : raw
}

const shortenText = (value: string): string => String(value || '')
  .replace(/\s+/g, ' ')
  .replace(/^(season|round|turn)\s+\d+\s*[—–-]\s*/i, '')
  .trim()
  .slice(0, 108)

/** 52 squares around a 14×14 ring: corners live at 0, 13, 26 and 39. */
function tileCell(position: number): { gridRow: number; gridColumn: number } {
  const p = ((Math.trunc(position) % 52) + 52) % 52
  if (p <= 13) return { gridRow: 14, gridColumn: p + 1 }
  if (p <= 26) return { gridRow: 27 - p, gridColumn: 14 }
  if (p <= 39) return { gridRow: 1, gridColumn: 40 - p }
  return { gridRow: p - 38, gridColumn: 1 }
}

export function MonopolyScreen() {
  const { app, dispatch, send, setSession } = useApp()
  const state = app.state as unknown as MonopolyState | null
  const lobby = state && !state.started ? state as unknown as MonopolyLobby : null
  const [helpOpen, setHelpOpen] = useState(false)
  const [tradeOpen, setTradeOpen] = useState(false)
  const [tradeGive, setTradeGive] = useState('')
  const [tradeTarget, setTradeTarget] = useState('')
  const [tradeTake, setTradeTake] = useState('')

  const you = state?.you || app.session?.playerId || ''
  const gamedata = state?.gamedata
  const countries: Record<string, MonopolyCountryMeta> = (gamedata?.countries
    || (app.gamedata?.countries as unknown as Record<string, MonopolyCountryMeta>)
    || {})

  const countryMeta = (country?: string): MonopolyCountryMeta | undefined => {
    if (!country) return undefined
    const key = String(country)
    if (countries[key]) return countries[key]
    const lower = key.toLowerCase()
    const found = Object.entries(countries).find(([metaKey, meta]) =>
      metaKey.toLowerCase() === lower || String(meta?.name || '').toLowerCase() === lower)
    return found?.[1]
  }

  const tileColor = (tile?: Tile): string => {
    if (!tile) return '#8f7439'
    if (tile.kind === 'corner') return '#d4af5f'
    if (tile.kind === 'stadium') return '#2bb686'
    if (tile.kind === 'event') return '#63b3ed'
    if (tile.country) return countryMeta(tile.country)?.color || '#b794f4'
    return '#d4af5f'
  }

  const rawTiles: Tile[] = state?.board?.length ? state.board : (app.gamedata?.board || [])
  const tiles = [...rawTiles].sort((a, b) => num(a.position) - num(b.position))
  const tileMap = new Map(tiles.map(tile => [String(tile.id), tile] as const))
  const tileByPosition = new Map(tiles.map(tile => [num(tile.position), tile] as const))
  const tileAt = (position: unknown): Tile | undefined => tileByPosition.get(num(position))
  const tileName = (id: unknown): string => {
    const tile = tileMap.get(String(id ?? ''))
    return tile?.name || (id !== undefined && id !== null && String(id) !== '' ? `Square ${id}` : 'a square')
  }

  const propertyFor = (tile?: Tile) => tile ? state?.properties?.[String(tile.id)] : undefined
  const ownerFor = (tile?: Tile): MonopolyFranchise | undefined => {
    const ownerId = propertyFor(tile)?.owner
    return ownerId ? state?.franchises?.[String(ownerId)] : undefined
  }
  const managerName = (pid?: string | number | null): string => {
    const manager = pid !== undefined && pid !== null && String(pid) !== ''
      ? state?.franchises?.[String(pid)] : undefined
    return manager?.name || 'Manager'
  }

  const playerMap = new Map((gamedata?.players || app.gamedata?.players || [])
    .map(player => [String(player.id), player] as const))

  const myFranchise: MonopolyFranchise | undefined = you ? state?.franchises?.[you] : undefined
  const managers = (() => {
    const entries = Object.values(state?.franchises || {})
    if (!state?.order?.length) return entries
    const byId = new Map(entries.map(franchise => [String(franchise.id), franchise] as const))
    return state.order.map(id => byId.get(String(id))).filter((f): f is MonopolyFranchise => Boolean(f))
  })()

  const standings: MonopolyStanding[] = (() => {
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
  const pending: MonopolyPending | null = state?.pending || null
  const rolled = Boolean(state?.rolled)
  const rules = (gamedata?.rules || {}) as Record<string, unknown>
  const configuredLaps = num(state?.settings?.laps ?? rules.laps ?? state?.laps ?? 3)
  const targetLaps = configuredLaps > 0 ? configuredLaps : 3
  const leaderLaps = managers.reduce((best, f) => Math.max(best, num(f.laps)), 0)
  const maxWickets = num(myFranchise?.max_wickets) > 0 ? num(myFranchise?.max_wickets) : 3

  const unlocked = Boolean(myFranchise?.unlocked)
  const homeGround = myFranchise?.home_ground !== undefined && myFranchise.home_ground !== null
    && String(myFranchise.home_ground) !== '' ? String(myFranchise.home_ground) : ''
  const homeTile = homeGround ? tileMap.get(homeGround) : undefined
  const myTile = tileAt(myFranchise?.pos)
  const myTileOwner = ownerFor(myTile)

  const propertiesOf = (pid: string) => Object.entries(state?.properties || {})
    .filter(([, property]) => Boolean(property?.owner) && String(property.owner) === String(pid))
    .map(([id, property]) => {
      const tile = tileMap.get(String(id))
      return { id, tile, name: tile?.name || String(id), price: num(property?.price ?? tile?.price) }
    })
    .sort((a, b) => a.name.localeCompare(b.name))

  const rivals = managers.filter(manager => String(manager.id) !== String(you))

  const ownedTiles = propertiesOf(you).map(item => {
    const level = Math.min(MAX_LEVEL, num(state?.properties?.[String(item.id)]?.level))
    const cost = UPGRADE_BASE + level * UPGRADE_STEP
    return {
      tileId: item.id,
      tile: item.tile,
      level,
      cost,
      canUpgrade: isMyTurn && unlocked && level < MAX_LEVEL && num(myFranchise?.fc) >= cost,
      upgradeId: tileIdValue(item.id),
    }
  })

  const eventLog: Array<{ type: string; text: string }> = (app.events || [])
    .map(event => ({ type: String(event?.type || 'update'), text: String(event?.text || '').trim() }))
    .filter(entry => Boolean(entry.text))
    .slice(-3)
    .reverse()
    .map(entry => ({ ...entry, text: shortenText(entry.text) }))
  if (state?.last_event?.text) {
    const text = shortenText(String(state.last_event.text))
    if (!eventLog.some(entry => entry.text === text)) {
      eventLog.unshift({ type: String(state.last_event.type || 'update'), text })
      if (eventLog.length > 3) eventLog.length = 3
    }
  }

  const pendingTile = pending?.tile_id !== undefined ? tileMap.get(String(pending.tile_id)) : undefined
  // `pid` is the acting manager; only an explicit player_id names a cricketer.
  const pendingPlayer: PlayerData | undefined = typeof pending?.player_id === 'string'
    ? playerMap.get(String(pending.player_id))
    : undefined
  const pendingPrice = num(pending?.price ?? pendingTile?.price)
  const pendingName = pendingPlayer?.name || pendingTile?.name || 'this property'

  const pendingTrade = pending?.type === 'trade' ? pending : null
  const tradeForMe = Boolean(pendingTrade && String(pendingTrade.target) === String(you))
  const tradeByMe = Boolean(pendingTrade && String(pendingTrade.pid) === String(you))
  const tradeTargetName = managerName(pendingTrade?.target)
  const canTrade = isMyTurn && !rolled && !pending && ownedTiles.length > 0 && rivals.length > 0
  const targetTiles = propertiesOf(tradeTarget)

  let prompt = 'Open the game to join a room'
  let hint = 'Create a room, join with a code, or jump into quick play.'
  if (!app.session) {
    prompt = 'Open the game to join a room'
  } else if (!state) {
    prompt = 'Connecting to the season…'
    hint = 'Your franchise is loading from the room.'
  } else if (state.finished || state.phase === 'over') {
    prompt = 'Season complete — see the final table'
    hint = 'Most runs after the laps takes the title.'
  } else if (!state.started || lobby) {
    prompt = 'Waiting for the host to start the season…'
    hint = 'Share the room code, add bots, then roll out.'
  } else if (tradeForMe) {
    prompt = `Trade offer from ${managerName(pendingTrade?.pid)}`
    hint = 'Accept or decline — you can answer between turns.'
  } else if (tradeByMe) {
    prompt = `Trade offer sent — waiting for ${tradeTargetName}`
    hint = 'Bots answer automatically.'
  } else if (pending?.type === 'buy') {
    prompt = `Buy ${pendingName} for ${pendingPrice} FC?`
    hint = 'Skip if you would rather save your FC.'
  } else if (pending?.type === 'auction') {
    prompt = `Player auction — sign ${pendingPlayer?.name || 'a cricketer'}?`
    hint = 'Signing adds a player to your squad and +1 wicket.'
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
      give_tile: tileIdValue(tradeGive),
      take_tile: tileIdValue(tradeTake),
    })
    setTradeOpen(false)
  }

  return (
    <div className="app-shell mono-shell">
      <header className="topbar slim-header mono-header">
        <div className="brand">
          <span className="brand-mark">🏏</span>
          <span><strong>CRICKET MONOPOLY</strong><small>CRICKOPOLY · RULES 6</small></span>
        </div>
        <div className="header-meta mono-header-meta">
          <Badge tone="gold" icon="🏠">{state?.code || app.session?.code || '—'}</Badge>
          <Badge tone="blue" icon="🔢">Turn {Math.max(1, num(state?.turn))}</Badge>
          <Badge icon="🔄">Laps {leaderLaps}/{targetLaps}</Badge>
          <Badge icon="🎲">{rolled ? 'Rolled' : 'Ready'}</Badge>
        </div>
        <div className="top-actions">
          <span className={`conn ${app.connected ? 'online' : 'offline'}`}
            title={app.connected ? 'Live connection' : 'Reconnecting…'} />
          <Button variant="subtle" small onClick={() => setHelpOpen(true)}>? Help</Button>
          {app.session && <Button variant="subtle" small onClick={exit}>Exit</Button>}
        </div>
      </header>

      {myFranchise && (
        <section className="mono-whereami" aria-label="Where am I?">
          <div className="mono-where-location">
            <span className="mono-where-kicker">📍 WHERE AM I?</span>
            <strong><span className="mono-where-number">#{pad2(num(myFranchise.pos))}</span>{myTile?.name || 'Unknown square'}</strong>
            <small>{myTile?.country ? `${countryMeta(myTile.country)?.flag || ''} ${myTile.country}` : (myTile?.kind || 'square')}</small>
          </div>
          <div className="mono-where-owner" style={{ '--owner': myTileOwner?.color || '#8f7439' } as React.CSSProperties}>
            <span className="mono-where-avatar">{myTileOwner?.avatar || '🏦'}</span>
            <span className="mono-where-owner-copy">
              <small>OWNER</small>
              <b>{myTileOwner ? myTileOwner.name : 'Unowned / Bank'}</b>
            </span>
            {myTileOwner && <span className="mono-where-swatch" />}
          </div>
          <div className="mono-where-stats">
            <span><small>FC</small><b>{num(myFranchise.fc).toLocaleString()}</b></span>
            <span><small>RUNS</small><b>{num(myFranchise.runs)}</b></span>
            <span><small>WKTS</small><b>{num(myFranchise.wickets)}/{maxWickets}</b></span>
            <span><small>LAPS</small><b>{num(myFranchise.laps)}/{targetLaps}</b></span>
          </div>
        </section>
      )}

      <main className="mono-main">
        <section className="mono-board-wrap" aria-label="Cricket Monopoly board">
          <div className="mono-board">
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
                  className={`mono-tile mono-kind-${tile.kind || 'event'} ${isCurrent ? 'is-current' : ''} ${isYou ? 'is-you' : ''} ${isHome ? 'is-home' : ''} ${owner ? 'is-owned' : ''} ${tokens.length > 0 ? 'has-tokens' : ''}`}
                  title={`#${position} ${tile.name || 'Tile'}${owner ? ` · ${owner.name}` : price > 0 ? ` · ${price} FC` : ''}${level ? ` · level ${level}` : ''}`}>
                  <span className="mono-tile-head">
                    <b className="mono-tile-icon">{tile.icon || '•'}</b>
                    <span className="mono-tile-name">{shortName(tile.short || tile.name)}</span>
                  </span>
                  {(tile.kind === 'market' || tile.kind === 'stadium') ? (
                    <span className="mono-pips mono-tile-pips" aria-label={`Level ${level}`}>
                      {[0, 1, 2, 3].map(index => <i key={index} className={index < level ? 'on' : ''} />)}
                    </span>
                  ) : <span className="mono-tile-gap" />}
                  {owner ? (
                    <span className="mono-tile-owner" style={{ '--owner': owner.color || '#c8a24b' } as React.CSSProperties}>
                      <b>{owner.avatar || '🏏'}</b>{shortName(owner.name)}
                    </span>
                  ) : price > 0 ? (
                    <span className="mono-tile-price">{price} FC</span>
                  ) : <span className="mono-tile-gap" />}
                  {tokens.length > 0 && (
                    <span className="mono-tile-tokens">
                      <span key={tokens[0].id} className="mono-token" title={tokens[0].name}
                        style={{ '--token': tokens[0].color || '#c8a24b' } as React.CSSProperties}>
                        {tokens[0].avatar || '🏏'}
                      </span>
                      {tokens.length > 1 && <span className="mono-token mono-token-count">+{tokens.length - 1}</span>}
                    </span>
                  )}
                </div>
              )
            })}

            <div className="mono-center">
              <div className="mono-center-mark">🏏</div>
              <h2>CRICKET MONOPOLY</h2>
              <small>BUY GROUNDS · SWAP SQUARES · SCORE RUNS</small>
              <div className="mono-dice" aria-label={`Dice: ${(state?.dice || []).join(', ') || 'not rolled'}`}>
                {(state?.dice?.length ? state.dice : [null, null]).map((face, index) => (
                  <span key={index} className={face ? 'rolled' : ''}>{face ?? '·'}</span>
                ))}
              </div>
              <div className="mono-center-lines">
                <span><small>SEASON LAPS</small><b>{leaderLaps} / {targetLaps}</b></span>
                <span><small>MANAGERS</small><b>{managers.length}</b></span>
              </div>
            </div>
          </div>
        </section>

        <aside className="mono-side">
          <Panel title="YOU" subtitle={myFranchise ? myFranchise.name : 'No franchise yet'} icon="⭐"
            className="mono-you-panel"
            action={isMyTurn ? <Badge tone="gold" icon="🎲">YOUR TURN</Badge> : <Badge>MANAGER</Badge>}>
            {myFranchise ? (
              <>
                <div className="mono-you-head" style={{ '--token': myFranchise.color } as React.CSSProperties}>
                  <span className="mono-you-avatar">{myFranchise.avatar || '🏏'}</span>
                  <div>
                    <strong>{myFranchise.name}</strong>
                    <small>{myFranchise.is_bot ? 'BOT' : 'MANAGER'} · POS {pad2(num(myFranchise.pos))}</small>
                  </div>
                </div>
                <div className="mono-you-flags">
                  <Badge tone={unlocked ? 'green' : 'default'}>{unlocked ? 'UPGRADES OPEN' : 'UPGRADES LOCKED'}</Badge>
                  {homeGround && <Badge tone="gold">🏠 {shortName(homeTile?.name)}</Badge>}
                </div>
                {Boolean(myFranchise.injured) && <p className="mono-status-line">🚑 Injury reserve — out for 2 turns.</p>}
                {Boolean(myFranchise.skipped) && !myFranchise.injured && <p className="mono-status-line">⏭️ Wicketkeeper charge — next turn skipped.</p>}
                {myFranchise.out && <p className="mono-status-line danger">⛔ All out — waiting for the season to end.</p>}
              </>
            ) : <Empty title="No franchise yet" text="Join a room to take your seat on the board." />}
          </Panel>

          <Panel title="Your properties"
            subtitle={unlocked ? `${ownedTiles.length} owned · upgrade before rolling` : `${ownedTiles.length} owned · upgrades locked`}
            icon="🏟️" className="mono-owned-panel">
            {!unlocked && (
              <p className="mono-upgrade-lock">🔒 Upgrade locked: own a batsman, bowler, wicketkeeper and a ground.</p>
            )}
            {unlocked && homeGround && (
              <p className="mono-home-note">⭐ HOME GROUND: +50% FC rent · +100 FC &amp; +50 runs when you land on it</p>
            )}
            <div className="mono-owned-list">
              {ownedTiles.length === 0 ? (
                <Empty title="Nothing owned yet" text="Buy a ground or player square when you land on it." />
              ) : ownedTiles.map(item => (
                <div key={item.tileId} className="mono-owned-row">
                  <span className="mono-owned-icon" style={{ '--tile': tileColor(item.tile) } as React.CSSProperties}>
                    {item.tile?.icon || '•'}
                  </span>
                  <div className="mono-owned-info">
                    <strong>
                      {item.tile?.name || String(item.tileId)}
                      {homeGround && String(item.tileId) === homeGround && <em className="mono-home-tag">HOME</em>}
                    </strong>
                    <small>
                      {countryMeta(item.tile?.country)?.flag} {item.tile?.country || item.tile?.kind || 'property'}
                      {item.tile?.role ? ` · ${item.tile.role}` : ''}
                    </small>
                    <span className="mono-pips">
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

          <Panel title="Standings" subtitle="Most runs wins the season" icon="🏆" className="mono-standings-panel">
            <div className="mono-table-scroll">
              <table className="data-table mono-standings-table">
                <thead><tr><th>#</th><th>Manager</th><th>Square</th><th>Runs</th><th>FC</th><th>Wk</th><th>Lap</th></tr></thead>
                <tbody>
                  {standings.map(row => {
                    const manager = state?.franchises?.[String(row.id)]
                    const position = num(manager?.pos ?? (row as { pos?: number }).pos)
                    const square = tileAt(position)
                    return (
                      <tr key={row.id} className={row.id === you ? 'is-me' : ''}>
                        <td><span className={`rank ${num(row.rank) === 1 ? 'rank-1' : ''}`}>{num(row.rank)}</span></td>
                        <td><span className="team-color" style={{ background: row.color }} />{row.name}</td>
                        <td className="mono-square-cell"><b>#{pad2(position)}</b><small>{shortName(square?.short || square?.name)}</small></td>
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

          <Panel title="Event log" subtitle="Latest three updates" icon="📢" className="mono-log-panel">
            <div className="mono-log-list">
              {eventLog.length === 0 ? (
                <Empty title="No events yet" text="Rolls, trades and charges appear here." />
              ) : eventLog.map((event, index) => (
                <div key={`${event.text}-${index}`} className="mono-log-row">
                  <span className="mono-log-dot" title={event.type}>{EVENT_ICONS[event.type] || '•'}</span>
                  <p>{event.text}</p>
                </div>
              ))}
            </div>
          </Panel>
        </aside>
      </main>

      <div className="mono-actionbar">
        <div className="mono-action-copy">
          <strong>{prompt}</strong>
          <small>{hint}</small>
        </div>
        <div className="mono-action-buttons">
          {app.session && state && !state.finished && state.phase !== 'over' && (
            pendingTrade ? (
              tradeForMe ? (
                <span className="mono-action-status">Trade offer — choose below</span>
              ) : (
                <span className="mono-action-status">Trade offer sent — waiting for {tradeTargetName}</span>
              )
            ) : pending?.type === 'buy' ? (
              <>
                <Button variant="gold" className="mono-action-primary"
                  onClick={() => send('buy', {})}>BUY · {pendingPrice} FC</Button>
                <Button variant="subtle" className="mono-action-secondary"
                  onClick={() => send('decline', {})}>SKIP</Button>
              </>
            ) : pending?.type === 'auction' ? (
              <>
                <Button variant="gold" className="mono-action-primary"
                  onClick={() => send('auction_buy', {})}>SIGN PLAYER · +1 WICKET</Button>
                <Button variant="subtle" className="mono-action-secondary"
                  onClick={() => send('auction_skip', {})}>SKIP</Button>
              </>
            ) : isMyTurn && !rolled ? (
              <>
                <Button variant="gold" className="mono-action-primary"
                  onClick={() => send('roll', {})}>🎲 ROLL DICE</Button>
                {canTrade && (
                  <Button variant="subtle" className="mono-action-trade" onClick={openTrade}>🔁 TRADE</Button>
                )}
              </>
            ) : (
              <span className="mono-action-status">
                {isMyTurn ? 'RESOLVING…' : currentFranchise?.is_bot ? 'BOT PLAYING…' : 'WAITING…'}
              </span>
            )
          )}
          {(!app.session || !state || state.finished || state.phase === 'over') && (
            <span className="mono-action-status">{state?.finished || state?.phase === 'over' ? 'FINISHED' : 'STANDBY'}</span>
          )}
        </div>
      </div>

      {helpOpen && <MonopolyHelpModal onClose={() => setHelpOpen(false)} />}
      {tradeOpen && state && !state.finished && state.phase !== 'over' && (
        <Modal title="Trade a square" subtitle="Swap one property for one rival's — no money"
          width="540px" onClose={() => setTradeOpen(false)}>
          <div className="mono-trade-form">
            <p className="mono-trade-note">Swap one property for one property — no money changes hands.</p>
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
            <div className="mono-trade-summary">
              <span className="mono-trade-card"><small>YOU GIVE</small><b>{tileName(tradeGive)}</b></span>
              <span className="mono-trade-arrow">⇄</span>
              <span className="mono-trade-card rival"><small>YOU GET</small><b>{tileName(tradeTake)}</b></span>
            </div>
            <div className="mono-trade-actions">
              <Button variant="subtle" onClick={() => setTradeOpen(false)}>Cancel</Button>
              <Button variant="gold" disabled={!tradeGive || !tradeTarget || !tradeTake} onClick={submitTrade}>
                Send offer
              </Button>
            </div>
          </div>
        </Modal>
      )}
      {tradeForMe && pendingTrade && state && !state.finished && state.phase !== 'over' && (
        <Modal title="Trade offer for you" subtitle="Answer any time — it is not tied to your turn"
          width="520px" onClose={() => send('decline_trade', {})}>
          <div className="mono-offer">
            <div className="mono-offer-head" style={{ '--token': state.franchises?.[String(pendingTrade.pid)]?.color || '#c8a24b' } as React.CSSProperties}>
              <span className="mono-offer-avatar">{state.franchises?.[String(pendingTrade.pid)]?.avatar || '🏏'}</span>
              <div><strong>{managerName(pendingTrade.pid)} proposes a swap</strong><small>No money — one square each.</small></div>
            </div>
            <p className="mono-offer-line">
              {managerName(pendingTrade.pid)} offers <b>{tileName(pendingTrade.give_tile)}</b> for your{' '}
              <b>{tileName(pendingTrade.take_tile)}</b>.
            </p>
            <div className="mono-trade-summary">
              <span className="mono-trade-card rival"><small>THEY GIVE</small><b>{tileName(pendingTrade.give_tile)}</b></span>
              <span className="mono-trade-arrow">⇄</span>
              <span className="mono-trade-card"><small>YOU GIVE</small><b>{tileName(pendingTrade.take_tile)}</b></span>
            </div>
            <div className="mono-trade-actions">
              <Button variant="subtle" onClick={() => send('decline_trade', {})}>DECLINE</Button>
              <Button variant="success" onClick={() => send('accept_trade', {})}>ACCEPT</Button>
            </div>
          </div>
        </Modal>
      )}
      {!app.session && <MonopolyLandingModal />}
      {app.session && !state && (
        <Modal title="Cricket Monopoly" subtitle="Loading your season…" onClose={() => {}}>
          <Empty title="Connecting to the room" text="The 52-square board appears as soon as the lobby loads." />
        </Modal>
      )}
      {app.session && lobby && <MonopolyLobbyModal lobby={lobby} />}
      {app.session && state && (state.finished || state.phase === 'over') && (
        <MonopolyFinishModal state={state} standings={standings}
          canRestart={app.session.playerId === state.host_id}
          onRestart={() => send('restart', {})} />
      )}
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Help                                                                       */
/* -------------------------------------------------------------------------- */

function MonopolyHelpModal({ onClose }: { onClose: () => void }) {
  return (
    <Modal title="How to play" subtitle="Cricket Monopoly in six lines" width="640px" onClose={onClose}>
      <ol className="mono-help-list">
        <li>Roll and move. Passing SEASON START pays 100 FC + 100 runs. Buy any unowned square you land on.</li>
        <li>Pay the owner: a wicketkeeper costs runs and skips your next turn; a batsman costs runs, less as it upgrades.</li>
        <li>A bowler costs runs + FC (a wicket at max upgrade); a ground charges FC rent; iconic squares pay FC + runs from the dice.</li>
        <li>Upgrades stay locked until you own a batsman, a bowler, a wicketkeeper and a ground.</li>
        <li>Your first ground is your home ground: +50% FC rent everywhere, and 100 FC + 50 runs when you land on it.</li>
        <li>On your turn, swap one square for a rival's — no money; bots answer automatically. Three laps: most runs wins, FC breaks ties, 3 wickets means all out. Auctions add a wicket; injury rests two turns.</li>
      </ol>
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */
/* Landing                                                                    */
/* -------------------------------------------------------------------------- */

function MonopolyLandingModal() {
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
    ruleset: 6,
    game: 'cricket-monopoly',
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
    <Modal title="Cricket Monopoly" subtitle="Buy grounds. Sign players. Score the most runs." width="940px"
      onClose={() => {}}>
      <div className="mono-landing-grid">
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
            <div className="settings-grid mono-landing-settings">
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
                  <p>Enter your manager name and join with this code. Only the room code is shared — no URLs or logins.</p>
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
              <strong>Instant season</strong>
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

        <Panel title="Continue a saved season" subtitle="Progress is saved on the server" icon="💾"
          action={<Button variant="subtle" small onClick={refreshSaved}>Refresh</Button>}>
          {app.saved.length === 0 ? (
            <div className="empty"><span>💾</span><strong>No saved seasons yet</strong>
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

function MonopolyLobbyModal({ lobby }: { lobby: MonopolyLobby }) {
  const { app, send, dispatch } = useApp()
  const [count, setCount] = useState(2)
  const [copied, setCopied] = useState(false)
  const members: LobbyMember[] = Array.isArray(lobby.members)
    ? lobby.members
    : Object.values((lobby.members || {}) as unknown as Record<string, LobbyMember>)
  const isHost = lobby.host_id === app.session?.playerId
    || members.some(member => member.is_host && member.id === app.session?.playerId)
  const maxPlayers = num(lobby.settings?.max_players) || 4
  const laps = num(lobby.settings?.laps) || 3
  const difficulty = String(lobby.settings?.difficulty || lobby.settings?.ai_difficulty || 'medium')
  const settings = {
    ruleset: 6,
    game: 'cricket-monopoly',
    laps,
    max_players: maxPlayers,
    difficulty,
    ai_difficulty: difficulty,
  }
  const patch = (next: Record<string, unknown>) => send('settings', { settings: { ...settings, ...next } })
  const copyCode = () => {
    navigator.clipboard?.writeText(lobby.code).then(() => {
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    }).catch(() => dispatch({ type: 'ERROR', error: `Room code: ${lobby.code}` }))
  }

  return (
    <Modal title="Cricket Monopoly lobby" subtitle="Invite managers, add bots, then start the season"
      width="900px" onClose={() => {}}>
      <div className="mono-lobby-grid">
        <Panel title="Managers" subtitle={`${members.length}/${maxPlayers} seats filled`} icon="🏏">
          <div className="mono-code-display">
            <small>ROOM CODE</small>
            <strong>{lobby.code}</strong>
            <span>Share the code only — no URLs or logins needed.</span>
            <Button variant="subtle" small onClick={copyCode}>{copied ? '✓ Copied code' : 'Copy code'}</Button>
          </div>
          <div className="member-list">
            {members.map(member => (
              <div key={member.id} className="member-row">
                <span className="mono-lobby-avatar"
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

        <Panel title="Settings" subtitle={isHost ? 'Host controls' : 'Only the host can edit these'} icon="⚙️">
          <div className="two-col">
            <label className="field"><span>Season laps</span>
              <select disabled={!isHost} value={laps}
                onChange={e => patch({ laps: Number(e.target.value) })}>
                {LAP_OPTIONS.map(option => <option key={option} value={option}>{option} laps</option>)}
              </select>
            </label>
            <label className="field"><span>Max players</span>
              <select disabled={!isHost} value={maxPlayers}
                onChange={e => patch({ max_players: Number(e.target.value) })}>
                {PLAYER_OPTIONS.map(option => <option key={option} value={option}>{option} managers</option>)}
              </select>
            </label>
          </div>
          <label className="field"><span>AI difficulty</span>
            <select disabled={!isHost} value={difficulty}
              onChange={e => patch({ difficulty: e.target.value, ai_difficulty: e.target.value })}>
              <option value="easy">Easy</option>
              <option value="medium">Medium</option>
              <option value="hard">Hard</option>
            </select>
          </label>
          <div className="bot-setup">
            <label className="field"><span>How many bots?</span>
              <input type="number" min={1} max={Math.max(1, maxPlayers - members.length)} value={count}
                onChange={e => setCount(Math.max(1, Math.min(maxPlayers, Number(e.target.value))))} />
            </label>
            <Button variant="subtle" block disabled={!isHost || members.length >= maxPlayers}
              onClick={() => send('bots', { count, difficulty })}>＋ Add bots</Button>
          </div>
          {isHost && (
            <div className="start-block">
              {members.length < 2 && <small>Add at least one more manager or bot.</small>}
              <Button variant="gold" block disabled={members.length < 2} onClick={() => send('start', {})}>
                🏏 Start season
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

function MonopolyFinishModal({ state, standings, canRestart, onRestart }: {
  state: MonopolyState
  standings: MonopolyStanding[]
  canRestart: boolean
  onRestart: () => void
}) {
  const championId = state.winner_id || standings[0]?.id
  const champion = standings.find(row => row.id === championId)
    || (championId ? state.franchises?.[championId] : undefined)
  const championName = champion?.name || 'Champion'
  const championRuns = num(champion?.runs)
  const championLaps = num(champion?.laps)

  return (
    <Modal title="Season complete" subtitle="The manager with the most runs takes the title"
      width="760px" onClose={() => {}}>
      <div className="mono-champion">
        <span>🏆</span>
        <small>CHAMPION</small>
        <h2>{championName}</h2>
        <p>{championRuns} runs · {championLaps} laps · most runs after the full season</p>
      </div>
      <table className="data-table mono-result-table">
        <thead><tr><th>#</th><th>Manager</th><th>Runs</th><th>FC</th><th>Wkts</th><th>Laps</th></tr></thead>
        <tbody>
          {standings.map(row => (
            <tr key={row.id} className={row.id === championId ? 'champion' : ''}>
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
      <div className="mono-modal-foot">
        <small>{canRestart ? 'Play again starts a fresh season for every manager.'
          : 'Only the host can start a new season.'}</small>
        <Button variant="gold" onClick={onRestart} disabled={!canRestart}>Play again</Button>
      </div>
    </Modal>
  )
}
