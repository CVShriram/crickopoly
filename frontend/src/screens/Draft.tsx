import React, { useMemo, useState } from 'react'
import { useApp } from '../store'
import type { PlayerData, Role, Tier } from '../types'
import { Avatar, Badge, Button, Empty, Meter, Panel, PlayerPortrait, Segmented } from '../components/UI'
import { DRAFT_PRICE } from '../constants'
import { money, roleClass, tierClass, titleCase } from '../utils'

export function Draft() {
  const { app, send } = useApp()
  const state = app.state!
  const [role, setRole] = useState<'all' | Role>('all')
  const [tier, setTier] = useState<'all' | Tier>('all')
  const [country, setCountry] = useState('all')
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<'overall' | 'value' | 'form'>('overall')

  const taken = useMemo(() => new Set(Object.values(state.franchises).flatMap(f => Object.keys(f.squad))), [state.franchises])
  const counts = useMemo(() => Object.fromEntries(Object.values(state.franchises).map(f => [f.id, Object.keys(f.squad).length])), [state.franchises])
  const current = state.current_player_id ? state.franchises[state.current_player_id] : undefined
  const myF = state.you ? state.franchises[state.you] : undefined
  const myTurn = state.current_player_id === state.you
  const myBalance = myF?.balance || 0

  const players = useMemo(() => {
    return (state.gamedata?.players || [])
      .filter(p => !taken.has(p.id))
      .filter(p => role === 'all' || p.role === role)
      .filter(p => tier === 'all' || p.tier === tier)
      .filter(p => country === 'all' || p.country === country)
      .filter(p => !query || p.name.toLowerCase().includes(query.toLowerCase()))
      .sort((a, b) => b[sort] - a[sort])
      .slice(0, 60)
  }, [state.gamedata, taken, role, tier, country, query, sort])

  const pick = (p: PlayerData) => {
    if (!myTurn) return
    send('draft', { player_id: p.id })
  }

  const mySquad = Object.keys(myF?.squad || {}).map(id => state.gamedata?.players?.find(p => p.id === id)).filter(Boolean) as PlayerData[]

  return (
    <div className="page draft-page">
      <div className="page-head">
        <div><small>SNAKE DRAFT · 15 PICKS EACH</small><h1>Inaugural Player Draft</h1>
          <p>Build a balanced 15-player squad. Role targets: 5 batters, 5 bowlers, 2 keepers, 3 all-rounders.</p></div>
        <div className="draft-turn-card">
          {current && <><Avatar franchise={current} size="lg" />
            <div><small>ON THE CLOCK</small><strong>{current.name}</strong>
              <span>{current.is_bot ? `${current.difficulty} AI is thinking…` : myTurn ? 'Your pick — choose wisely' : 'Human manager is picking'}</span></div></>}
        </div>
      </div>

      <div className="draft-layout">
        <Panel className="draft-pool" title="Available players" subtitle={`${(state.gamedata?.players || []).length - taken.size} unsigned · showing top ${players.length}`} icon="📋"
          action={<div className="filter-row">
            <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search name…" />
            <select value={country} onChange={e => setCountry(e.target.value)}>
              <option value="all">All countries</option>
              {Object.entries(state.gamedata?.countries || {}).map(([key, c]) =>
                <option key={key} value={key}>{c.flag} {c.name}</option>)}
            </select>
            <select value={sort} onChange={e => setSort(e.target.value as any)}>
              <option value="overall">Top rated</option><option value="form">Best form</option><option value="value">Highest value</option>
            </select>
          </div>}>
          <Segmented value={role} onChange={setRole} options={[
            { value: 'all', label: 'All' }, { value: 'batsman', label: 'Bat' },
            { value: 'bowler', label: 'Bowl' }, { value: 'wicketkeeper', label: 'WK' },
            { value: 'allrounder', label: 'All-round' },
          ]} />
          <div className="tier-filter">
            {(['all', 'bronze', 'silver', 'gold'] as const).map(t => (
              <button key={t} type="button" className={tier === t ? 'active' : ''} onClick={() => setTier(t)}>
                {t === 'all' ? 'All tiers' : `${t} · ${DRAFT_PRICE[t]} FC`}
              </button>
            ))}
          </div>
          {players.length === 0 ? <Empty title="No players match those filters" /> : (
            <div className="player-grid">
              {players.map(p => {
                const price = DRAFT_PRICE[p.tier] || 50
                const affordable = myBalance >= price
                return (
                  <button key={p.id} type="button" className={`draft-card ${tierClass(p.tier)} ${!myTurn || !affordable ? 'disabled' : ''}`}
                    onClick={() => pick(p)} disabled={!myTurn || !affordable}>
                    <span className="draft-flag">{p.flag}</span>
                    <PlayerPortrait player={p} />
                    <div className="draft-card-main">
                      <strong>{p.name}</strong>
                      <span className={`role-tag ${roleClass(p.role)}`}>{state.gamedata?.role_short?.[p.role] || p.role}</span>
                    </div>
                    <div className="draft-card-meta">
                      <span>OVR <b>{p.overall}</b></span><span>FRM <b>{p.form}</b></span><span>FIT <b>{p.fitness}</b></span>
                    </div>
                    <div className="draft-card-foot"><span className={`tier-dot ${tierClass(p.tier)}`} />{p.tier}
                      <strong>{price} FC</strong></div>
                    {myTurn && affordable && <span className="pick-hint">DRAFT →</span>}
                  </button>
                )
              })}
            </div>
          )}
        </Panel>

        <aside className="draft-side">
          <Panel title="Draft board" subtitle="Picks completed" icon="📊">
            <div className="draft-progress-list">
              {Object.values(state.franchises).map(f => (
                <div key={f.id} className={`draft-progress ${state.current_player_id === f.id ? 'active' : ''}`}>
                  <Avatar franchise={f} size="sm" />
                  <div><strong>{f.name}</strong><small>{Object.keys(f.squad).length}/15 picks</small></div>
                  <Meter value={counts[f.id] || 0} max={15} tone="gold" />
                </div>
              ))}
            </div>
          </Panel>
          <Panel title="Your squad" subtitle={money(myBalance)} icon="👥"
            action={<Badge tone="gold">{mySquad.length}/15</Badge>}>
            {mySquad.length === 0 ? <Empty title="No picks yet" text="Choose from the player pool." /> : (
              <div className="mini-squad">
                {mySquad.map(p => (
                  <div key={p.id} className="mini-squad-row">
                    <PlayerPortrait player={p} size="sm" />
                    <span><strong>{p.name}</strong><small>{titleCase(p.role)} · {p.country}</small></span>
                    <b>{p.overall}</b>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </aside>
      </div>
    </div>
  )
}
