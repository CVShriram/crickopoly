import React, { useEffect, useMemo, useState } from 'react'
import { useApp } from '../store'
import { Badge, Button, Empty, Panel, PlayerPortrait, Stat } from '../components/UI'
import { money, playerLabel, timeAgo } from '../utils'

export function Auctions() {
  const { app, send } = useApp()
  const state = app.state!
  const f = state.you ? state.franchises?.[state.you] : undefined
  const auction = state.auction
  const [amount, setAmount] = useState(0)
  const [candidate, setCandidate] = useState('')
  const [base, setBase] = useState(50)
  const [kind, setKind] = useState<'market' | 'mega'>('market')

  const currentPlayer = auction?.players?.[auction.index || 0]
  const player = state.gamedata?.players?.find(p => p.id === currentPlayer)
  const minBid = auction ? (auction.highest_bidder ? auction.current_bid + 10 : auction.base_price) : 0
  const highest = auction?.highest_bidder ? state.franchises?.[auction.highest_bidder] : undefined
  const passed = Boolean(auction?.passed?.includes(state.you))
  const alreadyHighest = auction?.highest_bidder === state.you
  const squadCap = state.gamedata?.rules?.squad_capacity || 15
  const squadFull = Object.keys(f?.squad || {}).length >= squadCap
  const isParticipant = Boolean(auction?.participants?.includes(state.you))
  const canBid = auction && isParticipant && !squadFull && !passed && !alreadyHighest
    && (f?.balance || 0) >= amount && amount >= minBid

  useEffect(() => { setAmount(minBid || 0) }, [minBid, auction?.id, currentPlayer])

  const unsigned = useMemo(() => {
    const signed = new Set(Object.values(state.franchises).flatMap(x => Object.keys(x.squad)))
    return (state.gamedata?.players || []).filter(p => !signed.has(p.id)).slice(0, 48)
  }, [state.franchises, state.gamedata])

  const history = Object.values(state.auctions || {}).slice().reverse()

  return (
    <div className="page auctions-page">
      <div className="page-head">
        <div><small>PLAYER EXCHANGE</small><h1>Auction room</h1>
          <p>Bid with FC, pass to sit out a lot, and let the server settle every contract atomically.</p></div>
        <Badge tone={auction ? 'danger' : 'green'} icon="🔨">{auction ? 'LOT LIVE' : 'ROOM OPEN'}</Badge>
      </div>

      <div className="dashboard-strip compact">
        <Stat label="Your balance" value={money(f?.balance)} tone="gold" icon="💰" />
        <Stat label="Lots opened" value={Object.keys(state.auctions || {}).length} icon="🔨" />
        <Stat label="Your squad" value={`${Object.keys(f?.squad || {}).length}/15`} icon="👥" />
        <Stat label="Current bid" value={money(auction?.current_bid || 0)} tone="danger" icon="💹" />
      </div>

      {auction ? (
        <div className="auction-layout">
          <Panel className="auction-stage" title={`${auction.kind.toUpperCase()} AUCTION`}
            subtitle={`Lot ${auction.index + 1} of ${auction.players.length}`} icon="🔨"
            action={<Badge tone="danger" icon="⏱️">Live</Badge>}>
            <div className="lot-card">
              <PlayerPortrait player={player} size="lg" />
              <div className="lot-info">
                <small>{player ? `${player.flag} ${player.country} · ${player.role} · ${player.tier}` : currentPlayer}</small>
                <h2>{player?.name || currentPlayer}</h2>
                <div className="lot-ratings">
                  <span>OVR <b>{player?.overall || '—'}</b></span>
                  <span>BAT <b>{player?.batting || '—'}</b></span>
                  <span>BOWL <b>{player?.bowling || '—'}</b></span>
                  <span>FORM <b>{player?.form || '—'}</b></span>
                  <span>VALUE <b>{player?.value || '—'}</b></span>
                </div>
              </div>
              <div className="lot-price">
                <small>HIGHEST BID</small>
                <strong>{money(auction.current_bid)}</strong>
                <span>{highest ? `${highest.avatar} ${highest.name}` : 'No bids yet'}</span>
              </div>
            </div>

            <div className="bid-panel">
              <div><small>MINIMUM BID</small><strong>{money(minBid)}</strong></div>
              <div className="bid-actions">
                <button type="button" onClick={() => setAmount(Math.max(minBid, amount - 10))}>−</button>
                <input type="number" min={minBid} value={amount} onChange={e => setAmount(Number(e.target.value))} />
                <button type="button" onClick={() => setAmount(amount + 10)}>＋</button>
                <Button variant="gold" disabled={!canBid} onClick={() => send('bid', { amount })}>Place bid</Button>
                <Button variant="subtle" disabled={passed || !isParticipant} onClick={() => send('pass', {})}>{passed ? 'Passed' : 'Pass lot'}</Button>
              </div>
              {(squadFull || !isParticipant || alreadyHighest || passed || (f?.balance || 0) < minBid) && <p className="bid-warning">
                {squadFull ? 'Your squad is full — release a player before bidding.'
                  : !isParticipant ? 'You are not bidding in this lot.'
                    : alreadyHighest ? 'You hold the highest bid.'
                      : passed ? 'You have passed this lot.' : 'Insufficient FC to bid.'}
              </p>}
            </div>

            <div className="bid-history">
              <h3>Bid history</h3>
              {auction.bids.length === 0 ? <Empty title="No bids yet" /> : [...auction.bids].reverse().map((b: any, i: number) => (
                <div key={i} className="bid-row"><span>{state.franchises?.[b.fid]?.avatar} {state.franchises?.[b.fid]?.name}</span>
                  <strong>{money(b.amount)}</strong><small>{timeAgo(b.ts)}</small></div>
              ))}
            </div>
          </Panel>

          <Panel title="Participants" subtitle="Passed managers cannot re-enter this lot" icon="👥">
            <div className="participant-list">
              {auction.participants.map((id: string) => {
                const fr = state.franchises?.[id]
                const isPassed = auction.passed.includes(id)
                return <div key={id} className={`participant ${isPassed ? 'passed' : ''}`}>
                  <span style={{ background: fr?.color }}>{fr?.avatar}</span>
                  <div><strong>{fr?.name}</strong><small>{money(fr?.balance)}</small></div>
                  {auction.highest_bidder === id && <Badge tone="gold">LEADING</Badge>}
                  {isPassed && <Badge>PASSED</Badge>}
                </div>
              })}
            </div>
          </Panel>
        </div>
      ) : (
        <Panel title="Open a scouting auction" subtitle="List an unsigned cricketer and set the opening price" icon="📢">
          <div className="open-auction-form">
            <label className="field"><span>Auction type</span>
              <select value={kind} onChange={e => setKind(e.target.value as any)}>
                <option value="market">Market auction</option><option value="mega">Mega auction</option>
              </select>
            </label>
            <label className="field"><span>Player</span>
              <select value={candidate} onChange={e => setCandidate(e.target.value)}>
                <option value="">Choose an unsigned player…</option>
                {unsigned.map(p => <option key={p.id} value={p.id}>{p.flag} {p.name} · {p.role} · OVR {p.overall}</option>)}
              </select>
            </label>
            <label className="field"><span>Base price (FC)</span>
              <input type="number" min={20} step={10} value={base} onChange={e => setBase(Number(e.target.value))} />
            </label>
            <Button variant="gold" disabled={!candidate || base < 20} onClick={() => { send('auction', { kind, player_ids: [candidate], base_price: base }); setCandidate('') }}>
              🔨 Open auction
            </Button>
          </div>
        </Panel>
      )}

      <Panel title="Completed lots" subtitle="Every auction keeps a full history" icon="📜">
        {history.length === 0 ? <Empty title="No auctions yet" /> : (
          <div className="auction-history">
            {history.map((a: any) => <div key={a.id} className="auction-history-row">
              <strong>{a.kind.toUpperCase()}</strong>
              <span>{a.players.map((id: string) => playerLabel(state, id)).join(', ')}</span>
              <small>{a.history?.length || 0} lots · {timeAgo(a.created_at)}</small>
            </div>)}
          </div>
        )}
      </Panel>
    </div>
  )
}
