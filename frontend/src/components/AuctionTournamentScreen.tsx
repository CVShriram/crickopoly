import React, { useEffect, useState } from 'react'
import { useApp } from '../store'
import { timeAgo } from '../utils'
import type {
  AuctionTournamentBid, AuctionTournamentFranchise, AuctionTournamentGameData,
  AuctionTournamentLobby, AuctionTournamentPlayer, AuctionTournamentResult,
  AuctionTournamentStanding, AuctionTournamentState, LobbyMember,
} from '../types'
import { Badge, Button, Empty, Modal, Panel, Tabs } from './UI'

const AVATARS = ['🦁', '🦅', '🐯', '🐋', '🦘', '🦓', '🦉', '🐊']
const COLORS = ['#c8a24b', '#4fd1c5', '#f56565', '#68d391', '#b794f4', '#f6ad55', '#63b3ed', '#fc8181']
const BUDGET_OPTIONS = [800, 1200, 1800]
const LOT_OPTIONS = [12, 18, 24]
const PLAYER_OPTIONS = [2, 3, 4, 5, 6]
const QUICK_BIDS = [0, 25, 50, 100, 200]

const TACTICS = [
  { id: 'attack', label: 'Attack', icon: '⚡', runs: '+25 runs', wickets: 'no wicket change' },
  { id: 'balanced', label: 'Balanced', icon: '⚖️', runs: '+10 runs', wickets: '−3 wickets' },
  { id: 'defensive', label: 'Defensive', icon: '🛡️', runs: '−5 runs', wickets: '−8 wickets' },
] as const

const HELP_LINES = [
  'Every manager gets 1,200 FC. Eighteen real cricketers come up for auction, one lot at a time.',
  'Bid secretly (or pass). The highest sealed bid wins the player and pays the FC; ties go to the earlier rotation.',
  'After the draft, pick your captain and a tactic before each round-robin match.',
  'Your captain matters: their BAT counts double and their BOWL adds to your attack.',
  'Scores come from real ratings — sum of top 6 BAT, top 3 BOWL ÷ 4, then score = runs − wickets × 4.',
  'Attack adds 25 runs, Balanced adds 10 runs and −3 wickets, Defensive loses 5 runs and 8 wickets. Most points wins the cup.',
]

const num = (value: unknown): number => {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

const txt = (value: unknown): string => String(value ?? '').trim()

const initialsOf = (name: string): string =>
  name.split(/\s+/).map(part => part[0]).filter(Boolean).join('').slice(0, 2).toUpperCase() || '?'

const batOf = (player?: AuctionTournamentPlayer | null): number =>
  num(player?.bat ?? player?.batting ?? (player as { ratings?: { bat?: number } } | null)?.ratings?.bat)

const bowlOf = (player?: AuctionTournamentPlayer | null): number =>
  num(player?.bowl ?? player?.bowling ?? (player as { ratings?: { bowl?: number } } | null)?.ratings?.bowl)

const flagOf = (player?: AuctionTournamentPlayer | null): string =>
  txt(player?.flag) || '🏏'

const valueHint = (player?: AuctionTournamentPlayer | null): { label: string; tone: string } => {
  const total = batOf(player) + bowlOf(player)
  if (total >= 160) return { label: 'ELITE VALUE', tone: 'gold' }
  if (total >= 130) return { label: 'STAR VALUE', tone: 'green' }
  if (total >= 100) return { label: 'SOLID VALUE', tone: 'blue' }
  return { label: 'PROSPECT', tone: 'default' }
}

const sideId = (value: unknown): string => {
  if (typeof value === 'string' || typeof value === 'number') return txt(value)
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>
    return txt(record.id ?? record.pid ?? record.fid ?? record.player_id)
  }
  return ''
}

interface RevealedBid {
  pid: string
  name: string
  color: string
  amount: number
}

function revealedBids(
  result: AuctionTournamentResult | null,
  franchises: Record<string, AuctionTournamentFranchise>,
): RevealedBid[] {
  if (!result) return []
  const raw: unknown = result.bids
  const entries: Array<[string, unknown]> = Array.isArray(raw)
    ? raw.map(item => {
      const row = (item && typeof item === 'object' ? item : {}) as Record<string, unknown>
      return [sideId(row.pid ?? row.fid ?? row.id ?? row.manager), item]
    })
    : Object.entries(raw && typeof raw === 'object' ? raw as Record<string, unknown> : {})
  return entries
    .map(([pid, value]) => {
      const manager = franchises[pid]
      const row = (value && typeof value === 'object' ? value : {}) as Record<string, unknown>
      const amount = typeof value === 'number' ? value : num(row.amount ?? row.bid)
      return {
        pid,
        name: manager?.name || txt(row.name) || 'Manager',
        color: manager?.color || '#c8a24b',
        amount,
      }
    })
    .sort((a, b) => b.amount - a.amount)
}

interface FixtureView {
  key: number
  a: string
  b: string
  played: boolean
  next: boolean
  label: string
}

function fixtureViews(state: AuctionTournamentState | null): FixtureView[] {
  const raw = Array.isArray(state?.fixtures) ? state!.fixtures as unknown[] : []
  const index = num(state?.match_index)
  return raw.map((item, key) => {
    const row = (Array.isArray(item) ? {} : (item && typeof item === 'object' ? item : {})) as Record<string, unknown>
    const pair = Array.isArray(item) ? item : [null, null]
    const a = Array.isArray(item) ? sideId(pair[0]) : sideId(row.a ?? row.home ?? row.p1 ?? row.home_id)
    const b = Array.isArray(item) ? sideId(pair[1]) : sideId(row.b ?? row.away ?? row.p2 ?? row.away_id)
    return {
      key,
      a,
      b,
      played: Boolean(row.played) || Boolean(row.result) || Boolean(row.winner_id) || key < index,
      next: key === index,
      label: txt(row.label) || (num(row.round) > 0 ? `R${num(row.round)}` : ''),
    }
  })
}

interface ScoreView {
  pid: string
  name: string
  color: string
  score: number
  runs: number
  wickets: number
  topBat: string
  captain: string
  tactic: string
}

function scoreViews(
  result: AuctionTournamentResult | null,
  franchises: Record<string, AuctionTournamentFranchise>,
  playerMap: Map<string, AuctionTournamentPlayer>,
): ScoreView[] {
  if (!result) return []
  const make = (
    pid: string,
    raw: unknown,
  ): ScoreView => {
    const manager = franchises[pid]
    const row = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
    const score = typeof raw === 'number' ? raw
      : num(row.score ?? row.total_score ?? row.final_score ?? row.runs_scored)
    return {
      pid,
      name: manager?.name || txt(row.name) || 'Manager',
      color: manager?.color || txt(row.color) || '#c8a24b',
      score,
      runs: num(row.runs ?? row.total_runs ?? row.bat_runs),
      wickets: num(row.wickets ?? row.bowling_wickets ?? row.wkts),
      topBat: txt(row.top_bat ?? row.top_batsman ?? row.top_batter ?? row.topBat) || '—',
      captain: txt(row.captain_bonus ?? row.captain ?? row.captain_name) || '—',
      tactic: txt(row.tactic ?? row.tactic_used) || '—',
    }
  }
  const rawRows = Array.isArray(result.rows) ? result.rows : []
  const rows = rawRows.map(row => make(sideId(row.pid ?? row.id ?? row.fid ?? row.franchise_id), row))
  if (rows.length < 2) {
    const extra: ScoreView[] = []
    const a = sideId(result.a ?? result.home ?? result.p1 ?? result.a_id)
    const b = sideId(result.b ?? result.away ?? result.p2 ?? result.b_id)
    if (a && !rows.some(row => row.pid === a)) {
      extra.push(make(a, {
        score: result.a_score ?? result.score_a,
        runs: result.a_runs,
        wickets: result.a_wickets,
      }))
    }
    if (b && !rows.some(row => row.pid === b)) {
      extra.push(make(b, {
        score: result.b_score ?? result.score_b,
        runs: result.b_runs,
        wickets: result.b_wickets,
      }))
    }
    rows.push(...extra)
  }
  // The server result carries runs/wickets/score. Derive the descriptive
  // breakdown from the live snapshot so the scorecard still shows top BAT,
  // captain bonus and tactic without inventing any result data.
  return rows.map(row => {
    const franchise = franchises[row.pid]
    const squadIds: string[] = Array.isArray(franchise?.squad) ? franchise!.squad : []
    const rated = squadIds.map(id => playerMap.get(id)).filter((p): p is AuctionTournamentPlayer => Boolean(p))
    const topBat = [...rated].sort((x, y) => batOf(y) - batOf(x))[0]
    const captain = playerMap.get(txt(franchise?.captain))
    const tacticId = txt(franchise?.tactic || 'balanced').toLowerCase()
    const tactic = TACTICS.find(item => item.id === tacticId)
    return {
      ...row,
      topBat: row.topBat !== '—' ? row.topBat
        : topBat ? `${topBat.name} (${batOf(topBat)})` : '—',
      captain: row.captain !== '—' ? row.captain
        : captain ? `${captain.name} · +${2 * batOf(captain)} runs, +${Math.floor(bowlOf(captain) / 10)} wkts`
          : 'none',
      tactic: row.tactic !== '—' ? row.tactic
        : tactic ? `${tactic.label} (${tactic.runs}, ${tactic.wickets})` : tacticId || 'balanced',
    }
  })
}

function SquadStrip({ squad, captain, playerMap, onCaptain, disabled }: {
  squad: string[]
  captain: string | null
  playerMap: Map<string, AuctionTournamentPlayer>
  onCaptain: (playerId: string) => void
  disabled?: boolean
}) {
  return (
    <section className="auct-squad panel">
      <header className="auct-squad-head">
        <div>
          <span className="auct-kicker">YOUR SQUAD</span>
          <h3>{squad.length} signed {squad.length === 1 ? 'player' : 'players'}</h3>
        </div>
        <small>Tap a player to appoint captain · ★ BAT ×2, BOWL adds to attack</small>
      </header>
      {squad.length === 0 ? (
        <Empty icon="🏏" title="No players signed yet" text="Win a lot in the auction to build your squad." />
      ) : (
        <div className="auct-squad-strip">
          {squad.map(playerId => {
            const player = playerMap.get(playerId)
            const name = player?.name || playerId
            const isCaptain = captain === playerId
            return (
              <button
                key={playerId}
                type="button"
                className={`auct-squad-card ${isCaptain ? 'is-captain' : ''}`}
                disabled={disabled || isCaptain}
                title={isCaptain ? 'Your captain' : `Make ${name} captain`}
                onClick={() => onCaptain(playerId)}
              >
                <span className="auct-squad-portrait" style={{ '--hue': num(player?.portrait_hue) || 40 } as React.CSSProperties}>
                  {initialsOf(name)}
                </span>
                <span className="auct-squad-copy">
                  <strong>{name}</strong>
                  <small>{flagOf(player)} {txt(player?.role) || 'Cricketer'}</small>
                  <em>BAT {batOf(player)} · BOWL {bowlOf(player)}</em>
                </span>
                {isCaptain && <span className="auct-star">★</span>}
              </button>
            )
          })}
        </div>
      )}
    </section>
  )
}

export function AuctionTournamentScreen() {
  const { app, dispatch, send, setSession } = useApp()
  const state = app.state as unknown as AuctionTournamentState | null
  const lobby = state && !state.started ? state as unknown as AuctionTournamentLobby : null
  const [helpOpen, setHelpOpen] = useState(false)
  const [bidAmount, setBidAmount] = useState(50)

  const you = state?.you || app.session?.playerId || ''
  const franchises = state?.franchises || {}
  const myFranchise: AuctionTournamentFranchise | undefined = you ? franchises[you] : undefined
  const fc = num(myFranchise?.fc)
  const lotIndex = num(state?.lot_index)
  const lotCount = Array.isArray(state?.lots) ? state.lots.length : (num(state?.lots) || num(state?.settings?.lots) || 18)
  const phase = txt(state?.phase || (state?.finished ? 'over' : 'auction'))
  const isAuction = phase === 'auction'
  const isTournament = phase === 'tournament'
  const isOver = Boolean(state?.finished) || phase === 'over'
  const lastResult = state?.last_result || null
  const resultLot = txt(lastResult?.type) === 'lot' ? lastResult : null
  const resultMatch = txt(lastResult?.type) === 'match' ? lastResult : null
  const awaitingNext = txt(state?.pending?.type) === 'next' || Boolean(resultLot || resultMatch)

  const gamedata = (state?.gamedata || app.gamedata) as unknown as AuctionTournamentGameData | undefined
  const playerMap = new Map((gamedata?.players || [])
    .map(player => [txt(player.id), player] as const)
    .filter(([id]) => Boolean(id)))
  const currentLot = state?.current_lot || null

  const myBid: AuctionTournamentBid | null | undefined = you ? state?.bids?.[you] : undefined
  const bidPlaced = Boolean(myBid)
  const myBidAmount = num(myBid?.amount)
  const rivals = Object.entries(state?.bids || {})
    .filter(([pid]) => pid !== you)
    .map(([pid, bid]) => {
      const manager = franchises[pid]
      return { pid, bid, name: manager?.name || 'Manager', color: manager?.color || '#c8a24b' }
    })

  const lotWinnerId = sideId(resultLot?.winner_id ?? resultLot?.winner)
  const lotWinner = franchises[lotWinnerId]
  const lotWinnerName = lotWinner?.name
    || txt(resultLot?.winner && typeof resultLot.winner === 'object' ? resultLot.winner.name : '')
    || (lotWinnerId ? 'A manager' : '')
  const winningBid = num(resultLot?.price ?? resultLot?.winning_bid ?? resultLot?.amount)
  const revealed = revealedBids(resultLot, franchises)

  const fixtures = fixtureViews(state)
  const scores = scoreViews(resultMatch, franchises, playerMap)
  const matchWinnerId = sideId(resultMatch?.winner_id ?? resultMatch?.winner)
  const matchWinnerName = franchises[matchWinnerId]?.name
    || txt(resultMatch?.winner && typeof resultMatch.winner === 'object' ? resultMatch.winner.name : '')
  const currentFixture = fixtures.find(fixture => fixture.next)
  const currentTactic = txt(myFranchise?.tactic).toLowerCase() || 'balanced'

  const standings: AuctionTournamentStanding[] = (() => {
    if (state?.standings?.length) return [...state.standings].sort((a, b) => num(a.rank) - num(b.rank))
    return Object.values(franchises)
      .map(franchise => ({
        id: franchise.id,
        name: franchise.name,
        avatar: franchise.avatar,
        color: franchise.color,
        points: num(franchise.points),
        total_score: num(franchise.total_score),
        wins: num(franchise.wins),
        losses: num(franchise.losses),
        squad_size: Array.isArray(franchise.squad) ? franchise.squad.length : 0,
        fc: num(franchise.fc),
        rank: 0,
      }))
      .sort((a, b) => b.points - a.points || b.total_score - a.total_score)
      .map((row, index) => ({ ...row, rank: index + 1 }))
  })()

  const activity: Array<{ text: string; type: string }> = (() => {
    const source: unknown[] = [
      ...(Array.isArray(state?.log) ? state.log : []),
      ...(Array.isArray(state?.events) ? state.events : []),
      ...app.events,
    ]
    return source
      .map(item => {
        const row = (item && typeof item === 'object' ? item : {}) as Record<string, unknown>
        return { text: txt(row.text), type: txt(row.type) || 'update' }
      })
      .filter(row => Boolean(row.text))
      .slice(-3)
      .reverse()
  })()

  useEffect(() => {
    setBidAmount(Math.min(50, Math.max(0, fc)))
    // Reset the bid entry for each new lot, not on every budget update.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lotIndex])

  const exit = () => {
    setSession(null)
    dispatch({ type: 'STATE', state: null })
    dispatch({ type: 'JOIN_CODE', code: null })
  }

  const submitBid = (amount: number) => {
    if (bidPlaced || awaitingNext) return
    const safe = Math.max(0, Math.min(fc, Math.round(num(amount))))
    setBidAmount(safe)
    send('bid', { amount: safe })
  }

  const nameOf = (pid: string): string => franchises[pid]?.name || (pid ? pid : 'TBD')

  return (
    <div className="app-shell auct-shell">
      <header className="topbar slim-header auct-header">
        <div className="brand">
          <span className="brand-mark">🏏</span>
          <span>
            <strong>AUCTION + TOURNAMENT</strong>
            <small>CRICKOPOLY · RULES 7</small>
          </span>
        </div>
        <div className="auct-header-meta">
          <Badge tone="gold" icon="#">{state?.code || app.session?.code || '—'}</Badge>
          <Badge tone={isAuction ? 'gold' : isTournament ? 'green' : 'default'} icon="◆">
            {isAuction ? 'AUCTION' : isTournament ? 'TOURNAMENT' : isOver ? 'FINISHED' : 'LOBBY'}
          </Badge>
          {isAuction && <Badge icon="🔨">LOT {Math.min(lotIndex + 1, lotCount)}/{lotCount}</Badge>}
          {isTournament && <Badge icon="🏏">MATCH {Math.min(num(state?.match_index) + 1, Math.max(1, fixtures.length))}/{fixtures.length || '—'}</Badge>}
          <Badge tone="blue" icon="💰">{fc.toLocaleString()} FC</Badge>
        </div>
        <div className="top-actions">
          <span className={`conn ${app.connected ? 'online' : 'offline'}`}
            title={app.connected ? 'Live connection' : 'Reconnecting…'} />
          <Button variant="subtle" small onClick={() => setHelpOpen(true)}>? Help</Button>
          {app.session && <Button variant="subtle" small onClick={exit}>Exit</Button>}
        </div>
      </header>

      <main className="auct-main">
        <div className="auct-stage">
          {!state && app.session && (
            <Panel title="Auction + Tournament" subtitle="Loading your room…" icon="🏏">
              <Empty title="Connecting" text="Your franchise and the first lot appear as soon as the room loads." />
            </Panel>
          )}

          {state?.started && isAuction && (
            <>
              {currentLot ? (
                <article className="auct-lot">
                  <div className="auct-lot-top">
                    <span className="auct-kicker">CURRENT LOT · {Math.min(lotIndex + 1, lotCount)} OF {lotCount}</span>
                    <span className="auct-lot-hint">{valueHint(currentLot).label}</span>
                  </div>
                  <div className="auct-lot-body">
                    <span className="auct-portrait" style={{ '--hue': num(currentLot.portrait_hue) || 40 } as React.CSSProperties}>
                      {initialsOf(txt(currentLot.name))}
                    </span>
                    <div className="auct-lot-copy">
                      <h2>{txt(currentLot.name) || 'Cricketer'}</h2>
                      <p>{flagOf(currentLot)} {txt(currentLot.country)} · {txt(currentLot.role) || 'Cricketer'}</p>
                      <span className={`auct-value auct-value-${valueHint(currentLot).tone}`}>
                        {valueHint(currentLot).label}
                      </span>
                    </div>
                  </div>
                  <div className="auct-ratings">
                    <div className="auct-rating">
                      <span><small>BAT RATING</small><b>{batOf(currentLot)}</b></span>
                      <i><em style={{ width: `${Math.min(100, batOf(currentLot))}%` }} /></i>
                    </div>
                    <div className="auct-rating bowl">
                      <span><small>BOWL RATING</small><b>{bowlOf(currentLot)}</b></span>
                      <i><em style={{ width: `${Math.min(100, bowlOf(currentLot))}%` }} /></i>
                    </div>
                  </div>
                </article>
              ) : (
                <Panel title="Auction" subtitle="Waiting for the next lot" icon="🔨">
                  <Empty title="No lot on the block" text="Press NEXT when the result panel appears." />
                </Panel>
              )}

              <section className="auct-bid-panel panel">
                <header className="auct-bid-head">
                  <span className="auct-kicker">SEALED BID</span>
                  <span className="auct-balance">YOUR BALANCE <b>{fc.toLocaleString()} FC</b></span>
                </header>
                {bidPlaced ? (
                  <div className="auct-bid-wait">
                    <strong>✓ Bid in — waiting for others</strong>
                    <small>Your sealed bid: {myBidAmount} FC. Rival amounts stay hidden until the result.</small>
                  </div>
                ) : awaitingNext ? (
                  <div className="auct-bid-wait">
                    <strong>Lot resolved — press NEXT LOT</strong>
                    <small>The next cricketer is ready when everyone advances.</small>
                  </div>
                ) : (
                  <div className="auct-bid-controls">
                    <div className="auct-quick-bids">
                      {QUICK_BIDS.map(amount => (
                        <button key={amount} type="button" disabled={amount > fc}
                          onClick={() => submitBid(amount)}>
                          {amount === 0 ? 'PASS' : `${amount}`}
                        </button>
                      ))}
                    </div>
                    <div className="auct-slider-row">
                      <input type="range" min={0} max={Math.max(25, fc)} step={25}
                        value={Math.min(bidAmount, Math.max(25, fc))}
                        onChange={event => setBidAmount(num(event.target.value))} />
                      <span>{Math.min(bidAmount, Math.max(0, fc))} FC</span>
                    </div>
                    <div className="auct-custom-row">
                      <label className="field">
                        <span>Custom bid (0 = pass)</span>
                        <input type="number" min={0} max={fc} value={bidAmount}
                          onChange={event => setBidAmount(num(event.target.value))} />
                      </label>
                      <Button variant="gold" onClick={() => submitBid(bidAmount)} disabled={fc <= 0}>
                        BID NOW
                      </Button>
                    </div>
                    <small className="auct-fine">Highest sealed bid wins and pays the FC. Ties go to the earlier manager in rotation.</small>
                  </div>
                )}
                {rivals.length > 0 && (
                  <div className="auct-rivals">
                    {rivals.map(rival => (
                      <span key={rival.pid} title={`${rival.name}: ${rival.bid ? 'bid in' : 'passed'}`}>
                        <i style={{ background: rival.color }} />
                        {rival.name}: <b>{rival.bid ? 'bid in' : '—'}</b>
                      </span>
                    ))}
                  </div>
                )}
              </section>

              {(resultLot || awaitingNext) && (
                <section className="auct-result panel">
                  <span className="auct-kicker">LOT RESULT</span>
                  <h3>
                    {lotWinnerName ? `${lotWinnerName} wins the lot` : 'No sale — lot unsold'}
                    {winningBid > 0 && <em> · {winningBid.toLocaleString()} FC</em>}
                  </h3>
                  <div className="auct-reveal-list">
                    {revealed.length === 0 ? (
                      <small>Bids are revealed in the room result.</small>
                    ) : revealed.map((row, index) => (
                      <div key={`${row.pid}-${index}`} className={row.pid === lotWinnerId ? 'is-winner' : ''}>
                        <span><i style={{ background: row.color }} />{index + 1}. {row.name}</span>
                        <b>{row.amount > 0 ? `${row.amount.toLocaleString()} FC` : 'PASS'}</b>
                      </div>
                    ))}
                  </div>
                  <Button variant="gold" className="auct-next-button"
                    onClick={() => send('next', {})}>NEXT LOT →</Button>
                </section>
              )}

              <SquadStrip
                squad={Array.isArray(myFranchise?.squad) ? myFranchise!.squad : []}
                captain={myFranchise?.captain || null}
                playerMap={playerMap}
                onCaptain={playerId => send('set_captain', { player_id: playerId })}
              />
            </>
          )}

          {state?.started && isTournament && (
            <>
              <section className="auct-fixtures panel">
                <header className="auct-section-head">
                  <div><span className="auct-kicker">ROUND ROBIN</span><h3>Fixtures</h3></div>
                  <small>Every manager plays every other manager once</small>
                </header>
                {fixtures.length === 0 ? (
                  <Empty title="Fixtures loading" text="The tournament schedule arrives with the snapshot." />
                ) : (
                  <div className="auct-fixture-list">
                    {fixtures.map(fixture => (
                      <div key={fixture.key}
                        className={`auct-fixture ${fixture.played ? 'is-played' : ''} ${fixture.next ? 'is-next' : ''}`}>
                        <span className="auct-fixture-mark">
                          {fixture.played ? '✓' : fixture.next ? '▶' : String(fixture.key + 1).padStart(2, '0')}
                        </span>
                        <span className="auct-fixture-team">
                          <i style={{ background: franchises[fixture.a]?.color || '#4a6780' }} />
                          {nameOf(fixture.a)}
                        </span>
                        <em>vs</em>
                        <span className="auct-fixture-team">
                          <i style={{ background: franchises[fixture.b]?.color || '#4a6780' }} />
                          {nameOf(fixture.b)}
                        </span>
                        <small>{fixture.next ? 'NEXT' : fixture.played ? 'PLAYED' : 'UPCOMING'}{fixture.label ? ` · ${fixture.label}` : ''}</small>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              <section className="auct-setup panel">
                <header className="auct-section-head">
                  <div><span className="auct-kicker">MATCH PLAN</span><h3>Tactic &amp; captain</h3></div>
                  <small>
                    {currentFixture
                      ? `Up next: ${nameOf(currentFixture.a)} vs ${nameOf(currentFixture.b)}`
                      : 'Set your plan before the next match'}
                  </small>
                </header>
                <div className="auct-tactic-grid">
                  {TACTICS.map(tactic => (
                    <button key={tactic.id} type="button"
                      className={`auct-tactic ${currentTactic === tactic.id ? 'is-active' : ''}`}
                      onClick={() => send('set_tactic', { tactic: tactic.id })}>
                      <span>{tactic.icon}</span>
                      <strong>{tactic.label}</strong>
                      <small>{tactic.runs}</small>
                      <small>{tactic.wickets}</small>
                    </button>
                  ))}
                </div>
                <label className="field auct-captain-field">
                  <span>Captain — BAT counts double, BOWL adds to your attack</span>
                  <select value={myFranchise?.captain || ''}
                    onChange={event => send('set_captain', { player_id: event.target.value })}
                    disabled={!Array.isArray(myFranchise?.squad) || myFranchise!.squad.length === 0}>
                    <option value="">Choose a captain</option>
                    {(myFranchise?.squad || []).map(playerId => (
                      <option key={playerId} value={playerId}>
                        {playerMap.get(playerId)?.name || playerId} · BAT {batOf(playerMap.get(playerId))}
                      </option>
                    ))}
                  </select>
                </label>
              </section>

              {resultMatch && (
                <section className="auct-scorecard panel">
                  <header className="auct-section-head">
                    <div><span className="auct-kicker">MATCH RESULT</span><h3>{matchWinnerName ? `${matchWinnerName} takes the points` : 'Match complete'}</h3></div>
                    <small>Scores are calculated from real BAT / BOWL ratings</small>
                  </header>
                  <div className="auct-score-grid">
                    {scores.length === 0 && <Empty title="Scorecard loading" text="Both scores arrive with the match result." />}
                    {scores.map((row, index) => (
                      <article key={`${row.pid}-${index}`} className={`auct-score-side ${row.pid === matchWinnerId ? 'is-winner' : ''}`}
                        style={{ '--team': row.color } as React.CSSProperties}>
                        <header>{row.name}{row.pid === matchWinnerId && <b>WIN</b>}</header>
                        <div className="auct-score-big">{row.score.toLocaleString()}</div>
                        <small>FINAL SCORE</small>
                        <div className="auct-score-lines">
                          <span><em>Runs</em><b>{row.runs}</b></span>
                          <span><em>Wickets</em><b>{row.wickets}</b></span>
                          <span><em>Top BAT</em><b>{row.topBat}</b></span>
                          <span><em>Captain bonus</em><b>{row.captain}</b></span>
                          <span><em>Tactic</em><b>{row.tactic}</b></span>
                        </div>
                      </article>
                    ))}
                  </div>
                  <Button variant="gold" className="auct-next-button" onClick={() => send('next', {})}>
                    NEXT MATCH →
                  </Button>
                </section>
              )}

              <Button variant="gold" className="auct-play-next" onClick={() => send('next', {})}>
                {resultMatch ? 'CONTINUE TOURNAMENT →' : '▶ PLAY NEXT MATCH'}
              </Button>

              <SquadStrip
                squad={Array.isArray(myFranchise?.squad) ? myFranchise!.squad : []}
                captain={myFranchise?.captain || null}
                playerMap={playerMap}
                onCaptain={playerId => send('set_captain', { player_id: playerId })}
              />
            </>
          )}

          {state?.started && !isAuction && !isTournament && !isOver && (
            <Panel title="Getting ready" subtitle="Waiting for the host" icon="⏳">
              <Empty title="Auction starting soon" text="The first lot appears when the room begins." />
            </Panel>
          )}
        </div>

        <aside className="auct-side">
          <Panel title="Standings" subtitle="Points decide the cup · score breaks ties" icon="🏆" className="auct-standings">
            <div className="auct-table-scroll">
              <table className="data-table auct-table">
                <thead>
                  <tr><th>#</th><th>Manager</th><th>Pts</th><th>Score</th><th>W</th><th>Sq</th><th>FC</th></tr>
                </thead>
                <tbody>
                  {standings.map(row => (
                    <tr key={row.id} className={row.id === you ? 'mine' : ''}>
                      <td><span className={`rank ${num(row.rank) === 1 ? 'rank-1' : ''}`}>{num(row.rank) || '—'}</span></td>
                      <td><span className="team-color" style={{ background: row.color }} />{row.name}</td>
                      <td><b>{num(row.points)}</b></td>
                      <td>{num(row.total_score).toLocaleString()}</td>
                      <td>{num(row.wins)}</td>
                      <td>{num(row.squad_size)}</td>
                      <td>{num(row.fc).toLocaleString()}</td>
                    </tr>
                  ))}
                  {standings.length === 0 && (
                    <tr><td colSpan={7}><Empty title="No standings yet" text="Join a room to see the table." /></td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title="Latest" subtitle="Room activity" icon="📢" className="auct-activity">
            {activity.length === 0 ? (
              <Empty title="Quiet so far" text="Bids and results appear here." />
            ) : (
              <div className="auct-activity-list">
                {activity.map((entry, index) => (
                  <div key={`${entry.text}-${index}`} className="auct-activity-row">
                    <span>◆</span><p>{entry.text}</p>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </aside>
      </main>

      {helpOpen && <AuctionHelpModal onClose={() => setHelpOpen(false)} />}
      {!app.session && <AuctionLandingModal />}
      {app.session && !state && (
        <Modal title="Auction + Tournament" subtitle="Loading your room…" onClose={() => {}}>
          <Empty title="Connecting to the room" text="The auction appears as soon as the lobby snapshot loads." />
        </Modal>
      )}
      {app.session && lobby && <AuctionLobbyModal lobby={lobby} />}
      {app.session && state && isOver && (
        <AuctionFinishModal state={state} standings={standings}
          canRestart={app.session.playerId === state.host_id}
          onRestart={() => send('restart', {})} />
      )}
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Help                                                                       */
/* -------------------------------------------------------------------------- */

function AuctionHelpModal({ onClose }: { onClose: () => void }) {
  return (
    <Modal title="How to play" subtitle="Auction + Tournament in six lines" width="660px" onClose={onClose}>
      <ol className="auct-help-list">
        {HELP_LINES.map(line => <li key={line}>{line}</li>)}
      </ol>
      <div className="auct-help-foot">
        <small>Virtual FC only. No deposits, wagering, photos, logos or league branding — player names are factual data.</small>
      </div>
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */
/* Landing                                                                    */
/* -------------------------------------------------------------------------- */

function AuctionLandingModal() {
  const { app, create, join, quick, continueRoom, dispatch, refreshSaved, joinCode } = useApp()
  const [tab, setTab] = useState<'new' | 'join' | 'quick'>(() => joinCode ? 'join' : 'new')
  const [name, setName] = useState(() => localStorage.getItem('fg-name') || 'Manager')
  const [avatar, setAvatar] = useState(() => localStorage.getItem('fg-avatar') || '🦁')
  const [color, setColor] = useState(() => localStorage.getItem('fg-color') || '#c8a24b')
  const [code, setCode] = useState(() => joinCode || '')
  const [budget, setBudget] = useState(1200)
  const [lots, setLots] = useState(18)
  const [maxPlayers, setMaxPlayers] = useState(4)
  const [difficulty, setDifficulty] = useState('medium')

  const profile = { name: name.trim() || 'Manager', avatar, color }
  const settings = {
    ruleset: 7,
    game: 'auction-tournament',
    budget,
    lots,
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
    <Modal title="Auction + Tournament" subtitle="Draft real cricketers. Pick a captain. Win the cup." width="940px"
      onClose={() => {}}>
      <div className="auct-landing-grid">
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
            <input value={name} maxLength={24} onChange={event => setName(event.target.value)}
              placeholder="Your manager name" />
          </label>
          <Tabs active={tab} onChange={switchTab} tabs={[
            { id: 'new', label: 'New room' },
            { id: 'join', label: 'Join code' },
            { id: 'quick', label: 'Quick play' },
          ]} />

          {tab === 'new' && (
            <div className="auct-settings-grid">
              <label className="field"><span>Starting budget</span>
                <select value={budget} onChange={event => setBudget(Number(event.target.value))}>
                  {BUDGET_OPTIONS.map(option => <option key={option} value={option}>{option} FC</option>)}
                </select>
              </label>
              <label className="field"><span>Auction lots</span>
                <select value={lots} onChange={event => setLots(Number(event.target.value))}>
                  {LOT_OPTIONS.map(option => <option key={option} value={option}>{option} players</option>)}
                </select>
              </label>
              <label className="field"><span>Max players</span>
                <select value={maxPlayers} onChange={event => setMaxPlayers(Number(event.target.value))}>
                  {PLAYER_OPTIONS.map(option => <option key={option} value={option}>{option} managers</option>)}
                </select>
              </label>
              <label className="field"><span>AI difficulty</span>
                <select value={difficulty} onChange={event => setDifficulty(event.target.value)}>
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
                  <p>Enter your manager name and join with this code. Code-only invites — no URLs or logins.</p>
                </div>
              )}
              <label className="field">
                <span>Room code</span>
                <input className="code-input" value={code} maxLength={8} placeholder="ABCDE"
                  onChange={event => setCode(event.target.value.toUpperCase())} />
              </label>
            </>
          )}

          {tab === 'quick' && (
            <div className="callout">
              <strong>Instant draft</strong>
              <p>Three managers, {lots} lots, {budget} FC and two bot rivals. Straight into the auction.</p>
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

        <Panel title="Continue a saved room" subtitle="Progress is saved on the server" icon="💾"
          action={<Button variant="subtle" small onClick={refreshSaved}>Refresh</Button>}>
          {app.saved.length === 0 ? (
            <div className="empty"><span>💾</span><strong>No saved rooms yet</strong>
              <p>Create a room and it will appear here.</p></div>
          ) : (
            <div className="saved-list">
              {app.saved.slice(0, 8).map(row => (
                <button key={row.room_id} type="button" className="saved-row" onClick={() => continueRoom(row)}>
                  <span className="saved-icon">{row.finished ? '🏆' : '🏏'}</span>
                  <span className="saved-info">
                    <strong>{row.winner_name || row.franchises.join(' vs ') || row.code}</strong>
                    <small>{row.code} · {row.franchises.length} managers</small>
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

function AuctionLobbyModal({ lobby }: { lobby: AuctionTournamentLobby }) {
  const { app, send, dispatch } = useApp()
  const [count, setCount] = useState(2)
  const [copied, setCopied] = useState(false)
  const members: LobbyMember[] = Array.isArray(lobby.members)
    ? lobby.members
    : Object.values((lobby.members || {}) as unknown as Record<string, LobbyMember>)
  const isHost = lobby.host_id === app.session?.playerId
    || members.some(member => member.is_host && member.id === app.session?.playerId)
  const budget = num(lobby.settings?.budget) || 1200
  const lots = num(lobby.settings?.lots) || 18
  const maxPlayers = num(lobby.settings?.max_players) || 4
  const difficulty = txt(lobby.settings?.difficulty || lobby.settings?.ai_difficulty || 'medium')
  const settings = {
    ruleset: 7,
    game: 'auction-tournament',
    budget,
    lots,
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
    <Modal title="Auction lobby" subtitle="Invite managers, add bots, then start the draft" width="900px"
      onClose={() => {}}>
      <div className="auct-lobby-grid">
        <Panel title="Managers" subtitle={`${members.length}/${maxPlayers} seats filled`} icon="🏏">
          <div className="auct-code-display">
            <small>ROOM CODE</small>
            <strong>{lobby.code}</strong>
            <span>Share the code only — no URLs or logins needed.</span>
            <Button variant="subtle" small onClick={copyCode}>{copied ? '✓ Copied code' : 'Copy code'}</Button>
          </div>
          <div className="member-list">
            {members.map(member => (
              <div key={member.id} className="member-row">
                <span className="auct-lobby-avatar"
                  style={{ '--auct-color': member.color || '#c8a24b' } as React.CSSProperties}>
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

        <Panel title="Host settings" subtitle={isHost ? 'Only you can edit these' : 'Waiting for the host'} icon="⚙️">
          <div className="auct-settings-grid">
            <label className="field"><span>Starting budget</span>
              <select disabled={!isHost} value={budget}
                onChange={event => patch({ budget: Number(event.target.value) })}>
                {BUDGET_OPTIONS.map(option => <option key={option} value={option}>{option} FC</option>)}
              </select>
            </label>
            <label className="field"><span>Auction lots</span>
              <select disabled={!isHost} value={lots}
                onChange={event => patch({ lots: Number(event.target.value) })}>
                {LOT_OPTIONS.map(option => <option key={option} value={option}>{option} players</option>)}
              </select>
            </label>
            <label className="field"><span>Max players</span>
              <select disabled={!isHost} value={maxPlayers}
                onChange={event => patch({ max_players: Number(event.target.value) })}>
                {PLAYER_OPTIONS.map(option => <option key={option} value={option}>{option} managers</option>)}
              </select>
            </label>
            <label className="field"><span>AI difficulty</span>
              <select disabled={!isHost} value={difficulty}
                onChange={event => patch({ difficulty: event.target.value, ai_difficulty: event.target.value })}>
                <option value="easy">Easy</option>
                <option value="medium">Medium</option>
                <option value="hard">Hard</option>
              </select>
            </label>
          </div>
          <div className="bot-setup">
            <label className="field"><span>How many bots?</span>
              <input type="number" min={1} max={Math.max(1, maxPlayers - members.length)} value={count}
                onChange={event => setCount(Math.max(1, Math.min(maxPlayers, num(event.target.value))))} />
            </label>
            <Button variant="subtle" block disabled={!isHost || members.length >= maxPlayers}
              onClick={() => send('bots', { count, difficulty })}>＋ Add bots</Button>
          </div>
          {isHost && (
            <div className="start-block">
              {members.length < 2 && <small>Add at least one more manager or bot.</small>}
              <Button variant="gold" block disabled={members.length < 2} onClick={() => send('start', {})}>
                🔨 Start auction
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

function AuctionFinishModal({ state, standings, canRestart, onRestart }: {
  state: AuctionTournamentState
  standings: AuctionTournamentStanding[]
  canRestart: boolean
  onRestart: () => void
}) {
  const championId = txt(state.winner_id) || standings[0]?.id || ''
  const champion = standings.find(row => row.id === championId)
    || (championId ? state.franchises?.[championId] : undefined)
  const championName = champion?.name || 'Champion'
  const championPoints = champion ? num((champion as { points?: number }).points) : 0

  return (
    <Modal title="Tournament complete" subtitle="Most points takes the cup" width="760px" onClose={() => {}}>
      <div className="auct-champion">
        <span>🏆</span>
        <small>CUP WINNER</small>
        <h2>{championName}</h2>
        <p>{championPoints} points · {champion ? num((champion as { total_score?: number }).total_score).toLocaleString() : 0} total score</p>
      </div>
      <div className="auct-table-scroll">
        <table className="data-table auct-table">
          <thead>
            <tr><th>#</th><th>Manager</th><th>Pts</th><th>Score</th><th>W</th><th>L</th><th>Sq</th><th>FC</th></tr>
          </thead>
          <tbody>
            {standings.map(row => (
              <tr key={row.id} className={row.id === championId ? 'champion' : ''}>
                <td><span className={`rank ${num(row.rank) === 1 ? 'rank-1' : ''}`}>{num(row.rank) || '—'}</span></td>
                <td><span className="team-color" style={{ background: row.color }} />{row.name}</td>
                <td><b>{num(row.points)}</b></td>
                <td>{num(row.total_score).toLocaleString()}</td>
                <td>{num(row.wins)}</td>
                <td>{num(row.losses)}</td>
                <td>{num(row.squad_size)}</td>
                <td>{num(row.fc).toLocaleString()}</td>
              </tr>
            ))}
            {standings.length === 0 && (
              <tr><td colSpan={8}><Empty title="No final table" text="Standings arrive with the final snapshot." /></td></tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="auct-modal-foot">
        <small>{canRestart ? 'Play again starts a fresh auction for every manager.'
          : 'Only the host can start a new auction.'}</small>
        <Button variant="gold" onClick={onRestart} disabled={!canRestart}>Play again</Button>
      </div>
    </Modal>
  )
}
