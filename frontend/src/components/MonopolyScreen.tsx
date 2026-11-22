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

const num = (value: unknown): number => {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

const collectionSize = (value: unknown): number =>
  Array.isArray(value) ? value.length : num(value)

const shortName = (value?: string): string =>
  String(value || '').replace(/^the\s+/i, '').split(/[·—–-]/)[0].trim() || '—'

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

  const ownedTiles = Object.entries(state?.properties || {})
    .filter(([, property]) => Boolean(property?.owner) && String(property.owner) === you)
    .map(([tileId, property]) => {
      const tile = tileMap.get(String(tileId))
      const level = Math.min(MAX_LEVEL, num(property?.level))
      const cost = UPGRADE_BASE + level * UPGRADE_STEP
      const upgradeId = tile ? tile.id : (/^\d+$/.test(tileId) ? Number(tileId) : tileId)
      const canUpgrade = isMyTurn && level < MAX_LEVEL
        && num(myFranchise?.fc) >= cost
      return { tileId, tile, level, cost, canUpgrade, upgradeId }
    })
    .sort((a, b) => String(a.tile?.name || a.tileId).localeCompare(String(b.tile?.name || b.tileId)))

  const eventLog: Array<{ type: string; text: string }> = (app.events || [])
    .map(event => ({ type: String(event?.type || 'update'), text: String(event?.text || '').trim() }))
    .filter(entry => Boolean(entry.text))
    .slice(-6)
    .reverse()
  if (state?.last_event?.text && !eventLog.some(entry => entry.text === state.last_event!.text)) {
    eventLog.unshift({ type: String(state.last_event.type || 'update'), text: String(state.last_event.text) })
  }

  const pendingTile = pending?.tile_id !== undefined ? tileMap.get(String(pending.tile_id)) : undefined
  // `pid` is the acting manager; only an explicit player_id names a cricketer.
  const pendingPlayer: PlayerData | undefined = typeof pending?.player_id === 'string'
    ? playerMap.get(String(pending.player_id))
    : undefined
  const pendingPrice = num(pending?.price ?? pendingTile?.price)
  const pendingName = pendingPlayer?.name || pendingTile?.name || 'this property'

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
    hint = 'Upgrade a property first, then roll.'
  } else if (currentFranchise) {
    prompt = `Waiting for ${currentFranchise.name}…`
    hint = currentFranchise.is_bot ? 'Bot turns resolve automatically.' : 'The dice pass around the board.'
  }

  const exit = () => {
    setSession(null)
    dispatch({ type: 'STATE', state: null })
    dispatch({ type: 'JOIN_CODE', code: null })
  }

  return (
    <div className="app-shell mono-shell">
      <header className="topbar slim-header mono-header">
        <div className="brand">
          <span className="brand-mark">🏏</span>
          <span><strong>CRICKET MONOPOLY</strong><small>CRICKOPOLY · RULES 5</small></span>
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

      <main className="mono-main">
        <section className="mono-board-wrap" aria-label="Cricket Monopoly board">
          <div className="mono-board">
            {tiles.map(tile => {
              const position = num(tile.position)
              const cell = tileCell(position)
              const property = state?.properties?.[String(tile.id)]
              const owner = property?.owner ? state?.franchises?.[String(property.owner)] : undefined
              const level = Math.min(MAX_LEVEL, num(property?.level))
              const tokens = managers.filter(f => num(f.pos) === position)
              const isCurrent = Boolean(currentFranchise && num(currentFranchise.pos) === position)
              const style = {
                gridRow: cell.gridRow,
                gridColumn: cell.gridColumn,
                '--tile': tileColor(tile),
                '--owner': owner?.color || 'transparent',
              } as React.CSSProperties
              return (
                <div key={`${tile.id}-${position}`} style={style}
                  className={`mono-tile mono-kind-${tile.kind || 'event'} ${isCurrent ? 'is-current' : ''} ${owner ? 'is-owned' : ''}`}
                  title={`${tile.name || 'Tile'}${owner ? ` · ${owner.name}` : ''}${level ? ` · level ${level}` : ''}`}>
                  <span className="mono-tile-head">
                    <b className="mono-tile-icon">{tile.icon || '•'}</b>
                    <span className="mono-tile-name">{shortName(tile.short || tile.name)}</span>
                  </span>
                  {(tile.kind === 'market' || tile.kind === 'stadium') ? (
                    <span className="mono-pips mono-tile-pips" aria-label={`Level ${level}`}>
                      {[0, 1, 2, 3].map(index => <i key={index} className={index < level ? 'on' : ''} />)}
                    </span>
                  ) : <span className="mono-tile-gap" />}
                  {tokens.length > 0 && (
                    <span className="mono-tile-tokens">
                      {tokens.slice(0, 4).map(token => (
                        <span key={token.id} className="mono-token" title={token.name}
                          style={{ '--token': token.color || '#c8a24b' } as React.CSSProperties}>
                          {token.avatar || '🏏'}
                        </span>
                      ))}
                    </span>
                  )}
                </div>
              )
            })}

            <div className="mono-center">
              <div className="mono-center-mark">🏏</div>
              <h2>CRICKET MONOPOLY</h2>
              <small>BUY GROUNDS · SIGN PLAYERS · CHARGE RIVALS</small>
              <div className="mono-dice" aria-label={`Dice: ${(state?.dice || []).join(', ') || 'not rolled'}`}>
                {(state?.dice?.length ? state.dice : [null, null]).map((face, index) => (
                  <span key={index} className={face ? 'rolled' : ''}>{face ?? '·'}</span>
                ))}
              </div>
              <div className="mono-center-lines">
                <span><small>SEASON LAPS</small><b>{leaderLaps} / {targetLaps}</b></span>
                <span><small>MANAGERS</small><b>{managers.length}</b></span>
              </div>
              {state?.last_event?.text && (
                <p className="mono-center-event"><span>{state.last_event.type === 'final' ? '🏆' : '📢'}</span>{state.last_event.text}</p>
              )}
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
                    <small>{myFranchise.is_bot ? 'BOT' : 'MANAGER'} · POS {num(myFranchise.pos)}</small>
                  </div>
                </div>
                <div className="mono-you-stats">
                  <span><small>FC</small><b>{num(myFranchise.fc).toLocaleString()}</b></span>
                  <span><small>RUNS</small><b>{num(myFranchise.runs)}</b></span>
                  <span><small>WICKETS</small><b>{num(myFranchise.wickets)} / {maxWickets}</b></span>
                  <span><small>LAPS</small><b>{num(myFranchise.laps)} / {targetLaps}</b></span>
                  <span><small>SQUAD</small><b>{collectionSize(myFranchise.squad)}</b></span>
                </div>
                <div className="mono-wickets" title={`${num(myFranchise.wickets)} of ${maxWickets} wickets left`}>
                  {Array.from({ length: maxWickets }, (_, index) => (
                    <span key={index} className={index < num(myFranchise.wickets) ? 'alive' : ''}>🏏</span>
                  ))}
                </div>
                {Boolean(myFranchise.injured) && <p className="mono-status-line">🚑 In injury reserve — you sit out.</p>}
                {Boolean(myFranchise.skipped) && !myFranchise.injured && <p className="mono-status-line">⏭️ Wicketkeeper charge — your next turn is skipped.</p>}
                {myFranchise.out && <p className="mono-status-line danger">⛔ All out — waiting for the season to end.</p>}
              </>
            ) : <Empty title="No franchise yet" text="Join a room to take your seat on the board." />}
          </Panel>

          <Panel title="Your properties" subtitle={`${ownedTiles.length} owned · upgrades before rolling`}
            icon="🏟️" className="mono-owned-panel">
            <div className="mono-owned-list">
              {ownedTiles.length === 0 ? (
                <Empty title="Nothing owned yet" text="Buy a ground or player square when you land on it." />
              ) : ownedTiles.map(item => (
                <div key={item.tileId} className="mono-owned-row">
                  <span className="mono-owned-icon" style={{ '--tile': tileColor(item.tile) } as React.CSSProperties}>
                    {item.tile?.icon || '•'}
                  </span>
                  <div className="mono-owned-info">
                    <strong>{item.tile?.name || String(item.tileId)}</strong>
                    <small>
                      {countryMeta(item.tile?.country)?.flag} {item.tile?.country || item.tile?.kind || 'property'}
                      {item.tile?.role ? ` · ${item.tile.role}` : ''}
                    </small>
                    <span className="mono-pips">
                      {[0, 1, 2, 3].map(index => <i key={index} className={index < item.level ? 'on' : ''} />)}
                    </span>
                  </div>
                  <Button small variant="subtle" disabled={!item.canUpgrade}
                    title={item.level >= MAX_LEVEL ? 'Maximum upgrade reached'
                      : `Upgrade for ${item.cost} FC`}
                    onClick={() => send('upgrade', { tile_id: item.upgradeId })}>
                    {item.level >= MAX_LEVEL ? 'MAX' : `↑ ${item.cost}`}
                  </Button>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Standings" subtitle="Most runs wins the season" icon="🏆" className="mono-standings-panel">
            <table className="data-table mono-standings-table">
              <thead><tr><th>#</th><th>Manager</th><th>Runs</th><th>FC</th><th>Wk</th><th>Lap</th></tr></thead>
              <tbody>
                {standings.map(row => (
                  <tr key={row.id} className={row.id === you ? 'is-me' : ''}>
                    <td><span className={`rank ${num(row.rank) === 1 ? 'rank-1' : ''}`}>{num(row.rank)}</span></td>
                    <td><span className="team-color" style={{ background: row.color }} />{row.name}</td>
                    <td><b>{num(row.runs)}</b></td>
                    <td>{num(row.fc)}</td>
                    <td>{num(row.wickets)}</td>
                    <td>{num(row.laps)}</td>
                  </tr>
                ))}
                {standings.length === 0 && (
                  <tr><td colSpan={6}><Empty title="No standings yet" /></td></tr>
                )}
              </tbody>
            </table>
          </Panel>

          <Panel title="Event log" subtitle="Latest six updates" icon="📢" className="mono-log-panel">
            <div className="mono-log-list">
              {eventLog.length === 0 ? (
                <Empty title="No events yet" text="Rolls, purchases and charges appear here." />
              ) : eventLog.map((event, index) => (
                <div key={`${event.text}-${index}`} className="mono-log-row">
                  <span className="mono-log-dot" />
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
            pending?.type === 'buy' ? (
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
              <Button variant="gold" className="mono-action-primary"
                onClick={() => send('roll', {})}>🎲 ROLL DICE</Button>
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
        <li>Roll and move; buy grounds and players you land on with FC. Passing SEASON START pays 100 FC and 100 runs.</li>
        <li>Each country has three player squares — wicketkeeper, batsman and bowler — with different charges.</li>
        <li>A wicketkeeper costs runs and skips your next turn; a batsman charge drops as the player is upgraded.</li>
        <li>A bowler costs runs plus FC; at maximum upgrade it also takes a wicket and pays the owner a bonus.</li>
        <li>Player auctions sign a real cricketer and add +1 wicket; injury reserve sits you out for two turns.</li>
        <li>The manager with the most runs after three laps (or the last with wickets) wins. FC breaks ties.</li>
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
    ruleset: 5,
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
    ruleset: 5,
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
