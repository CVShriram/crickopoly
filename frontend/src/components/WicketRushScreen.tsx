import React, { useEffect, useMemo, useState } from 'react'
import { useApp } from '../store'
import type {
  LobbyMember, PlayerData, Role, RushFranchise, RushLobby, RushStanding, RushState,
} from '../types'
import { timeAgo, titleCase } from '../utils'
import { Avatar, Badge, Button, Empty, Modal, Panel, PlayerPortrait, Tabs } from './UI'

const AVATARS = ['🦁', '🦅', '🐯', '🐋', '🦘', '🦓', '🦉', '🐊']
const COLORS = ['#c8a24b', '#4fd1c5', '#f56565', '#68d391', '#b794f4', '#f6ad55', '#63b3ed', '#fc8181']
const HAND_SIZES = [5, 7, 9]
const PLAYER_OPTIONS = [2, 3, 4, 5, 6]

const ROLE_META: Record<Role, { icon: string; label: string; effect: string; tone: string }> = {
  batsman: { icon: '🏏', label: 'Batsman', effect: '+runs · next must bowl', tone: 'gold' },
  bowler: { icon: '🎯', label: 'Bowler', effect: '+1 wicket · skip next', tone: 'blue' },
  wicketkeeper: { icon: '🧤', label: 'Wicketkeeper', effect: 'steal a rival’s best card', tone: 'green' },
  allrounder: { icon: '⭐', label: 'All-rounder', effect: 'wild · +5 runs · reverse · again', tone: 'gold' },
}

const num = (value: unknown): number => {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

function formatEffect(effect: unknown, role: Role | null): string {
  if (typeof effect === 'string' && effect.trim()) {
    const value = effect.trim()
    const key = value.toLowerCase() as Role
    // The engine stores the role as the effect descriptor; expand it here.
    if (key in ROLE_META) return ROLE_META[key].effect
    return value
  }
  if (effect && typeof effect === 'object') {
    const e = effect as Record<string, unknown>
    const parts: string[] = []
    if (typeof e.text === 'string' && e.text.trim()) parts.push(e.text.trim())
    if (num(e.runs)) parts.push(`${num(e.runs) > 0 ? '+' : ''}${num(e.runs)} runs`)
    if (num(e.wickets)) parts.push(`+${num(e.wickets)} wicket${num(e.wickets) === 1 ? '' : 's'}`)
    if (e.reverse) parts.push('direction reversed')
    if (e.skip) parts.push('next player skipped')
    if (e.steal || num(e.stolen)) parts.push('card stolen')
    if (parts.length) return parts.join(' · ')
  }
  return role ? ROLE_META[role].effect : 'Opening play — any cricketer is legal'
}

export function WicketRushScreen() {
  const { app, dispatch, send, setSession } = useApp()
  const state = app.state as unknown as RushState | null
  const lobby = state && !state.started ? state as unknown as RushLobby : null
  const [selectedCard, setSelectedCard] = useState<string | null>(null)
  const [helpOpen, setHelpOpen] = useState(false)
  const [targeting, setTargeting] = useState(false)

  const you = state?.you || app.session?.playerId || ''
  const gamedata = state?.gamedata || app.gamedata
  const players = gamedata?.players || []
  const roleLabels = (gamedata?.role_labels || {}) as Record<string, string>
  const playerMap = useMemo(
    () => new Map(players.map(p => [String(p.id), p] as const)),
    [players],
  )
  const labelRole = (role: Role | null) => {
    if (!role) return 'Opening'
    return String(roleLabels[role] || ROLE_META[role]?.label || titleCase(role))
  }

  const myFranchise = state?.franchises?.[you]
  const hand = (myFranchise?.hand || [])
    .map(id => playerMap.get(String(id)))
    .filter((p): p is PlayerData => Boolean(p))
  const currentRole = state?.current_role || null
  const forcedRole = state?.forced_role || null
  // A batsman paints the next turn as bowler-only; the forced role wins.
  const activeRole = forcedRole || currentRole
  const lastCard = state?.last_card || null
  const currentCard = lastCard ? playerMap.get(String(lastCard.player_id)) : undefined
  const cardOwner = lastCard?.owner_id ? state?.franchises?.[lastCard.owner_id] : undefined
  const effect = formatEffect(lastCard?.effect, lastCard?.role || activeRole)
  const cardCount = (franchise?: RushFranchise) => franchise
    ? (franchise.hand_count !== undefined ? num(franchise.hand_count) : (franchise.hand?.length ?? 0))
    : 0

  const managers = useMemo(() => {
    const entries = Object.values(state?.franchises || {})
    if (!state?.order?.length) return entries
    const byId = new Map(entries.map(f => [String(f.id), f]))
    return state.order
      .map(id => byId.get(String(id)))
      .filter((f): f is RushFranchise => Boolean(f))
  }, [state?.franchises, state?.order])

  const standings = useMemo(
    () => [...(state?.standings || [])].sort((a, b) => num(a.rank) - num(b.rank)),
    [state?.standings],
  )

  const isMyTurn = Boolean(state?.started && !state.finished && state.phase !== 'over'
    && state.current_player_id === you)
  const pendingTarget = state?.pending?.type === 'target' ? state.pending : null
  const canTarget = isMyTurn && Boolean(pendingTarget)

  const targetCandidates = useMemo(() => {
    const allIds = state?.order?.length ? state.order : Object.keys(state?.franchises || {})
    const raw = pendingTarget?.candidates?.length ? pendingTarget.candidates : allIds
    return Array.from(new Set((raw || []).map(String)))
      .filter(id => Boolean(id) && id !== you && Boolean(state?.franchises?.[id]))
  }, [pendingTarget, state?.order, state?.franchises, you])
  const targetSet = useMemo(() => new Set(targetCandidates), [targetCandidates])

  const matchesRole = (card: PlayerData) =>
    !activeRole || (forcedRole ? card.role === forcedRole : card.role === activeRole)
      || card.role === 'allrounder'
  const playable = hand.filter(matchesRole)
  const selected = hand.find(card => card.id === selectedCard) || null
  const selectedLegal = Boolean(selected && isMyTurn && !pendingTarget && matchesRole(selected))

  useEffect(() => {
    setSelectedCard(null)
    setTargeting(false)
  }, [state?.code, state?.turn, state?.current_player_id, state?.current_role,
    state?.forced_role, state?.pending?.type, state?.pending?.pid])

  const currentName = state?.franchises?.[state.current_player_id || '']?.name || 'the other manager'
  let prompt = 'Open the game to join a room'
  if (!app.session) prompt = 'Open the game to join a room'
  else if (state?.finished || state?.phase === 'over') prompt = 'Match over — first to empty their hand wins'
  else if (!state?.started || lobby) prompt = 'Waiting for the host to start…'
  else if (canTarget) prompt = 'Pick a rival to run out'
  else if (isMyTurn && activeRole) {
    prompt = `Your turn — play a ${labelRole(activeRole).toLowerCase()} or any all-rounder`
  } else if (isMyTurn) prompt = 'Your turn — any cricketer is legal'
  else prompt = `Waiting for ${currentName}…`

  let hint = 'Match the live role or fire an all-rounder.'
  if (canTarget) hint = `${targetCandidates.length} rival${targetCandidates.length === 1 ? '' : 's'} available · tap a manager to steal`
  else if (selectedLegal && selected) hint = `${selected.name} · ${formatEffect(null, selected.role)}`
  else if (isMyTurn && playable.length === 0) hint = 'No playable card — draw 2 and pass the turn.'
  else if (isMyTurn) hint = 'Tap a lit cricketer, then play it.'

  const primaryLabel = canTarget ? 'PICK TARGET'
    : selectedLegal ? 'PLAY CARD'
      : isMyTurn && playable.length === 0 ? 'DRAW 2' : 'PLAY CARD'
  const primaryDisabled = canTarget ? false
    : selectedLegal ? false
      : isMyTurn && playable.length === 0 ? false : true

  const draw = () => {
    if (!isMyTurn || pendingTarget) return
    setSelectedCard(null)
    send('draw', {})
  }
  const sendTarget = (pid: string) => {
    if (!canTarget || !targetSet.has(pid)) return
    setTargeting(false)
    send('target', { target_id: pid })
  }
  const pickTarget = () => {
    if (!canTarget) return
    if (targetCandidates.length === 1) {
      sendTarget(targetCandidates[0])
      return
    }
    setTargeting(true)
    document.querySelector('.rush-strip')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
  const playSelected = () => {
    if (!selectedLegal || !selected) return
    send('play_card', { player_id: selected.id })
  }
  const primary = () => {
    if (canTarget) pickTarget()
    else if (selectedLegal) playSelected()
    else if (isMyTurn && playable.length === 0) draw()
  }
  const exit = () => {
    setSession(null)
    dispatch({ type: 'STATE', state: null })
    dispatch({ type: 'JOIN_CODE', code: null })
  }

  const direction = num(state?.direction) < 0 ? '↺' : '↻'
  const turnNumber = Math.max(1, num(state?.turn))

  return (
    <div className="app-shell rush-shell">
      <header className="topbar slim-header rush-header">
        <div className="brand">
          <span className="brand-mark">⚡</span>
          <span><strong>WICKET RUSH</strong><small>CRICKOPOLY · RULES 4</small></span>
        </div>
        <div className="header-meta">
          <Badge tone="gold" icon="🏠">{state?.code || app.session?.code || '—'}</Badge>
          <Badge tone="blue" icon="🔢">Turn {turnNumber}</Badge>
          <Badge tone={activeRole ? ROLE_META[activeRole].tone : 'gold'}
            icon={activeRole ? ROLE_META[activeRole].icon : '🎲'}>
            {labelRole(activeRole)}{forcedRole ? ' · forced' : ''}
          </Badge>
          <Badge icon="🂠">Deck {num(state?.deck_count)}</Badge>
          {state?.started && <Badge icon={direction}>{direction === '↺' ? 'Reverse' : 'Forward'}</Badge>}
        </div>
        <div className="top-actions">
          <span className={`conn ${app.connected ? 'online' : 'offline'}`}
            title={app.connected ? 'Live connection' : 'Reconnecting…'} />
          <Button variant="subtle" small onClick={() => setHelpOpen(true)}>? Help</Button>
          {app.session && <Button variant="subtle" small onClick={exit}>Exit</Button>}
        </div>
      </header>

      <main className="rush-main">
        <section className="panel rush-arena">
          <div className="rush-arena-top">
            <div className={`rush-current-card rush-role-${lastCard?.role || 'open'}`}>
              <div className="rush-current-label">
                <span>{lastCard ? ROLE_META[lastCard.role].icon : '🎲'}</span>
                <small>CURRENT CARD · {labelRole(lastCard?.role || null).toUpperCase()}</small>
              </div>
              {lastCard ? (
                <>
                  <div className="rush-current-identity">
                    <PlayerPortrait player={currentCard} size="lg" />
                    <div>
                      <strong>{lastCard.name || currentCard?.name || 'Cricketer'}</strong>
                      <small>{currentCard?.flag} {currentCard?.country} · {labelRole(lastCard.role)}</small>
                    </div>
                  </div>
                  <div className="rush-current-ratings">
                    <span><small>BAT</small><b>{num(currentCard?.batting)}</b></span>
                    <span><small>BOWL</small><b>{num(currentCard?.bowling)}</b></span>
                  </div>
                  <p className="rush-current-effect">{effect}</p>
                  <small className="rush-current-owner">
                    Played by {cardOwner?.name || 'a rival'}
                    {lastCard.owner_id === you ? ' (you)' : ''}
                  </small>
                </>
              ) : (
                <div className="rush-current-empty">
                  <span>🏏</span>
                  <strong>OPENING PLAY</strong>
                  <p>No card down yet. Any cricketer in your hand is legal.</p>
                </div>
              )}
            </div>

            <div className="rush-arena-side">
              <div className="rush-turn-prompt">
                <span className={`rush-pulse ${isMyTurn ? 'live' : ''}`} />
                <div>
                  <strong>{prompt}</strong>
                  <small>{hint}</small>
                </div>
              </div>
              {state?.last_event?.text && (
                <div className="rush-event-ticker">
                  <span>{['final', 'finish'].includes(state.last_event.type) ? '🏆' : '📢'}</span>
                  <p>{state.last_event.text}</p>
                </div>
              )}
              <div className="rush-quick-rules">
                <span><b>{num(myFranchise?.runs)}</b> runs</span>
                <span><b>{num(myFranchise?.wickets)}</b> wickets</span>
                <span><b>{cardCount(myFranchise)}</b> in hand</span>
                <span><b>{num(myFranchise?.drawn)}</b> drawn</span>
              </div>
            </div>
          </div>

          <div className={`rush-strip ${targeting ? 'targeting' : ''}`}>
            <div className="rush-strip-head">
              <h3>THE TABLE</h3>
              <small>{canTarget ? 'Tap a rival to steal their best card' : 'First manager out of cards wins'}</small>
            </div>
            <div className="rush-player-grid">
              {managers.length === 0 ? <Empty title="No managers yet" /> : managers.map(manager => {
                const isCurrent = state?.current_player_id === manager.id
                const targetable = canTarget && targetSet.has(manager.id)
                return (
                  <div
                    key={manager.id}
                    role={targetable ? 'button' : undefined}
                    tabIndex={targetable ? 0 : undefined}
                    onClick={targetable ? () => sendTarget(manager.id) : undefined}
                    onKeyDown={targetable ? e => {
                      if (e.key === 'Enter' || e.key === ' ') sendTarget(manager.id)
                    } : undefined}
                    className={`rush-player ${isCurrent ? 'current' : ''} ${manager.id === you ? 'mine' : ''} ${targetable ? 'targetable' : ''}`}
                    style={{ '--player': manager.color || '#c8a24b' } as React.CSSProperties}
                  >
                    <div className="rush-player-head">
                      <span className="rush-player-avatar">{manager.avatar || '🏏'}</span>
                      <span className="rush-player-name">
                        <strong>{manager.name}</strong>
                        <small>{manager.is_bot ? 'AI' : manager.id === you ? 'YOU' : 'MANAGER'}</small>
                      </span>
                      {isCurrent && <span className="rush-turn-flag">TURN</span>}
                      {targetable && <span className="rush-target-tag">RUN OUT</span>}
                    </div>
                    <div className="rush-player-stats">
                      <span><small>CARDS</small><b>{cardCount(manager)}</b></span>
                      <span><small>RUNS</small><b>{num(manager.runs)}</b></span>
                      <span><small>WKTS</small><b>{num(manager.wickets)}</b></span>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </section>

        <Panel title="Your hand" subtitle={`${hand.length} cricketers · ${playable.length} playable`}
          icon="🏏" className="rush-hand-panel"
          action={myFranchise && <Badge tone="gold" icon="⚡">
            {num(myFranchise.runs) - num(myFranchise.wickets) * 5} pts
          </Badge>}>
          {hand.length === 0 ? (
            <Empty title="No cards yet" text="Your cricketers appear when the match is dealt." />
          ) : (
            <div className="rush-hand-grid">
              {hand.map(card => {
                const legal = isMyTurn && !pendingTarget && matchesRole(card)
                const status = !isMyTurn ? 'WAIT' : pendingTarget ? 'TARGET' : legal ? 'LIVE' : 'BLOCKED'
                return (
                  <button
                    key={card.id}
                    type="button"
                    aria-pressed={selectedCard === card.id}
                    className={`rush-card rush-role-${card.role} ${legal ? 'legal' : 'illegal'} ${selectedCard === card.id ? 'selected' : ''}`}
                    onClick={() => { if (legal) setSelectedCard(selectedCard === card.id ? null : card.id) }}
                    disabled={!legal}
                  >
                    <span className="rush-card-top">
                      <PlayerPortrait player={card} size="sm" />
                      <span className="rush-card-name">
                        <strong>{card.name}</strong>
                        <small>{card.flag} {card.country}</small>
                      </span>
                      <span className={`rush-card-status status-${status.toLowerCase()}`}>{status}</span>
                    </span>
                    <span className="rush-card-role">
                      <b>{ROLE_META[card.role].icon}</b>
                      <span>{labelRole(card.role)}</span>
                    </span>
                    <span className="rush-card-ratings">
                      <span><small>BAT</small><b>{num(card.batting)}</b></span>
                      <span><small>BOWL</small><b>{num(card.bowling)}</b></span>
                    </span>
                    <span className="rush-card-effect">{ROLE_META[card.role].effect}</span>
                  </button>
                )
              })}
            </div>
          )}
        </Panel>
      </main>

      <div className="rush-actionbar">
        <div className="rush-action-copy">
          <strong>{prompt}</strong>
          <small>{hint}</small>
        </div>
        <div className="rush-action-buttons">
          <Button variant="gold" className="rush-action-btn" onClick={primary} disabled={primaryDisabled}>
            {primaryLabel}
          </Button>
          <Button variant="subtle" className="rush-draw-btn" onClick={draw}
            disabled={!isMyTurn || Boolean(pendingTarget)}>
            DRAW 2
          </Button>
        </div>
      </div>

      {helpOpen && <RushHelpModal onClose={() => setHelpOpen(false)} />}
      {!app.session && <RushLandingModal />}
      {app.session && !state && (
        <Modal title="Wicket Rush" subtitle="Loading your room…" onClose={() => {}}>
          <Empty title="Connecting to the table" text="Your cricketers appear as soon as the lobby loads." />
        </Modal>
      )}
      {app.session && lobby && <RushLobbyModal lobby={lobby} />}
      {app.session && state?.finished && (
        <RushFinishedModal state={state} standings={standings}
          canRestart={app.session.playerId === state.host_id}
          onRestart={() => send('restart', {})} />
      )}
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Help                                                                       */
/* -------------------------------------------------------------------------- */

function RushHelpModal({ onClose }: { onClose: () => void }) {
  return (
    <Modal title="How to play" subtitle="Wicket Rush in six lines" width="620px" onClose={onClose}>
      <ol className="rush-help-list">
        <li>Match the current role, or play any all-rounder (wild card).</li>
        <li>Batsman: add runs and force the next player to bowl.</li>
        <li>Bowler: give the next player a wicket and skip their turn.</li>
        <li>Wicketkeeper: pick a rival, steal their best card and make them draw 1.</li>
        <li>All-rounder: wild, +5 runs, reverse direction and play again.</li>
        <li>First manager to empty their hand wins. Runs and wickets are bragging rights.</li>
      </ol>
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */
/* Landing                                                                    */
/* -------------------------------------------------------------------------- */

function RushLandingModal() {
  const { app, create, join, quick, continueRoom, dispatch, refreshSaved, joinCode } = useApp()
  const [tab, setTab] = useState<'new' | 'join' | 'quick'>(() => joinCode ? 'join' : 'new')
  const [name, setName] = useState(() => localStorage.getItem('fg-name') || 'Manager')
  const [avatar, setAvatar] = useState(() => localStorage.getItem('fg-avatar') || '🦁')
  const [color, setColor] = useState(() => localStorage.getItem('fg-color') || '#c8a24b')
  const [code, setCode] = useState(() => joinCode || '')
  const [handSize, setHandSize] = useState(7)
  const [maxPlayers, setMaxPlayers] = useState(4)
  const [difficulty, setDifficulty] = useState('medium')

  const profile = { name: name.trim() || 'Manager', avatar, color }
  const settings = {
    ruleset: 4,
    game: 'wicket-rush',
    hand_size: handSize,
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
    <Modal title="Wicket Rush" subtitle="Match the role. Empty your hand. Win the table." width="940px"
      onClose={() => {}}>
      <div className="rush-landing-grid">
        <Panel title="Start or join" subtitle="Create a room, use a code, or play the bots" icon="🚀">
          <div className="profile-row">
            <div className="avatar-picker">
              {AVATARS.map(a => (
                <button key={a} type="button" className={avatar === a ? 'active' : ''}
                  onClick={() => setAvatar(a)}>{a}</button>
              ))}
            </div>
            <div className="color-picker">
              {COLORS.map(c => (
                <button key={c} type="button" style={{ background: c }} className={color === c ? 'active' : ''}
                  onClick={() => setColor(c)} aria-label={`Colour ${c}`} />
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
            <div className="settings-grid rush-landing-settings">
              <label className="field"><span>Hand size</span>
                <select value={handSize} onChange={e => setHandSize(Number(e.target.value))}>
                  {HAND_SIZES.map(n => <option key={n} value={n}>{n} cards</option>)}
                </select>
              </label>
              <label className="field"><span>Max players</span>
                <select value={maxPlayers} onChange={e => setMaxPlayers(Number(e.target.value))}>
                  {PLAYER_OPTIONS.map(n => <option key={n} value={n}>{n} managers</option>)}
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
                  <p>Enter your manager name and join with this code. Share the room code only — no URLs.</p>
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
              <strong>Instant rush</strong>
              <p>Three managers, {handSize} cards each and two AI rivals. Straight to the table, no lobby wait.</p>
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

        <Panel title="Continue a saved match" subtitle="Progress is saved on the server" icon="💾"
          action={<Button variant="subtle" small onClick={refreshSaved}>Refresh</Button>}>
          {app.saved.length === 0 ? (
            <div className="empty"><span>💾</span><strong>No saved matches yet</strong>
              <p>Create a room and it will appear here.</p></div>
          ) : (
            <div className="saved-list">
              {app.saved.slice(0, 8).map(row => (
                <button key={row.room_id} type="button" className="saved-row" onClick={() => continueRoom(row)}>
                  <span className="saved-icon">{row.finished ? '🏆' : '⚡'}</span>
                  <span className="saved-info">
                    <strong>{row.winner_name || row.franchises.join(' vs ') || row.code}</strong>
                    <small>{row.code} · Turn {row.round} · {row.franchises.length} managers</small>
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

function RushLobbyModal({ lobby }: { lobby: RushLobby }) {
  const { app, send, dispatch } = useApp()
  const [count, setCount] = useState(2)
  const [copied, setCopied] = useState(false)
  const members: LobbyMember[] = Array.isArray(lobby.members)
    ? lobby.members
    : Object.values((lobby.members || {}) as Record<string, LobbyMember>)
  const isHost = lobby.host_id === app.session?.playerId
    || members.some(m => m.is_host && m.id === app.session?.playerId)
  const maxPlayers = num(lobby.settings?.max_players) || 4
  const handSize = num(lobby.settings?.hand_size) || 7
  const difficulty = String(lobby.settings?.difficulty || lobby.settings?.ai_difficulty || 'medium')
  const settings = {
    ruleset: 4,
    game: 'wicket-rush',
    hand_size: handSize,
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
    <Modal title="Wicket Rush lobby" subtitle="Invite managers, add bots, then get the innings going"
      width="900px" onClose={() => {}}>
      <div className="rush-lobby-grid">
        <Panel title="Managers" subtitle={`${members.length}/${maxPlayers} seats filled`} icon="🏏">
          <div className="rush-code-display">
            <small>ROOM CODE</small>
            <strong>{lobby.code}</strong>
            <span>Share this code only — no URLs.</span>
            <Button variant="subtle" small onClick={copyCode}>{copied ? '✓ Copied code' : 'Copy code'}</Button>
          </div>
          <div className="member-list">
            {members.map(member => (
              <div key={member.id} className="member-row">
                <Avatar franchise={member as any} />
                <div className="member-name"><strong>{member.name}</strong>
                  <small>{member.is_bot ? `${member.difficulty} AI manager` : 'Human manager'}</small></div>
                {member.is_host && <Badge tone="gold">HOST</Badge>}
                {member.is_bot && <Badge tone="blue">BOT</Badge>}
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Settings" subtitle={isHost ? 'Host controls' : 'Only the host can edit these'} icon="⚙️">
          <div className="two-col">
            <label className="field"><span>Hand size</span>
              <select disabled={!isHost} value={handSize}
                onChange={e => patch({ hand_size: Number(e.target.value) })}>
                {HAND_SIZES.map(n => <option key={n} value={n}>{n} cards</option>)}
              </select>
            </label>
            <label className="field"><span>Max players</span>
              <select disabled={!isHost} value={maxPlayers}
                onChange={e => patch({ max_players: Number(e.target.value) })}>
                {PLAYER_OPTIONS.map(n => <option key={n} value={n}>{n} managers</option>)}
              </select>
            </label>
          </div>
          <label className="field"><span>AI difficulty</span>
            <select disabled={!isHost} value={difficulty}
              onChange={e => { patch({ difficulty: e.target.value, ai_difficulty: e.target.value }) }}>
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
                ⚡ Start rush
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

function RushFinishedModal({ state, standings, canRestart, onRestart }: {
  state: RushState
  standings: RushStanding[]
  canRestart: boolean
  onRestart: () => void
}) {
  const championId = state.winner_id || standings[0]?.id
  const champion = standings.find(row => row.id === championId)
    || (championId ? state.franchises?.[championId] : undefined)
  const championName = champion?.name || 'Champion'
  const championCards = num((champion as RushStanding | RushFranchise | undefined)?.cards)
  const championRuns = num((champion as RushStanding | RushFranchise | undefined)?.runs)
  const championWickets = num((champion as RushStanding | RushFranchise | undefined)?.wickets)

  return (
    <Modal title="Match complete" subtitle="First manager to empty their hand takes the title"
      width="760px" onClose={() => {}}>
      <div className="rush-champion">
        <span>🏆</span>
        <small>CHAMPION</small>
        <h2>{championName}</h2>
        <p>{championCards} cards left · {championRuns} runs · {championWickets} wickets</p>
      </div>
      <table className="data-table rush-result-table">
        <thead><tr><th>#</th><th>Manager</th><th>Cards</th><th>Runs</th><th>Wkts</th><th>Score</th></tr></thead>
        <tbody>
          {standings.map(row => (
            <tr key={row.id} className={row.id === championId ? 'champion' : ''}>
              <td><span className={`rank ${num(row.rank) === 1 ? 'rank-1' : ''}`}>{num(row.rank)}</span></td>
              <td><span className="team-color" style={{ background: row.color }} />{row.name}</td>
              <td>{num(row.cards)}</td>
              <td>{num(row.runs)}</td>
              <td>{num(row.wickets)}</td>
              <td><strong>{num(row.score)}</strong></td>
            </tr>
          ))}
          {standings.length === 0 && (
            <tr><td colSpan={6}><Empty title="No final table" text="The standings arrive with the final snapshot." /></td></tr>
          )}
        </tbody>
      </table>
      <div className="rush-modal-foot">
        <small>{canRestart ? 'Play again deals a fresh hand to every manager.'
          : 'Only the host can deal a new match.'}</small>
        <Button variant="gold" onClick={onRestart} disabled={!canRestart}>Play again</Button>
      </div>
    </Modal>
  )
}
