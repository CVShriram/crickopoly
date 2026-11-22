import React, { useEffect, useMemo, useState } from 'react'
import { useApp } from '../store'
import type {
  BattleLobby, BattleResult, BattleStanding, BattleState, BattleTactic, PlayerData,
} from '../types'
import { timeAgo, titleCase } from '../utils'
import { Avatar, Badge, Button, Empty, Modal, Panel, PlayerPortrait, Tabs } from './UI'

const AVATARS = ['🦁', '🦅', '🐯', '🐋', '🦘', '🦓', '🦉', '🐊']
const COLORS = ['#c8a24b', '#4fd1c5', '#f56565', '#68d391', '#b794f4', '#f6ad55', '#63b3ed', '#fc8181']
const ROUND_OPTIONS = [2, 4, 6, 8, 10, 12]
const PLAYER_OPTIONS = [2, 3, 4, 5, 6]
const PITCH_ICONS: Record<string, string> = { flat: '🏏', green: '🌿', dry: '🏜️', slow: '🐢' }

const num = (value: unknown): number => {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

/** The battle game always offers exactly three tactics: Attack, Anchor, Slog. */
function pickTactics(source: BattleTactic[]): BattleTactic[] {
  if (source.length <= 3) return source
  const byId = new Map(source.map(t => [String(t.id), t]))
  const chosen: BattleTactic[] = []
  const add = (t?: BattleTactic) => { if (t && !chosen.includes(t)) chosen.push(t) }
  add(byId.get('attack') || byId.get('powerplay'))
  add(byId.get('anchor'))
  add(byId.get('slog') || byId.get('death_slog'))
  for (const t of source) {
    if (chosen.length >= 3) break
    add(t)
  }
  return chosen.slice(0, 3)
}

function tacticEffect(tactic: BattleTactic): string {
  const bits: string[] = []
  const runs = num(tactic.run_mod)
  const bowl = num(tactic.bowl_mod)
  const risk = num(tactic.risk ?? tactic.wicket_mod)
  if (runs) bits.push(`${runs > 0 ? '+' : ''}${runs} runs`)
  if (bowl) bits.push(`${bowl > 0 ? '+' : ''}${bowl} BOWL`)
  if (risk) bits.push(`${risk > 0 ? '+' : ''}${risk} wicket risk`)
  if (num(tactic.pitch_run)) {
    bits.push(`${num(tactic.pitch_run) > 0 ? '+' : ''}${num(tactic.pitch_run)} on ${titleCase(tactic.pitch || 'pitch')}`)
  }
  return bits.join(' · ') || 'Balanced play'
}

export function BattleScreen() {
  const { app, dispatch, send, setSession } = useApp()
  const state = app.state as unknown as BattleState | null
  const lobby = state && !state.started ? state as unknown as BattleLobby : null
  const [selectedPlayer, setSelectedPlayer] = useState<string | null>(null)
  const [selectedTactic, setSelectedTactic] = useState<string | null>(null)
  const [helpOpen, setHelpOpen] = useState(false)

  const you = state?.you || app.session?.playerId || ''
  const gamedata = state?.gamedata || app.gamedata
  const players = gamedata?.players || []
  const rules = (gamedata?.rules || {}) as Record<string, any>
  const playerMap = useMemo(
    () => new Map(players.map(p => [String(p.id), p] as const)),
    [players],
  )
  const tactics = useMemo(
    () => pickTactics(Object.values((gamedata?.tactical_cards || {}) as Record<string, BattleTactic>)),
    [gamedata],
  )
  const roleLabels = (gamedata?.role_labels || {}) as Record<string, string>

  useEffect(() => {
    const play = state?.plays?.[you]
    setSelectedPlayer(play?.player_id || null)
    setSelectedTactic(play?.tactic_id || null)
  }, [state?.round, state?.code, you])

  const myFranchise = state?.franchises?.[you]
  const hand = (myFranchise?.hand || [])
    .map(id => playerMap.get(String(id)))
    .filter((p): p is PlayerData => Boolean(p))
  const standings = [...(state?.standings || [])].sort((a, b) => num(a.rank) - num(b.rank))
  const rounds = num(state?.rounds ?? rules.rounds ?? state?.settings?.rounds
    ?? state?.settings?.season_rounds ?? 6) || 6

  const pitchKey = state?.pitch || 'flat'
  const pitchInfo = ((gamedata?.pitches as Record<string, any> | undefined)?.[pitchKey] || {}) as
    Record<string, any>
  const pitchEffect = ((rules.pitch_effects as Record<string, any> | undefined)?.[pitchKey] || {}) as
    Record<string, any>
  const pitchIcon = String(pitchInfo.icon || PITCH_ICONS[pitchKey] || '🏏')
  const pitchName = String(pitchInfo.name || titleCase(pitchKey))
  const pitchNote = String(pitchEffect.note || pitchInfo.desc || 'Standard conditions')

  const pendingResult = state?.pending?.type === 'result' ? state.pending : null
  const lastResult = state?.last_result || null
  const revealedResult = state?.revealed && lastResult
    && (!state.round || num(lastResult.round) === num(state.round)) ? lastResult : null
  const showResult = Boolean(pendingResult || revealedResult)
  const result = ((pendingResult?.result as BattleResult | undefined) || lastResult) as BattleResult | null
  const canContinue = !pendingResult?.viewers?.length || pendingResult.viewers.includes(you)

  const yourPlay = state?.plays?.[you]
  const alreadyPlayed = Boolean(yourPlay?.player_id || yourPlay?.tactic_id)
  const myTurn = Boolean(state?.started && !state.finished && state.current_player_id === you
    && !showResult)
  const canPick = myTurn && !alreadyPlayed
  const canPlay = canPick && Boolean(selectedPlayer && selectedTactic)
  const waitingName = state?.franchises?.[state.current_player_id || '']?.name || 'the other manager'

  const selectedPlayerName = playerMap.get(selectedPlayer || '')?.name || 'no cricketer'
  const selectedTacticName = tactics.find(t => t.id === selectedTactic)?.name || 'no tactic'
  const selectionSummary = `Selected: ${selectedPlayerName} · ${selectedTacticName}`

  let prompt = 'Waiting for the host to start…'
  if (!app.session) prompt = 'Open the game to join a room'
  else if (state?.finished) prompt = 'Season complete — see the final table'
  else if (showResult) prompt = 'Results are in — review the round'
  else if (!state?.started) prompt = 'Waiting for the host to start…'
  else if (myTurn) prompt = alreadyPlayed ? 'Card locked in — waiting for everyone…' : 'Your turn — pick a card'
  else prompt = `Waiting for ${waitingName}…`

  const playCard = () => {
    if (!canPlay || !selectedPlayer || !selectedTactic) return
    send('play_card', { player_id: selectedPlayer, tactic_id: selectedTactic })
  }
  const nextRound = () => {
    if (!canContinue) return
    send('next', {})
  }
  const exit = () => {
    setSession(null)
    dispatch({ type: 'STATE', state: null })
    dispatch({ type: 'JOIN_CODE', code: null })
  }

  return (
    <div className="app-shell battle-shell">
      <header className="topbar slim-header battle-header">
        <div className="brand">
          <span className="brand-mark">🏏</span>
          <span><strong>CRICKET CARD BATTLE</strong><small>CRICKOPOLY</small></span>
        </div>
        <div className="header-meta">
          <Badge tone="gold" icon="🏠">{state?.code || app.session?.code || '—'}</Badge>
          <Badge tone="blue" icon="🎯">Round {state?.round || 1}/{rounds}</Badge>
          <Badge icon={pitchIcon}>{pitchName}</Badge>
        </div>
        <div className="top-actions">
          <span className={`conn ${app.connected ? 'online' : 'offline'}`}
            title={app.connected ? 'Live connection' : 'Reconnecting…'} />
          <Button variant="subtle" small onClick={() => setHelpOpen(true)}>? Help</Button>
          {app.session && <Button variant="subtle" small onClick={exit}>Exit</Button>}
        </div>
      </header>

      <main className="battle-main">
        <section className="panel battle-arena">
          <div className="battle-pitch-banner">
            <span className="battle-pitch-icon">{pitchIcon}</span>
            <div className="battle-pitch-copy">
              <small>PITCH · {titleCase(pitchKey)}</small>
              <strong>{pitchName}</strong>
              <p>{pitchNote}</p>
            </div>
            <Badge tone="gold">{rounds} rounds</Badge>
          </div>

          <div className="battle-turn-prompt">
            <span className="battle-pulse" />
            <strong>{prompt}</strong>
            <small>{showResult ? 'Cards revealed — the highest score takes the round' : selectionSummary}</small>
          </div>

          <div className="battle-arena-grid">
            <div className="battle-standings">
              <h3>Standings</h3>
              {standings.length === 0 ? <Empty title="Table opens at kickoff" /> : (
                <table className="data-table battle-table">
                  <thead><tr><th>#</th><th>Manager</th><th>Wins</th><th>Score</th></tr></thead>
                  <tbody>
                    {standings.map(row => (
                      <tr key={row.id} className={row.id === you ? 'mine' : ''}>
                        <td><span className={`rank ${num(row.rank) === 1 ? 'rank-1' : ''}`}>{num(row.rank)}</span></td>
                        <td><span className="team-color" style={{ background: row.color }} />{row.name}</td>
                        <td><strong>{num(row.points)}</strong></td>
                        <td>{num(row.total_score)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="battle-last-round">
              <h3>Last round</h3>
              {result?.rows?.length ? (
                <div className="battle-score-strip">
                  <small>R{num(result.round)} · {titleCase(result.pitch || pitchKey)}</small>
                  {result.rows.map((row, index) => (
                    <div key={`${row.pid || index}`}
                      className={`score-row ${row.won || row.pid === result.winner_id ? 'winner' : ''}`}>
                      <span className="score-avatar" style={{ '--avatar': row.color || '#c8a24b' } as React.CSSProperties}>
                        {row.avatar || '🏏'}
                      </span>
                      <span className="score-name">{row.name}</span>
                      <span className="score-stat"><small>RUNS</small><b>{num(row.runs)}</b></span>
                      <span className="score-stat"><small>WKTS</small><b>{num(row.wickets)}</b></span>
                      <span className="score-total">{num(row.score)}</span>
                    </div>
                  ))}
                </div>
              ) : <Empty title="No results yet" text="The first scorecard appears after round one." />}
            </div>
          </div>
        </section>

        <Panel title="Your hand" subtitle={`${hand.length} real cricketers · tap one to select`} icon="🏏"
          className="battle-hand-panel"
          action={myFranchise && <Badge tone="gold" icon="⭐">{num(myFranchise.points)} wins</Badge>}>
          {hand.length === 0 ? <Empty title="No cards in hand" text="Join a room to receive your cricketers." /> : (
            <div className="battle-hand-grid">
              {hand.map(player => (
                <button key={player.id} type="button" aria-pressed={selectedPlayer === player.id}
                  className={`cricket-card ${selectedPlayer === player.id ? 'selected' : ''}`}
                  onClick={() => setSelectedPlayer(player.id)} disabled={!canPick}>
                  <span className="cricket-card-head">
                    <PlayerPortrait player={player} size="sm" />
                    <span className="cricket-card-identity">
                      <strong>{player.name}</strong>
                      <small>{player.flag} {player.country} · {roleLabels[player.role] || titleCase(player.role)}</small>
                    </span>
                  </span>
                  <span className="cricket-card-ratings">
                    <span className="rating rating-bat"><small>BAT</small><b>{num(player.batting)}</b></span>
                    <span className="rating rating-bowl"><small>BOWL</small><b>{num(player.bowling)}</b></span>
                  </span>
                </button>
              ))}
            </div>
          )}
        </Panel>

        <Panel title="Pick a tactic" subtitle="Secret until every card is played" icon="⚡">
          <div className="battle-tactics-grid">
            {tactics.length === 0 ? <Empty title="No tactics available" /> : tactics.map(tactic => (
              <button key={tactic.id} type="button" aria-pressed={selectedTactic === tactic.id}
                className={`tactic-card ${selectedTactic === tactic.id ? 'selected' : ''}`}
                onClick={() => setSelectedTactic(tactic.id)} disabled={!canPick}>
                <span className="tactic-icon">{tactic.icon || '⚡'}</span>
                <strong>{tactic.name}</strong>
                <small className="tactic-effect">{tacticEffect(tactic)}</small>
                {tactic.desc && <span className="tactic-desc">{tactic.desc}</span>}
              </button>
            ))}
          </div>
        </Panel>
      </main>

      <div className="battle-actionbar">
        <div className="battle-action-copy"><strong>{prompt}</strong><small>{selectionSummary}</small></div>
        {showResult ? (
          <Button variant="gold" className="battle-action-btn" onClick={nextRound} disabled={!canContinue}>
            CONTINUE
          </Button>
        ) : (
          <Button variant="gold" className="battle-action-btn" onClick={playCard} disabled={!canPlay}>
            PLAY CARD
          </Button>
        )}
      </div>

      {helpOpen && <BattleHelpModal rounds={rounds} onClose={() => setHelpOpen(false)} />}
      {!app.session && <BattleLandingModal />}
      {app.session && !state && (
        <Modal title="Cricket Card Battle" subtitle="Loading your room…" onClose={() => {}}>
          <Empty title="Connecting to the room" text="Your cards appear as soon as the lobby loads." />
        </Modal>
      )}
      {app.session && lobby && <BattleLobbyModal lobby={lobby} />}
      {app.session && state?.started && showResult && result && !state.finished && (
        <BattleResultModal result={result} players={players} tactics={tactics}
          canContinue={canContinue} onContinue={nextRound} />
      )}
      {app.session && state?.finished && (
        <BattleFinishedModal state={state} standings={standings}
          canRestart={app.session?.playerId === state.host_id}
          onRestart={() => send('restart', {})} />
      )}
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Help                                                                       */
/* -------------------------------------------------------------------------- */

function BattleHelpModal({ rounds, onClose }: { rounds: number; onClose: () => void }) {
  return (
    <Modal title="How to play" subtitle="Cricket Card Battle in six lines" onClose={onClose} width="620px">
      <ol className="battle-help-list">
        <li>Each round, pick one real cricketer card and one tactic.</li>
        <li>BAT scores runs for your innings.</li>
        <li>BOWL gives opponents wickets.</li>
        <li>The pitch modifies the score.</li>
        <li>Highest score wins the round.</li>
        <li>Most rounds won after {rounds} rounds wins the game.</li>
      </ol>
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */
/* Landing                                                                    */
/* -------------------------------------------------------------------------- */

function BattleLandingModal() {
  const { app, create, join, quick, continueRoom, dispatch, refreshSaved, joinCode } = useApp()
  const [tab, setTab] = useState<'new' | 'join' | 'quick'>(() => joinCode ? 'join' : 'new')
  const [name, setName] = useState(() => localStorage.getItem('fg-name') || 'Manager')
  const [avatar, setAvatar] = useState(() => localStorage.getItem('fg-avatar') || '🦁')
  const [color, setColor] = useState(() => localStorage.getItem('fg-color') || '#c8a24b')
  const [code, setCode] = useState(() => joinCode || '')
  const [rounds, setRounds] = useState(6)
  const [maxPlayers, setMaxPlayers] = useState(4)
  const [difficulty, setDifficulty] = useState('medium')

  const profile = { name: name.trim() || 'Manager', avatar, color }
  const settings = {
    rounds, season_rounds: rounds, max_players: maxPlayers,
    difficulty, ai_difficulty: difficulty, pitch: 'flat',
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
    <Modal title="Cricket Card Battle" subtitle="Pick a cricketer. Pick a tactic. Win the round." width="940px"
      onClose={() => {}}>
      <div className="battle-landing-grid">
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
            <div className="settings-grid battle-landing-settings">
              <label className="field"><span>Rounds</span>
                <select value={rounds} onChange={e => setRounds(Number(e.target.value))}>
                  {ROUND_OPTIONS.map(n => <option key={n} value={n}>{n} rounds</option>)}
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
                  <p>Enter your own manager name and join with this code. Invites never contain tokens.</p>
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
              <strong>Instant battle</strong>
              <p>Three managers, two AI rivals, {rounds} rounds and sensible defaults. No waiting in a lobby.</p>
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

        <Panel title="Continue a saved battle" subtitle="Progress is saved on the server" icon="💾"
          action={<Button variant="subtle" small onClick={refreshSaved}>Refresh</Button>}>
          {app.saved.length === 0 ? (
            <div className="empty"><span>💾</span><strong>No saved battles yet</strong>
              <p>Create a room and it will appear here.</p></div>
          ) : (
            <div className="saved-list">
              {app.saved.slice(0, 8).map(row => (
                <button key={row.room_id} type="button" className="saved-row" onClick={() => continueRoom(row)}>
                  <span className="saved-icon">{row.finished ? '🏆' : '🏏'}</span>
                  <span className="saved-info">
                    <strong>{row.winner_name || row.franchises.join(' vs ') || row.code}</strong>
                    <small>{row.code} · Round {row.round} · {row.franchises.length} managers</small>
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

function BattleLobbyModal({ lobby }: { lobby: BattleLobby }) {
  const { app, send, dispatch } = useApp()
  const [count, setCount] = useState(2)
  const [difficulty, setDifficulty] = useState(String(lobby.settings?.difficulty
    || lobby.settings?.ai_difficulty || 'medium'))
  const [copied, setCopied] = useState(false)
  const members = lobby.members || []
  const isHost = lobby.host_id === app.session?.playerId
    || members.some(m => m.is_host && m.id === app.session?.playerId)
  const maxPlayers = num(lobby.settings?.max_players) || 4
  const currentRounds = num(lobby.settings?.rounds ?? lobby.settings?.season_rounds) || 6
  const settings = {
    rounds: currentRounds, season_rounds: currentRounds,
    max_players: maxPlayers, difficulty, ai_difficulty: difficulty,
    pitch: String(lobby.settings?.pitch || 'flat'),
  }
  const patch = (next: Record<string, unknown>) => send('settings', { settings: next })
  const copyCode = () => {
    navigator.clipboard?.writeText(lobby.code).then(() => {
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    }).catch(() => dispatch({ type: 'ERROR', error: `Room code: ${lobby.code}` }))
  }

  return (
    <Modal title="Battle lobby" subtitle="Invite managers, add bots, then start the rounds" width="900px"
      onClose={() => {}}>
      <div className="battle-lobby-grid">
        <div className="panel battle-lobby-panel">
          <header className="panel-head"><div className="panel-title-wrap"><span className="panel-icon">🏏</span>
            <div><h2>Managers</h2><p>{members.length}/{maxPlayers} seats filled</p></div></div></header>
          <div className="battle-code-display">
            <small>ROOM CODE</small>
            <strong>{lobby.code}</strong>
            <span>Share this code only — no links or tokens.</span>
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
        </div>

        <div className="panel battle-lobby-panel">
          <header className="panel-head"><div className="panel-title-wrap"><span className="panel-icon">⚙️</span>
            <div><h2>Settings</h2><p>{isHost ? 'Host controls' : 'Only the host can edit these'}</p></div></div></header>
          <div className="two-col">
            <label className="field"><span>Rounds</span>
              <select disabled={!isHost} value={currentRounds}
                onChange={e => patch({ ...settings, rounds: Number(e.target.value), season_rounds: Number(e.target.value) })}>
                {ROUND_OPTIONS.map(n => <option key={n} value={n}>{n} rounds</option>)}
              </select>
            </label>
            <label className="field"><span>Max players</span>
              <select disabled={!isHost} value={maxPlayers}
                onChange={e => patch({ ...settings, max_players: Number(e.target.value) })}>
                {PLAYER_OPTIONS.map(n => <option key={n} value={n}>{n} managers</option>)}
              </select>
            </label>
          </div>
          <label className="field"><span>AI difficulty</span>
            <select disabled={!isHost} value={difficulty}
              onChange={e => { setDifficulty(e.target.value); patch({ ...settings, ai_difficulty: e.target.value }) }}>
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
                🏏 Start battle
              </Button>
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */
/* Result & finish                                                            */
/* -------------------------------------------------------------------------- */

function BattleResultModal({ result, players, tactics, canContinue, onContinue }: {
  result: BattleResult
  players: PlayerData[]
  tactics: BattleTactic[]
  canContinue: boolean
  onContinue: () => void
}) {
  const playerMap = useMemo(() => new Map(players.map(p => [String(p.id), p] as const)), [players])
  const tacticMap = useMemo(() => new Map(tactics.map(t => [String(t.id), t] as const)), [tactics])
  const rows = result.rows || []
  const winner = rows.find(row => row.pid === result.winner_id)
  const winnerName = winner?.name
    || (result.winner_id ? 'Manager ' + result.winner_id.slice(-4) : 'No winner')

  return (
    <Modal title={`Round ${num(result.round)} results`}
      subtitle={`${titleCase(result.pitch || 'flat')} pitch · highest score wins`}
      width="860px" onClose={() => {}}>
      <div className="battle-winner-banner"><span>🏆</span>
        <div><small>ROUND WINNER</small><strong>{winnerName}</strong></div>
      </div>
      <table className="data-table battle-result-table">
        <thead><tr><th>Manager</th><th>Cricketer</th><th>Tactic</th><th>Runs</th><th>Wkts</th><th>Score</th></tr></thead>
        <tbody>
          {rows.map((row, index) => {
            const card = playerMap.get(String(row.player_id))
            const tactic = tacticMap.get(String(row.tactic_id))
            return (
              <tr key={`${row.pid || index}`} className={row.won || row.pid === result.winner_id ? 'winner' : ''}>
                <td><span className="team-color" style={{ background: row.color }} />{row.name}</td>
                <td>{card?.name || '—'}</td>
                <td>{tactic?.name || titleCase(row.tactic_id || '—')}</td>
                <td>{num(row.runs)}</td>
                <td>{num(row.wickets)}</td>
                <td><strong>{num(row.score)}</strong></td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <div className="battle-modal-foot">
        <small>{canContinue ? 'Everyone can move to the next round.' : 'Waiting for a viewer to continue…'}</small>
        <Button variant="gold" onClick={onContinue} disabled={!canContinue}>CONTINUE</Button>
      </div>
    </Modal>
  )
}

function BattleFinishedModal({ state, standings, canRestart, onRestart }: {
  state: BattleState
  standings: BattleStanding[]
  canRestart: boolean
  onRestart: () => void
}) {
  const championId = state.winner_id || standings[0]?.id
  const champion = state.franchises?.[championId || '']
    || standings.find(row => row.id === championId)
  const championName = champion?.name || 'Champion'
  const championWins = num((champion as { points?: number } | undefined)?.points)

  return (
    <Modal title="Battle complete" subtitle="Most rounds won takes the title" width="720px" onClose={() => {}}>
      <div className="battle-champion">
        <span>🏆</span>
        <small>CHAMPION</small>
        <h2>{championName}</h2>
        <p>{championWins} round wins</p>
      </div>
      <table className="data-table battle-result-table">
        <thead><tr><th>#</th><th>Manager</th><th>Wins</th><th>Total score</th></tr></thead>
        <tbody>
          {standings.map(row => (
            <tr key={row.id} className={row.id === championId ? 'winner' : ''}>
              <td><span className={`rank ${num(row.rank) === 1 ? 'rank-1' : ''}`}>{num(row.rank)}</span></td>
              <td><span className="team-color" style={{ background: row.color }} />{row.name}</td>
              <td><strong>{num(row.points)}</strong></td>
              <td>{num(row.total_score)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="battle-modal-foot">
        <small>{canRestart ? 'Play again resets the room with fresh cards.'
          : 'Only the host can start a new battle.'}</small>
        <Button variant="gold" onClick={onRestart} disabled={!canRestart}>Play again</Button>
      </div>
    </Modal>
  )
}
