import React, { useMemo, useState } from 'react'
import { useApp } from '../store'
import type { Franchise, GameModal, PlayerData, TycoonLobby, TycoonState } from '../types'
import { money, timeAgo, titleCase } from '../utils'
import { Avatar, Badge, Button, Empty, Modal, Panel, PlayerPortrait, Stat } from './UI'

const AVATARS = ['🦁', '🦅', '🐯', '🐋', '🦘', '🦓', '🦉', '🐊']
const COLORS = ['#c8a24b', '#4fd1c5', '#f56565', '#68d391', '#b794f4', '#f6ad55', '#63b3ed', '#fc8181']

type ForcedModal = 'landing' | 'loading' | 'lobby'
type ActiveModal = ForcedModal | GameModal

export function ModalHost({ state, lobby, manual, onClose }: {
  state: TycoonState | null
  lobby: TycoonLobby | null
  manual: GameModal
  onClose: () => void
}) {
  const { app } = useApp()

  let active: ActiveModal | null = null
  if (!app.session) active = 'landing'
  else if (!state) active = 'loading'
  else if (!state.started || lobby) active = 'lobby'

  if (!active && state) {
    if (manual) active = manual
    else if (state.auction) active = 'auction'
    else if (state.pending?.type === 'duel') active = 'duel'
    else if (state.pending?.type === 'result') active = 'result'
    else if (state.finished) active = 'results'
  }

  switch (active) {
    case 'landing': return <LandingModal />
    case 'loading': return <LoadingModal />
    case 'lobby': return lobby ? <LobbyModal lobby={lobby} /> : <LoadingModal />
    // State-driven modals stay until the server clears that pending state.
    case 'auction': return state ? <AuctionModal state={state} onClose={() => {}} /> : null
    case 'duel': return state ? <DuelModal state={state} onClose={() => {}} /> : null
    case 'result': return state ? <ResultModal state={state} onClose={() => {}} /> : null
    case 'market': return state ? <MarketModal state={state} onClose={onClose} /> : null
    case 'guide': return <GuideModal onClose={onClose} />
    case 'results': return state ? <ResultsModal state={state} onClose={onClose} /> : null
    case 'history': return state ? <HistoryModal state={state} onClose={onClose} /> : null
    case 'studio': return state ? <StudioModal state={state} onClose={onClose} /> : null
    case 'assets': return state ? <AssetsModal state={state} onClose={onClose} /> : null
    default: return null
  }
}

/* -------------------------------------------------------------------------- */
/* Landing                                                                    */
/* -------------------------------------------------------------------------- */

function LandingModal() {
  const { app, create, join, quick, continueRoom, dispatch, joinCode } = useApp()
  const [tab, setTab] = useState<'new' | 'join' | 'quick'>(joinCode ? 'join' : 'new')
  const [name, setName] = useState(() => localStorage.getItem('fg-name') || 'Manager')
  const [avatar, setAvatar] = useState(() => localStorage.getItem('fg-avatar') || '🦁')
  const [color, setColor] = useState(() => localStorage.getItem('fg-color') || '#c8a24b')
  const [code, setCode] = useState(() => joinCode || '')
  const [settings, setSettings] = useState({
    starting_credits: 1500, max_players: 6, season_rounds: 8,
    mode: 'standard', pitch: 'flat', ai_difficulty: 'medium',
  })

  const profile = { name: name.trim() || 'Manager', avatar, color }
  const saveProfile = () => {
    localStorage.setItem('fg-name', profile.name)
    localStorage.setItem('fg-avatar', avatar)
    localStorage.setItem('fg-color', color)
  }
  const switchTab = (next: 'new' | 'join' | 'quick') => {
    setTab(next)
    if (joinCode) dispatch({ type: 'JOIN_CODE', code: null })
  }

  return (
    <Modal title="Stadium Tycoon" subtitle="One board · one action · real cricketers · virtual FC" width="1000px" onClose={() => {}}>
      <div className="callout" style={{ margin: '0 0 14px' }}>
        <strong>Virtual FC only</strong>
        <p>No deposits, withdrawals, wagering or real-money prizes. Player names are used as factual data only.</p>
      </div>
      <div className="landing-grid">
        <Panel title="Start or join" subtitle="Create a room, use a code, or play the bots" icon="🚀">
          <div className="profile-row">
            <div className="avatar-picker">
              {AVATARS.map(a => (
                <button key={a} type="button" className={avatar === a ? 'active' : ''} onClick={() => setAvatar(a)}>{a}</button>
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
            <span>Manager / franchise name</span>
            <input value={name} maxLength={24} onChange={e => setName(e.target.value)} placeholder="Your franchise name" />
          </label>
          <div className="tabs compact">
            <button type="button" className={tab === 'new' ? 'active' : ''} onClick={() => switchTab('new')}>New room</button>
            <button type="button" className={tab === 'join' ? 'active' : ''} onClick={() => switchTab('join')}>Join code</button>
            <button type="button" className={tab === 'quick' ? 'active' : ''} onClick={() => switchTab('quick')}>Quick play</button>
          </div>

          {tab === 'new' && (
            <div className="settings-grid">
              <label className="field"><span>Franchises</span>
                <select value={settings.max_players} onChange={e => setSettings({ ...settings, max_players: Number(e.target.value) })}>
                  {[2, 3, 4, 5, 6].map(n => <option key={n} value={n}>{n} managers</option>)}
                </select>
              </label>
              <label className="field"><span>Rounds</span>
                <select value={settings.season_rounds} onChange={e => setSettings({ ...settings, season_rounds: Number(e.target.value) })}>
                  {[2, 4, 6, 8, 10, 12, 16].map(n => <option key={n} value={n}>{n} rounds</option>)}
                </select>
              </label>
              <label className="field"><span>Starting FC</span>
                <select value={settings.starting_credits} onChange={e => setSettings({ ...settings, starting_credits: Number(e.target.value) })}>
                  {[1000, 1500, 2000, 2500].map(n => <option key={n} value={n}>{n} FC</option>)}
                </select>
              </label>
              <label className="field"><span>Mode</span>
                <select value={settings.mode} onChange={e => setSettings({ ...settings, mode: e.target.value })}>
                  <option value="standard">Standard — highest Brand Value</option>
                  <option value="classic">Classic survival</option>
                </select>
              </label>
              <label className="field"><span>Opening pitch</span>
                <select value={settings.pitch} onChange={e => setSettings({ ...settings, pitch: e.target.value })}>
                  {['flat', 'green', 'dry', 'slow'].map(key =>
                    <option key={key} value={key}>{titleCase(key)}</option>)}
                </select>
              </label>
              <label className="field"><span>AI difficulty</span>
                <select value={settings.ai_difficulty} onChange={e => setSettings({ ...settings, ai_difficulty: e.target.value })}>
                  <option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option>
                </select>
              </label>
            </div>
          )}

          {tab === 'join' && <>
            {joinCode && (
              <div className="callout">
                <strong>Invite link opened</strong>
                <p>Enter your own manager name. You will join as a new franchise, not as the host.</p>
              </div>
            )}
            <label className="field">
              <span>Room code</span>
              <input className="code-input" value={code} maxLength={8} placeholder="ABCDE"
                onChange={e => setCode(e.target.value.toUpperCase())} />
            </label>
          </>}

          {tab === 'quick' && (
            <div className="callout">
              <strong>Instant season</strong>
              <p>Three franchises, two Medium AI managers, sensible defaults. No waiting in a lobby.</p>
            </div>
          )}

          <div className="button-row">
            {tab === 'new' && <Button onClick={() => { saveProfile(); create({ ...profile, settings }) }} disabled={app.busy}>Create room →</Button>}
            {tab === 'join' && <Button onClick={() => {
              saveProfile(); join(code.trim().toUpperCase(), profile.name, avatar, color)
              dispatch({ type: 'JOIN_CODE', code: null })
            }} disabled={app.busy || code.trim().length < 4}>Join room →</Button>}
            {tab === 'quick' && <Button onClick={() => {
              saveProfile(); quick({ ...profile, settings: { ...settings, max_players: 3 } })
            }} disabled={app.busy}>Start quick play →</Button>}
          </div>
        </Panel>

        <Panel title="Continue a saved season" subtitle="Progress is persisted on the server" icon="💾">
          {app.saved.length === 0 ? (
            <div className="empty"><span>💾</span><strong>No saved seasons yet</strong><p>Create a room and it will appear here.</p></div>
          ) : (
            <div className="saved-list">
              {app.saved.slice(0, 8).map(row => (
                <button key={row.room_id} type="button" className="saved-row" onClick={() => continueRoom(row)}>
                  <span className="saved-icon">{row.finished ? '🏆' : '🏏'}</span>
                  <span className="saved-info">
                    <strong>{row.winner_name || row.franchises.join(' vs ') || row.code}</strong>
                    <small>{row.code} · Round {row.round} · {row.matches} duels</small>
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

function LoadingModal() {
  return (
    <Modal title="Connecting…" subtitle="Loading your room from the server" width="440px" onClose={() => {}}>
      <Empty icon="🏏" title="Opening the board" text="This usually takes a moment." />
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */
/* Lobby                                                                      */
/* -------------------------------------------------------------------------- */

function LobbyModal({ lobby }: { lobby: TycoonLobby }) {
  const { app, send, dispatch } = useApp()
  const [count, setCount] = useState(2)
  const [difficulty, setDifficulty] = useState('medium')
  const [copied, setCopied] = useState(false)
  const members = lobby.members || []
  const isHost = lobby.host_id === app.session?.playerId
  const meMember = members.find(m => m.id === app.session?.playerId)
  const canStart = members.length >= 2 && members.every(m => m.is_bot || m.ready)

  const patch = (settings: Record<string, unknown>) => send('settings', { settings })
  const share = () => {
    // Code-only invite. Never put the host token into a shareable link.
    const url = `${window.location.origin}${window.location.pathname}?code=${lobby.code}&join=1`
    navigator.clipboard?.writeText(url).then(() => {
      setCopied(true); window.setTimeout(() => setCopied(false), 1800)
    }).catch(() => dispatch({ type: 'ERROR', error: url }))
  }

  return (
    <Modal title="Room lobby" subtitle={`${lobby.code} · Stadium Tycoon · virtual FC only`} width="980px" onClose={() => {}}>
      <div className="lobby-grid">
        <Panel title="Managers" subtitle={`${members.length}/${Number(lobby.settings?.max_players || 6)} seats`} icon="🏟️"
          action={<Badge tone="gold">{lobby.code}</Badge>}>
          <div className="member-list">
            {members.map(m => (
              <div key={m.id} className="member-row">
                <Avatar franchise={m as unknown as Franchise} />
                <div className="member-name"><strong>{m.name}</strong>
                  <small>{m.is_bot ? `${m.difficulty} AI` : m.is_host ? 'Room host' : 'Human manager'}</small></div>
                {m.is_host && <Badge tone="gold">HOST</Badge>}
                {m.is_bot ? <Badge tone="blue">BOT</Badge>
                  : <Badge tone={m.ready ? 'green' : 'danger'}>{m.ready ? 'READY' : 'NOT READY'}</Badge>}
              </div>
            ))}
          </div>
          {!meMember?.is_bot && (
            <Button variant={meMember?.ready ? 'subtle' : 'primary'} block
              onClick={() => send('ready', { ready: !meMember?.ready })}>
              {meMember?.ready ? 'Mark not ready' : 'I am ready'}
            </Button>
          )}
          <Button variant="subtle" block onClick={share}>{copied ? '✓ Invite link copied' : '🔗 Copy code-only invite'}</Button>
        </Panel>

        <Panel title="Season settings" subtitle={isHost ? 'Host controls' : 'Only the host can edit these'} icon="⚙️">
          <label className="field"><span>Mode</span>
            <select disabled={!isHost} value={String(lobby.settings?.mode || 'standard')}
              onChange={e => patch({ mode: e.target.value })}>
              <option value="standard">Standard — highest Brand Value</option>
              <option value="classic">Classic survival</option>
            </select>
          </label>
          <div className="two-col">
            <label className="field"><span>Franchises</span>
              <select disabled={!isHost} value={Number(lobby.settings?.max_players || 6)}
                onChange={e => patch({ max_players: Number(e.target.value) })}>
                {[2, 3, 4, 5, 6].map(n => <option key={n} value={n}>{n} managers</option>)}
              </select>
            </label>
            <label className="field"><span>Rounds</span>
              <select disabled={!isHost} value={Number(lobby.settings?.season_rounds || 8)}
                onChange={e => patch({ season_rounds: Number(e.target.value) })}>
                {[2, 4, 6, 8, 10, 12, 16].map(n => <option key={n} value={n}>{n} rounds</option>)}
              </select>
            </label>
          </div>
          <div className="two-col">
            <label className="field"><span>Starting FC</span>
              <select disabled={!isHost} value={Number(lobby.settings?.starting_credits || 1500)}
                onChange={e => patch({ starting_credits: Number(e.target.value) })}>
                {[1000, 1500, 2000, 2500].map(n => <option key={n} value={n}>{n} FC</option>)}
              </select>
            </label>
            <label className="field"><span>Opening pitch</span>
              <select disabled={!isHost} value={String(lobby.settings?.pitch || 'flat')}
                onChange={e => patch({ pitch: e.target.value })}>
                {['flat', 'green', 'dry', 'slow'].map(key => <option key={key} value={key}>{titleCase(key)}</option>)}
              </select>
            </label>
          </div>
          <label className="field"><span>AI difficulty</span>
            <select disabled={!isHost} value={String(lobby.settings?.ai_difficulty || 'medium')}
              onChange={e => patch({ ai_difficulty: e.target.value })}>
              <option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option>
            </select>
          </label>
        </Panel>

        <Panel title="AI managers" subtitle="Fill empty seats with automated rivals" icon="🤖">
          <div className="bot-setup">
            <label className="field"><span>How many bots?</span>
              <input type="number" min={1} max={6} value={count}
                onChange={e => setCount(Math.max(1, Math.min(6, Number(e.target.value))))} />
            </label>
            <label className="field"><span>Difficulty</span>
              <select value={difficulty} onChange={e => setDifficulty(e.target.value)}>
                <option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option>
              </select>
            </label>
          </div>
          <Button variant="subtle" block disabled={!isHost || members.length >= 6}
            onClick={() => send('bots', { count, difficulty })}>＋ Add AI managers</Button>
          <div className="callout"><strong>No draft</strong>
            <p>Everyone starts with six real cricketers and five tactic cards. You only sign players from market and auction tiles.</p>
          </div>
          {isHost && <div className="start-block">
            {!canStart && <small>Add at least one more manager or bot, and make sure everyone is ready.</small>}
            <Button variant="gold" block disabled={!canStart} onClick={() => send('start', {})}>🏏 Start season</Button>
          </div>}
        </Panel>
      </div>
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */
/* Auction                                                                    */
/* -------------------------------------------------------------------------- */

function AuctionModal({ state, onClose }: { state: TycoonState; onClose: () => void }) {
  const { send } = useApp()
  const auction = state.auction
  if (!auction) return null
  const player: PlayerData | undefined = auction.player
    || state.gamedata?.players?.find(p => p.id === auction.player_id)
  const base = auction.base_price || player?.value || 80
  const me = state.you ? state.franchises[state.you] : undefined
  const passed = Boolean(auction.has_passed)
  const bids = [base, base + 20, base + 50]

  return (
    <Modal title="Sealed auction" subtitle="One bid per manager · rivals’ bids stay hidden until reveal" width="640px" onClose={onClose}>
      <div className="lot-card">
        <PlayerPortrait player={player} size="lg" />
        <div className="lot-info">
          <small>{player ? `${player.flag} ${player.country} · ${titleCase(player.role)} · ${player.tier}` : 'Featured cricketer'}</small>
          <h2>{player?.name || 'Star cricketer'}</h2>
          <div className="lot-ratings">
            <span>OVR <b>{player?.overall ?? '—'}</b></span>
            <span>BAT <b>{player?.batting ?? '—'}</b></span>
            <span>BOWL <b>{player?.bowling ?? '—'}</b></span>
            <span>FIELD <b>{player?.fielding ?? '—'}</b></span>
          </div>
        </div>
        <div className="lot-price">
          <small>BASE PRICE</small>
          <strong>{money(base)}</strong>
          <span>your purse {money(me?.balance)}</span>
        </div>
      </div>

      <div className="bid-panel">
        <div>
          <small>YOUR SEALED BID</small>
          <strong>{auction.my_bid ? money(auction.my_bid) : '—'}</strong>
        </div>
        <div className="bid-actions">
          {bids.map(amount => (
            <Button key={amount} variant="gold" small
              disabled={passed || (me?.balance || 0) < amount || (auction.my_bid !== undefined && auction.my_bid >= amount)}
              onClick={() => send('bid', { amount })}>{money(amount)}</Button>
          ))}
          <Button variant="subtle" small disabled={passed} onClick={() => send('pass', {})}>
            {passed ? 'Passed' : 'Pass'}
          </Button>
        </div>
      </div>

      {passed && <div className="callout"><strong>Passed — waiting for reveal</strong>
        <p>The lot resolves once every manager has bid or passed.</p></div>}
      {!passed && auction.my_bid && <div className="callout success"><strong>Bid locked in</strong>
        <p>You can raise it before the reveal, or pass to withdraw.</p></div>}

      <div className="button-row" style={{ marginTop: 14 }}>
        <Button variant="subtle" small onClick={() => send('tick_auctions', {})}>Check / settle auction</Button>
      </div>
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */
/* Duel / tactic picker                                                       */
/* -------------------------------------------------------------------------- */

function DuelModal({ state, onClose }: { state: TycoonState; onClose: () => void }) {
  const { send } = useApp()
  const pending = state.pending
  if (!pending || pending.type !== 'duel') return null
  const you = state.you
  const me = you ? state.franchises[you] : undefined
  const isSide = Boolean(you && (pending.pid === you || pending.defender === you))
  const locked = you ? pending.cards?.[you] : undefined
  const challenger = pending.pid ? state.franchises[pending.pid] : undefined
  const defender = pending.defender ? state.franchises[pending.defender] : undefined
  const cards = (me?.tactics || [])
    .map(id => state.gamedata?.tactical_cards?.[id])
    .filter((card): card is NonNullable<typeof card> => Boolean(card))
  const pitchName = titleCase(state.pitch)

  return (
    <Modal title="Pick your tactic" subtitle={`${pending.label || 'Match duel'} · ${pitchName} pitch · ${money(pending.rent || 0)} at stake`}
      width="760px" onClose={onClose}>
      <div className="matchup-bar">
        <div className="matchup-team">
          <span style={{ background: challenger?.color }}>{challenger?.avatar || '🏏'}</span>
          <div><strong>{challenger?.name || 'Challenger'}</strong><small>Challenger</small></div>
        </div>
        <span className="versus">VS</span>
        <div className="matchup-team">
          <span style={{ background: defender?.color }}>{defender?.avatar || '🏏'}</span>
          <div><strong>{defender?.name || 'Defender'}</strong><small>Defender</small></div>
        </div>
      </div>

      {locked && <div className="callout success"><strong>🔒 {state.gamedata?.tactical_cards?.[locked]?.name || locked} locked in</strong>
        <p>Waiting for the other manager. Cards are revealed together on the scorecard.</p></div>}
      {!isSide && <div className="callout"><strong>Spectating</strong>
        <p>Only the two managers in this duel can choose a card.</p></div>}
      {!locked && isSide && <p className="muted" style={{ margin: '14px 0 4px' }}>
        Your hand — {cards.length} cards. The opponent’s choice is hidden.
      </p>}

      {!locked && isSide && <div className="challenge-grid">
        {cards.map(card => {
          const synergy = card.pitch === state.pitch
          return (
            <button key={card.id} type="button" className="challenge-card"
              onClick={() => send('card', { card: card.id })}>
              <span>{card.icon || '🃏'}</span>
              <div>
                <strong>{card.name}</strong>
                <small>{card.desc}</small>
                <small className={synergy ? 'synergy-on' : 'synergy-off'}>
                  {synergy ? `⚡ Pitch synergy: ${pitchName}` : card.pitch ? `Best on ${titleCase(card.pitch)}` : 'Works on any pitch'}
                </small>
                <small>
                  {card.run_mod ? `${card.run_mod > 0 ? '+' : ''}${card.run_mod} runs · ` : ''}
                  {card.bowl_mod ? `+${card.bowl_mod} wickets` : ''}
                  {!card.run_mod && !card.bowl_mod ? 'Balanced' : ''}
                </small>
              </div>
            </button>
          )
        })}
      </div>}

      {cards.length === 0 && isSide && <Empty title="No cards in hand" text="A strategy room tile can add one." />}
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */
/* Market / signing                                                           */
/* -------------------------------------------------------------------------- */

function MarketModal({ state, onClose }: { state: TycoonState; onClose: () => void }) {
  const { send } = useApp()
  const pending = state.pending
  if (!pending || pending.type !== 'sign_player') return null
  const isBuyer = pending.pid === state.you
  const candidates = (pending.candidates || [])
    .map(id => state.gamedata?.players?.find(p => p.id === id))
    .filter((p): p is PlayerData => Boolean(p))
  const me = state.you ? state.franchises[state.you] : undefined
  const price = pending.price || 150

  return (
    <Modal title={`Player market — ${pending.title || 'Signing'}`} subtitle={`Fixed fee ${money(price)} · one cricketer`}
      width="720px" onClose={onClose}>
      <p className="muted">
        {titleCase(pending.role || '')} · {pending.country ? titleCase(pending.country) : 'Global'} ·
        {' '}your purse {money(me?.balance)}
      </p>
      <div className="player-grid">
        {candidates.map(player => (
          <div key={player.id} className="draft-card">
            <PlayerPortrait player={player} />
            <div className="draft-card-main">
              <strong>{player.name}</strong>
              <small>{player.flag} {titleCase(player.role)} · {player.tier}</small>
            </div>
            <div className="draft-card-meta">
              <span>BAT <b>{player.batting}</b></span>
              <span>BOWL <b>{player.bowling}</b></span>
              <span>FIELD <b>{player.fielding}</b></span>
            </div>
            <div className="draft-card-foot">
              <span>OVR {player.overall}</span>
              <Button variant="success" small disabled={!isBuyer || (me?.balance || 0) < price}
                onClick={() => { send('buy_market', { player_id: player.id }); onClose() }}>
                Sign · {money(price)}
              </Button>
            </div>
          </div>
        ))}
      </div>
      <div className="button-row" style={{ marginTop: 14 }}>
        {isBuyer && <Button variant="subtle" onClick={() => { send('skip', {}); onClose() }}>Pass on this market</Button>}
        <Button variant="subtle" onClick={onClose}>Close</Button>
      </div>
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */
/* Result / scorecard                                                         */
/* -------------------------------------------------------------------------- */

function ResultModal({ state, onClose }: { state: TycoonState; onClose: () => void }) {
  const { send } = useApp()
  const pending = state.pending
  if (!pending || pending.type !== 'result') return null
  const you = state.you
  const canContinue = Boolean(you && (
    pending.pid === you || pending.viewers?.includes(you)
  ))
  const scorecard = pending.scorecard
  const score = (runs: number, wickets: number) => runs - wickets * 4
  const margin = scorecard
    ? Math.abs(score(scorecard.challenger.runs, scorecard.challenger.wickets)
      - score(scorecard.defender.runs, scorecard.defender.wickets))
    : 0
  const winner = pending.winner_id ? state.franchises[pending.winner_id] : undefined

  const proceed = () => {
    if (pending.pid === you) send('next', {})
    else send('skip', {})
    onClose()
  }

  return (
    <Modal title={pending.title || 'Result'} subtitle={pending.text || 'Turn outcome'} width="680px" onClose={onClose}>
      {scorecard && <>
        <div className="summary-list">
          {[scorecard.challenger, scorecard.defender].map(side => (
            <div key={side.id} className={`summary-row ${side.id === pending.winner_id ? 'champion' : ''}`}>
              <span style={{ fontSize: 22 }}>{side.icon || '🏏'}</span>
              <div><strong>{side.name}</strong><small>{side.id === pending.winner_id ? 'Winner' : 'Innings'}</small></div>
              <Badge tone={side.id === pending.winner_id ? 'gold' : 'default'}>
                {side.runs}/{side.wickets} — {side.card}
              </Badge>
            </div>
          ))}
        </div>
        <div className="score-mid" style={{ textAlign: 'center', margin: '14px 0 4px' }}>
          <span>{winner ? `${winner.name} won by ${margin} runs` : `Decided by ${margin} runs`}</span>
          <p>{money(pending.paid || 0)} settled at {pending.multiplier || 1}× rent{pending.pitch ? ` · ${titleCase(pending.pitch)} pitch` : ''}</p>
        </div>
      </>}
      {!scorecard && <div className="callout success"><strong>{pending.title || 'Outcome'}</strong><p>{pending.text || 'The board moves on.'}</p></div>}
      <div className="button-row" style={{ marginTop: 16, justifyContent: 'flex-end' }}>
        {canContinue
          ? <Button variant="gold" onClick={proceed}>➜ CONTINUE</Button>
          : <Button disabled>⏳ WAITING FOR THE ACTIVE MANAGER</Button>}
      </div>
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */
/* Guide                                                                      */
/* -------------------------------------------------------------------------- */

function GuideModal({ onClose }: { onClose: () => void }) {
  const steps = [
    { icon: '🎲', title: '1 · Roll', text: 'On your turn, roll the single die and move 1–6 tiles around the 52-tile board.' },
    { icon: '🏟️', title: '2 · Own & sign', text: 'Buy an unowned ground or sign one of three real cricketers on a market tile. Fixed prices only.' },
    { icon: '🔨', title: '3 · Auction', text: 'A star goes under a sealed bid. Choose base, +20, +50 or pass. Rivals’ bids stay hidden.' },
    { icon: '🛡️', title: '4 · Duel', text: 'When rent or a matchday is due, both managers secretly lock one of their five tactic cards.' },
    { icon: '📈', title: '5 · Score', text: 'Cards reveal together. Read one scorecard, pay the adjusted rent, then continue.' },
    { icon: '🏆', title: '6 · Win', text: 'After the final round, the highest Brand Value (cash + grounds + squad + duels) wins.' },
  ]
  return (
    <Modal title="How to play" subtitle="Six steps — that’s the whole game" width="760px" onClose={onClose}>
      <div className="howto-grid">
        {steps.map(s => (
          <div key={s.title} className="policy-card">
            <span>{s.icon}</span><strong>{s.title}</strong><p>{s.text}</p>
          </div>
        ))}
      </div>
      <div className="callout"><strong>Virtual FC only — no real money</strong>
        <p>No wagering, deposits, withdrawals or cash prizes. Cricketers are represented by names and ratings only — no photos, logos or official likenesses.</p>
      </div>
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */
/* Final results                                                              */
/* -------------------------------------------------------------------------- */

function ResultsModal({ state, onClose }: { state: TycoonState; onClose: () => void }) {
  const { app, send, refreshSaved } = useApp()
  const champion = state.winner_id ? state.franchises[state.winner_id] : undefined
  const isHost = state.host_id === app.session?.playerId
  const standings = useMemo(() => [...(state.standings || [])].sort((a, b) => a.rank - b.rank), [state.standings])

  return (
    <Modal title="Season complete" subtitle="Final Brand Value table" width="820px" onClose={onClose}>
      <div className="trophy-hero" style={{ padding: 18 }}>
        <span className="trophy">🏆</span>
        <small>CHAMPION</small>
        <h1 style={{ fontSize: 34 }}>{champion?.name || 'Season winner'}</h1>
        <p>Highest Brand Value after {Number(state.settings?.season_rounds || 8)} rounds. Virtual FC only.</p>
      </div>
      <table className="data-table">
        <thead><tr><th>#</th><th>Franchise</th><th>Brand value</th><th>Cash</th><th>Grounds</th><th>Players</th><th>Duels</th></tr></thead>
        <tbody>
          {standings.map(row => (
            <tr key={row.id} className={row.id === state.you ? 'mine' : ''}>
              <td>{row.rank}</td>
              <td><span className="team-color" style={{ background: row.color }} />{row.name}</td>
              <td><strong>{money(row.brand_value)}</strong></td>
              <td>{money(row.cash)}</td>
              <td>{row.stadiums}</td><td>{row.players}</td><td>{row.duels_won}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="button-row" style={{ marginTop: 16, justifyContent: 'flex-end' }}>
        <Button variant="subtle" onClick={onClose}>Back to board</Button>
        {isHost && <Button variant="danger" onClick={() => {
          if (window.confirm('Restart this season? Current progress will be replaced.')) {
            send('restart', {}); refreshSaved(); onClose()
          }
        }}>🔁 Restart season</Button>}
      </div>
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */
/* History / ledger                                                           */
/* -------------------------------------------------------------------------- */

function HistoryModal({ state, onClose }: { state: TycoonState; onClose: () => void }) {
  const { app, continueRoom } = useApp()
  const log = [...(state.log || [])].slice(-30).reverse()

  return (
    <Modal title="Season history" subtitle="Round log and saved rooms" width="760px" onClose={onClose}>
      <Panel title="Recent log" subtitle="Latest board events first" icon="📜">
        {log.length === 0 ? <Empty title="Nothing recorded yet" /> : (
          <div className="event-feed">
            {log.map((entry, i) => (
              <div key={i} className="feed-row"><span className="feed-dot" />
                <div><p>{entry.text}</p><small>R{entry.round || '—'} · {entry.kind || 'info'}</small></div>
              </div>
            ))}
          </div>
        )}
      </Panel>
      <Panel title="Saved seasons" subtitle="Invite links only ever contain the room code" icon="💾" className="mt-12">
        {app.saved.length === 0 ? <Empty title="No saved rooms" /> : (
          <div className="saved-list">
            {app.saved.slice(0, 8).map(row => (
              <button key={row.room_id} type="button" className="saved-row" onClick={() => { continueRoom(row); onClose() }}>
                <span className="saved-icon">{row.finished ? '🏆' : '💾'}</span>
                <span className="saved-info"><strong>{row.code} · Round {row.round}</strong>
                  <small>{row.franchises.join(' vs ') || 'Room'}</small></span>
                <span className="saved-time">{timeAgo(row.updated_at)}</span>
              </button>
            ))}
          </div>
        )}
      </Panel>
      <div className="button-row" style={{ marginTop: 14, justifyContent: 'flex-end' }}>
        <Button variant="subtle" onClick={onClose}>Close</Button>
      </div>
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */
/* Studio (host-only data editor)                                             */
/* -------------------------------------------------------------------------- */

function StudioModal({ state, onClose }: { state: TycoonState; onClose: () => void }) {
  const { app, send } = useApp()
  const players: PlayerData[] = state.gamedata?.players || []
  const [query, setQuery] = useState('')
  const [selectedId, setSelectedId] = useState(players[0]?.id || '')
  const [draft, setDraft] = useState<Record<string, string>>({})
  const isHost = state.host_id === app.session?.playerId
  const filtered = useMemo(() => players.filter(p =>
    !query || p.name.toLowerCase().includes(query.toLowerCase()) || p.country.includes(query.toLowerCase())
  ).slice(0, 40), [players, query])
  const selected = players.find(p => p.id === selectedId) || filtered[0]
  const fields = ['name', 'batting', 'bowling', 'fielding', 'value'] as const

  const apply = () => {
    if (!selected || !isHost) return
    const changes: Record<string, string | number> = {}
    if (draft.name !== undefined && draft.name !== selected.name) changes.name = draft.name
    for (const key of ['batting', 'bowling', 'fielding', 'value'] as const) {
      if (draft[key] !== undefined && Number(draft[key]) !== selected[key]) changes[key] = Number(draft[key])
    }
    if (Object.keys(changes).length) send('admin_update', { overrides: { players: { [selected.id]: changes } } })
    setDraft({})
  }

  return (
    <Modal title="Studio" subtitle="Host-only player data editor" width="900px" onClose={onClose}>
      {!isHost && <div className="callout danger"><strong>Host only</strong><p>Ask the room host to edit player data.</p></div>}
      <div className="admin-layout">
        <Panel title="Players" subtitle={`${players.length} real cricketers`} icon="📋"
          action={<input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search…" />}>
          <div className="roster-list">
            {filtered.map(p => (
              <button key={p.id} type="button" className={selected?.id === p.id ? 'active' : ''}
                onClick={() => { setSelectedId(p.id); setDraft({}) }}>
                <PlayerPortrait player={p} size="sm" />
                <div><strong>{p.name}</strong><small>{p.flag} {titleCase(p.role)} · {p.tier}</small></div>
                <b>{p.overall}</b>
              </button>
            ))}
          </div>
        </Panel>
        <Panel title={selected ? `Edit ${selected.name}` : 'Select a player'} subtitle={selected?.id || '—'} icon="✏️"
          action={<Button variant="gold" small disabled={!isHost || !selected} onClick={apply}>Apply edit</Button>}>
          {selected && <div className="two-col">
            {fields.map(key => (
              <label key={key} className="field"><span>{titleCase(key)}</span>
                <input
                  type={key === 'name' ? 'text' : 'number'}
                  min={key === 'name' ? undefined : 1}
                  max={key === 'name' ? undefined : key === 'value' ? 1000 : 99}
                  value={draft[key] ?? String(selected[key])}
                  disabled={!isHost}
                  onChange={e => setDraft({ ...draft, [key]: e.target.value })}
                />
              </label>
            ))}
          </div>}
          <div className="callout"><strong>Room-local edits only</strong>
            <p>Changes affect only this room’s saved game. Payload: <code>{'{ players: { playerId: { name?, batting?, bowling?, fielding?, value? } } }'}</code>.</p>
          </div>
        </Panel>
      </div>
      <div className="button-row" style={{ marginTop: 14, justifyContent: 'flex-end' }}>
        <Button variant="subtle" onClick={onClose}>Close</Button>
      </div>
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */
/* Assets / squad                                                             */
/* -------------------------------------------------------------------------- */

function AssetsModal({ state, onClose }: { state: TycoonState; onClose: () => void }) {
  const me = state.you ? state.franchises[state.you] : undefined
  const squad = (me?.squad || [])
    .map(id => state.gamedata?.players?.find(p => p.id === id))
    .filter((p): p is PlayerData => Boolean(p))
  const tactics = (me?.tactics || [])
    .map(id => state.gamedata?.tactical_cards?.[id])
    .filter((card): card is NonNullable<typeof card> => Boolean(card))
  const grounds = (me?.stadiums || [])
    .map(id => state.board?.find(t =>
      String(t.id) === String(id) || String(t.position) === String(id)))
    .filter((tile): tile is NonNullable<typeof tile> => Boolean(tile))

  return (
    <Modal title="Your franchise" subtitle="Squad, tactic hand and owned grounds" width="820px" onClose={onClose}>
      <div className="dashboard-strip compact" style={{ gridTemplateColumns: 'repeat(3,1fr)' }}>
        <Stat label="Cash" value={money(me?.balance)} tone="gold" icon="💰" />
        <Stat label="Squad" value={`${squad.length}/15`} icon="👥" />
        <Stat label="Duels won" value={me?.duels_won || 0} tone="green" icon="🏏" />
      </div>
      <Panel title="Squad" subtitle="Signed real cricketers" icon="👥" className="mt-12">
        {squad.length === 0 ? <Empty title="Empty squad" /> : (
          <div className="squad-grid">
            {squad.map(p => (
              <div key={p.id} className="squad-card">
                <div className="squad-select"><PlayerPortrait player={p} size="sm" />
                  <div className="squad-card-main"><strong>{p.name}</strong><small>{p.flag} {titleCase(p.role)} · {p.tier}</small></div>
                </div>
                <div className="squad-ratings"><span>BAT <b>{p.batting}</b></span><span>BOWL <b>{p.bowling}</b></span><span>FIELD <b>{p.fielding}</b></span></div>
              </div>
            ))}
          </div>
        )}
      </Panel>
      <div className="two-col mt-12">
        <Panel title="Tactic hand" subtitle={`${tactics.length} cards`} icon="🃏">
          <div className="chip-row">
            {tactics.map(card => <Badge key={card.id} tone="gold" icon={card.icon}>{card.name}</Badge>)}
          </div>
        </Panel>
        <Panel title="Owned grounds" subtitle={`${grounds.length} stadiums`} icon="🏟️">
          {grounds.length === 0 ? <Empty title="No grounds yet" /> : (
            <div className="venue-list">
              {grounds.map(t => <div key={t.position} className="venue-row"><div>
                <strong>{t.name}</strong><small>Ground {t.position} · {money(t.price || 0)}</small>
              </div></div>)}
            </div>
          )}
        </Panel>
      </div>
      <div className="button-row" style={{ marginTop: 14, justifyContent: 'flex-end' }}>
        <Button variant="subtle" onClick={onClose}>Close</Button>
      </div>
    </Modal>
  )
}
