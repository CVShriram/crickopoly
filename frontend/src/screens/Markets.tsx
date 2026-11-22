import React, { useMemo, useState } from 'react'
import { useApp } from '../store'
import type { Franchise, Trade } from '../types'
import { Badge, Button, Empty, Modal, Panel, PlayerPortrait, Stat, Tabs } from '../components/UI'
import { money, ownerName, titleCase } from '../utils'

type Bundle = { players: string[]; stadiums: number[]; sponsors: string[]; cards: string[]; cash: number }
const emptyBundle = (): Bundle => ({ players: [], stadiums: [], sponsors: [], cards: [], cash: 0 })

export function Markets() {
  const { app, send } = useApp()
  const state = app.state!
  const f = state.you ? state.franchises[state.you] : undefined
  const [tab, setTab] = useState('portfolio')
  const [to, setTo] = useState('')
  const [give, setGive] = useState<Bundle>(emptyBundle())
  const [want, setWant] = useState<Bundle>(emptyBundle())
  const [message, setMessage] = useState('')
  const [upgradePos, setUpgradePos] = useState<number | null>(null)

  const offers = (state.trade_offers || []) as Trade[]
  const incoming = offers.filter(t => t.to === state.you && t.status === 'pending')
  const outgoing = offers.filter(t => t.from === state.you && t.status === 'pending')
  const history = offers.filter(t => t.status !== 'pending')
  const windowInfo = state.transfer_window
  const rivals = Object.values(state.franchises).filter(x => x.id !== state.you)
  const target: Franchise | undefined = state.franchises[to]
  const ownerMarkets = (state.board || []).filter(t => t.kind === 'market' && state.ownership?.[String(t.position)] === state.you)
  const ownerVenues = (state.board || []).filter(t => t.kind === 'stadium' && state.ownership?.[String(t.position)] === state.you)
  const sponsorRows = (state.gamedata?.sponsors || []).map((s: any) => ({ ...s, signed: f?.sponsors?.includes(s.id) }))
  const cardRows = (f?.cards || []).map(id => state.gamedata?.tactical_cards?.[id]).filter(Boolean)
  const squadRows = useMemo(() => Object.keys(f?.squad || {}).map(id => ({
    id, player: state.gamedata?.players?.find(p => p.id === id),
  })).filter(x => x.player), [f, state.gamedata])

  const toggle = (bundle: Bundle, key: keyof Bundle, value: any, setter: (b: Bundle) => void) => {
    const current = bundle[key] as any[]
    const exists = current.includes(value)
    setter({ ...bundle, [key]: exists ? current.filter(x => x !== value) : [...current, value] } as Bundle)
  }

  const submitOffer = () => send('trade_offer', {
    to, give, want, message,
  })

  const renderBundle = (bundle: Bundle, owner?: Franchise, side: 'give' | 'want' = 'give') => (
    <div className="bundle-card">
      <h4>{side === 'give' ? 'You offer' : `You request from ${owner?.name || 'rival'}`}</h4>
      <label className="field"><span>FC</span>
        <input type="number" min={0} max={owner?.balance || f?.balance || 0} value={bundle.cash}
          onChange={e => setterFor(side)({ ...bundle, cash: Math.max(0, Number(e.target.value) || 0) })} />
      </label>
      <div className="bundle-list">
        {bundle.players.map(id => <Badge key={id} tone="blue" icon="🏏">
          {state.gamedata?.players?.find(p => p.id === id)?.name || id}
          <button type="button" onClick={() => toggle(bundle, 'players', id, setterFor(side))}>×</button>
        </Badge>)}
        {bundle.stadiums.map(pos => <Badge key={pos} tone="gold" icon="🏟️">
          {state.board?.[pos]?.short || `Tile ${pos}`}
          <button type="button" onClick={() => toggle(bundle, 'stadiums', pos, setterFor(side))}>×</button>
        </Badge>)}
        {bundle.sponsors.map(id => <Badge key={id} tone="green" icon="🤝">
          {titleCase(id)}
          <button type="button" onClick={() => toggle(bundle, 'sponsors', id, setterFor(side))}>×</button>
        </Badge>)}
        {bundle.cards.map(id => <Badge key={id} tone="gold" icon="🧠">
          {state.gamedata?.tactical_cards?.[id]?.name || id}
          <button type="button" onClick={() => toggle(bundle, 'cards', id, setterFor(side))}>×</button>
        </Badge>)}
      </div>
      <div className="asset-picker">
        <select value="" onChange={e => e.target.value && toggle(bundle, 'players', e.target.value, setterFor(side))}>
          <option value="">＋ Player contract</option>
          {(side === 'give' ? squadRows.map(x => x.id) : Object.keys(target?.squad || {})).map(id =>
            <option key={id} value={id}>{state.gamedata?.players?.find(p => p.id === id)?.name || id}</option>)}
        </select>
        <select value="" onChange={e => e.target.value && toggle(bundle, 'stadiums', Number(e.target.value), setterFor(side))}>
          <option value="">＋ Stadium</option>
          {Object.keys(side === 'give' ? (f?.stadiums || {}) : (target?.stadiums || {})).map(pos =>
            <option key={pos} value={pos}>{state.board?.[Number(pos)]?.short || `Tile ${pos}`}</option>)}
        </select>
        {side === 'give' && <select value="" onChange={e => e.target.value && toggle(bundle, 'sponsors', e.target.value, setterFor(side))}>
          <option value="">＋ Sponsor</option>
          {f?.sponsors?.map(id => <option key={id} value={id}>{titleCase(id)}</option>)}
        </select>}
        {side === 'give' && <select value="" onChange={e => e.target.value && toggle(bundle, 'cards', e.target.value, setterFor(side))}>
          <option value="">＋ Tactical card</option>
          {f?.cards?.map(id => <option key={id} value={id}>{state.gamedata?.tactical_cards?.[id]?.name || id}</option>)}
        </select>}
      </div>
    </div>
  )

  const setterFor = (side: 'give' | 'want') => side === 'give' ? setGive : setWant

  return (
    <div className="page markets-page">
      <div className="page-head">
        <div><small>PORTFOLIO & EXCHANGE</small><h1>Markets, venues & trades</h1>
          <p>Own all four roles in a country for a collection bonus, develop stadiums and trade with rivals.</p></div>
        <Badge tone={windowInfo?.open ? 'green' : 'danger'} icon="🤝">
          {windowInfo?.open ? 'Transfer window open' : `Opens round ${windowInfo?.next_round}`}
        </Badge>
      </div>

      <div className="dashboard-strip compact">
        <Stat label="Liquid FC" value={money(f?.balance)} tone="gold" icon="💰" />
        <Stat label="Markets" value={`${ownerMarkets.length}/32`} icon="🌍" />
        <Stat label="Stadiums" value={`${ownerVenues.length}/8`} icon="🏟️" />
        <Stat label="Sponsors" value={`${f?.sponsors?.length || 0}/4`} tone="green" icon="🤝" />
        <Stat label="Pending offers" value={incoming.length} tone={incoming.length ? 'danger' : 'default'} icon="📨" />
      </div>

      <Tabs active={tab} onChange={setTab} tabs={[
        { id: 'portfolio', label: 'Portfolio', icon: '🏟️' },
        { id: 'sponsors', label: 'Sponsors', icon: '🤝' },
        { id: 'trades', label: 'Trade desk', icon: '🔄', count: incoming.length || undefined },
        { id: 'history', label: 'History', icon: '📜' },
      ]} />

      {tab === 'portfolio' && (
        <div className="portfolio-grid">
          <Panel title="Player markets" subtitle="Country role monopolies pay collection bonuses" icon="🌍">
            {ownerMarkets.length === 0 ? <Empty title="No markets owned" text="Land on a market tile and buy it." /> : (
              <div className="asset-grid">
                {ownerMarkets.map(t => (
                  <div key={t.position} className="asset-card">
                    <span>{t.icon}</span><strong>{t.name}</strong>
                    <small>{ownerName(state, state.you)} · {money(t.price)}</small>
                  </div>
                ))}
              </div>
            )}
          </Panel>
          <Panel title="Stadiums" subtitle="Upgrade venues for revenue, recovery and home advantage" icon="🏟️">
            {ownerVenues.length === 0 ? <Empty title="No stadiums owned" text="Buy a venue when you land on it." /> : (
              <div className="venue-list">
                {ownerVenues.map(t => (
                  <div key={t.position} className="venue-row">
                    <div><strong>{t.name}</strong><small>{t.pitch ? (state.gamedata?.pitches?.[t.pitch]?.name || t.pitch) : '—'} · {money(t.match_revenue)}/round</small></div>
                    <div className="chip-row">{(f?.stadiums?.[String(t.position)] || []).map(u =>
                      <Badge key={u} tone="blue">{state.gamedata?.stadium_upgrades?.[u]?.name || u}</Badge>)}</div>
                    <Button variant="subtle" small onClick={() => setUpgradePos(t.position)}>Upgrade</Button>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>
      )}

      {tab === 'sponsors' && (
        <Panel title="Sponsorship portfolio" subtitle="Contracts pay every completed board round" icon="🤝">
          <div className="sponsor-grid">
            {sponsorRows.map((s: any) => (
              <div key={s.id} className={`sponsor-card ${s.signed ? 'signed' : ''}`}>
                <span className="sponsor-icon">{s.icon}</span>
                <strong>{s.name}</strong>
                <small>{money(s.per_round)} / round · +{s.reputation} reputation</small>
                <Badge tone={s.signed ? 'green' : 'default'}>{s.signed ? 'SIGNED' : 'AVAILABLE'}</Badge>
              </div>
            ))}
          </div>
        </Panel>
      )}

      {tab === 'trades' && (
        <div className="trade-layout">
          <Panel title="Incoming offers" subtitle="Nothing moves until you explicitly confirm" icon="📨">
            {incoming.length === 0 ? <Empty title="No incoming offers" /> : incoming.map(t => (
              <TradeRow key={t.id} trade={t} state={state} onAccept={() => send('trade_accept', { trade_id: t.id })}
                onReject={() => send('trade_reject', { trade_id: t.id })} />
            ))}
          </Panel>
          <Panel title="Make an offer" subtitle={windowInfo?.open ? 'Two-sided confirmation required' : `Closed until round ${windowInfo?.next_round}`} icon="🔄">
            <label className="field"><span>Offer to</span>
              <select value={to} onChange={e => { setTo(e.target.value); setGive(emptyBundle()); setWant(emptyBundle()) }}>
                <option value="">Choose a rival franchise…</option>
                {rivals.map(r => <option key={r.id} value={r.id}>{r.avatar} {r.name} · {money(r.balance)}</option>)}
              </select>
            </label>
            {target ? <>
              <div className="two-col">{renderBundle(give, target, 'give')}{renderBundle(want, target, 'want')}</div>
              <label className="field"><span>Message (optional)</span>
                <input value={message} maxLength={180} onChange={e => setMessage(e.target.value)} placeholder="Propose a fair swap…" /></label>
              <Button variant="gold" block disabled={!windowInfo?.open || give.cash > (f?.balance || 0) || want.cash > (target.balance || 0)}
                onClick={submitOffer}>Send two-sided offer</Button>
            </> : <Empty title="Choose a rival" text="Select a franchise above to build an offer." />}
          </Panel>
          <Panel title="Your outgoing offers" subtitle="Withdraw before confirmation" icon="📤">
            {outgoing.length === 0 ? <Empty title="No outgoing offers" /> : outgoing.map(t => (
              <TradeRow key={t.id} trade={t} state={state} onCancel={() => send('trade_cancel', { trade_id: t.id })} />
            ))}
          </Panel>
        </div>
      )}

      {tab === 'history' && (
        <Panel title="Trade history" subtitle="Executed, rejected and withdrawn offers" icon="📜">
          {history.length === 0 ? <Empty title="No trades yet" /> : history.map(t => <TradeRow key={t.id} trade={t} state={state} />)}
        </Panel>
      )}

      {upgradePos !== null && (
        <Modal title={`Upgrade ${state.board?.[upgradePos]?.short || 'stadium'}`} subtitle="Permanent venue improvement" onClose={() => setUpgradePos(null)}>
          <div className="upgrade-options">
            {Object.entries(state.gamedata?.stadium_upgrades || {}).map(([key, spec]: any) => {
              const installed = (f?.stadiums?.[String(upgradePos)] || []).includes(key)
              return <button key={key} type="button" disabled={installed || (f?.balance || 0) < spec.cost}
                onClick={() => { send('upgrade_stadium', { pos: upgradePos, upgrade: key }); setUpgradePos(null) }}>
                <span>⬆️</span><div><strong>{spec.name}</strong><small>{spec.desc}</small></div><b>{money(spec.cost)}</b>
              </button>
            })}
          </div>
        </Modal>
      )}
    </div>
  )
}

function TradeRow({ trade, state, onAccept, onReject, onCancel }: {
  trade: Trade; state: any; onAccept?: () => void; onReject?: () => void; onCancel?: () => void
}) {
  const label = (ids: string[]) => ids.map(id => state.gamedata?.players?.find((p: any) => p.id === id)?.name || id).join(', ') || '—'
  return (
    <div className="trade-row">
      <div className="trade-head">
        <strong>{state.franchises[trade.from]?.name} → {state.franchises[trade.to]?.name}</strong>
        <Badge tone={trade.status === 'executed' ? 'green' : trade.status === 'pending' ? 'gold' : 'default'}>{trade.status.toUpperCase()}</Badge>
      </div>
      {trade.message && <p className="trade-message">“{trade.message}”</p>}
      <div className="trade-detail">
        <span><small>Gives</small><strong>{label(trade.give.players)}</strong></span>
        <span><small>Gets</small><strong>{label(trade.want.players)}</strong></span>
        <span><small>FC</small><strong>{trade.give.cash} ↔ {trade.want.cash}</strong></span>
      </div>
      {(onAccept || onReject || onCancel) && <div className="button-row">
        {onAccept && <Button variant="success" small onClick={onAccept}>✓ Confirm trade</Button>}
        {onReject && <Button variant="danger" small onClick={onReject}>Reject</Button>}
        {onCancel && <Button variant="subtle" small onClick={onCancel}>Withdraw</Button>}
      </div>}
    </div>
  )
}
