import React, { useMemo, useState } from 'react'
import { useApp } from '../store'
import type { PlayerData } from '../types'
import { Badge, Button, Empty, Panel, PlayerPortrait, Stat, Tabs } from '../components/UI'
import { titleCase } from '../utils'

const NUMERIC_FIELDS = ['overall', 'batting', 'bowling', 'fielding', 'fitness', 'consistency', 'form', 'confidence', 'value', 'portrait_hue']
const RULE_FIELDS = ['starting_credits', 'squad_capacity', 'xi_size', 'overs', 'powerplay', 'middle_end', 'season_start_income', 'win_points', 'tie_points', 'loss_points']

export function Admin() {
  const { app, send, dispatch } = useApp()
  const state = app.state!
  const isHost = state.host_id === app.session?.playerId
  const players = state.gamedata?.players || []
  const overrides: Record<string, any> = state.data_overrides || {}
  const [tab, setTab] = useState('roster')
  const [query, setQuery] = useState('')
  const [selectedId, setSelectedId] = useState<string>(players[0]?.id || '')
  const [draft, setDraft] = useState<Record<string, any>>({})
  const [ruleDraft, setRuleDraft] = useState<Record<string, any>>({})
  const [saved, setSaved] = useState(false)

  const filtered = useMemo(() => players.filter(p =>
    !query || p.name.toLowerCase().includes(query.toLowerCase()) || p.country.includes(query.toLowerCase())
  ).slice(0, 40), [players, query])
  const selected = players.find(p => p.id === selectedId) || filtered[0]
  const appliedPlayer: Record<string, any> = overrides.players?.[selected?.id] || {}
  const fields: Record<string, any> = selected ? {
    name: draft.name ?? appliedPlayer.name ?? selected.name,
    ...Object.fromEntries(NUMERIC_FIELDS.map(k => [k, draft[k] ?? appliedPlayer[k] ?? (selected as any)[k]])),
  } : {}

  const choose = (p: PlayerData) => { setSelectedId(p.id); setDraft({}); setSaved(false) }
  const savePlayer = () => {
    if (!selected) return
    clean: {
      const changes: Record<string, any> = {}
      if (fields.name !== selected.name) changes.name = fields.name
      NUMERIC_FIELDS.forEach(k => { if (Number(fields[k]) !== (selected as any)[k]) changes[k] = Number(fields[k]) })
      if (!Object.keys(changes).length) break clean
      send('admin_update', { overrides: { players: { [selected.id]: changes } } })
    }
    setSaved(true); window.setTimeout(() => setSaved(false), 1600)
  }
  const saveRules = () => {
    const changes: Record<string, number> = {}
    Object.entries(ruleDraft).forEach(([k, v]) => {
      if (v !== '' && Number(v) !== state.gamedata?.rules?.[k]) changes[k] = Number(v)
    })
    if (Object.keys(changes).length) send('admin_update', { overrides: { rules: changes } })
  }

  return (
    <div className="page admin-page">
      <div className="page-head">
        <div><small>DATA STUDIO</small><h1>Game data & season studio</h1>
          <p>Tune the fictional roster and bounded rules. No real player likenesses, logos or licensed branding are used.</p></div>
        <Badge tone={isHost ? 'green' : 'danger'} icon="🔒">{isHost ? 'HOST ACCESS' : 'READ ONLY'}</Badge>
      </div>

      <div className="dashboard-strip compact">
        <Stat label="Fictional players" value={players.length} icon="👥" />
        <Stat label="Edited players" value={Object.keys(overrides.players || {}).length} tone="gold" icon="✏️" />
        <Stat label=" Edited rules" value={Object.keys(overrides.rules || {}).length} tone="blue" icon="📐" />
        <Stat label="Board tiles" value={state.board?.length || 52} icon="🗺️" />
      </div>

      <Tabs active={tab} onChange={setTab} tabs={[
        { id: 'roster', label: 'Player editor', icon: '👥' },
        { id: 'rules', label: 'Rule tables', icon: '📐' },
        { id: 'about', label: 'Data policy', icon: '🛡️' },
      ]} />

      {!isHost && <div className="callout danger"><strong>Host only</strong><p>Ask the room host to make data edits.</p></div>}

      {tab === 'roster' && selected && (
        <div className="admin-layout">
          <Panel title="Roster" subtitle="96 fictional players · 8 countries × 4 roles × 3 tiers" icon="📋"
            action={<input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search roster…" />}>
            <div className="roster-list">
              {filtered.map(p => (
                <button key={p.id} type="button" className={selected.id === p.id ? 'active' : ''} onClick={() => choose(p)}>
                  <PlayerPortrait player={p} size="sm" />
                  <div><strong>{p.name}</strong><small>{p.flag} {titleCase(p.role)} · {p.tier}</small></div>
                  <b>{p.overall}</b>
                  {overrides.players?.[p.id] && <span className="edited-dot" title="Edited" />}
                </button>
              ))}
            </div>
          </Panel>
          <Panel title={`Edit ${selected.name}`} subtitle={selected.id} icon="✏️"
            action={<Button variant="gold" small disabled={!isHost} onClick={savePlayer}>{saved ? '✓ Saved' : 'Apply edit'}</Button>}>
            <label className="field"><span>Display name</span>
              <input value={fields.name} maxLength={40} disabled={!isHost}
                onChange={e => setDraft({ ...draft, name: e.target.value })} />
            </label>
            <div className="admin-fields">
              {NUMERIC_FIELDS.map(k => (
                <label key={k} className="field"><span>{titleCase(k)}</span>
                  <input type="number" value={fields[k]} disabled={!isHost}
                    min={k === 'value' ? 1 : k === 'portrait_hue' ? 0 : k === 'overall' ? 1 : 1}
                    max={k === 'value' ? 1000 : k === 'portrait_hue' ? 359 : k === 'overall' ? 100 : 99}
                    onChange={e => setDraft({ ...draft, [k]: Number(e.target.value) })} />
                </label>
              ))}
            </div>
            <div className="callout"><strong>Visible after apply</strong>
              <p>Edits are sanitised server-side, persisted with the save and shown in every connected client immediately.</p></div>
          </Panel>
        </div>
      )}

      {tab === 'rules' && (
        <Panel title="Bounded rule tables" subtitle="Only whitelisted numeric rules can be changed" icon="📐"
          action={<Button variant="gold" small disabled={!isHost} onClick={saveRules}>Apply rules</Button>}>
          <div className="admin-fields wide">
            {RULE_FIELDS.map(k => (
              <label key={k} className="field"><span>{titleCase(k)}</span>
                <input type="number" min={1} max={10000} disabled={!isHost}
                  placeholder={String(state.gamedata?.rules?.[k] ?? '')}
                  value={ruleDraft[k] ?? ''} onChange={e => setRuleDraft({ ...ruleDraft, [k]: e.target.value })} />
              </label>
            ))}
          </div>
          <div className="callout"><strong>Core structure is fixed</strong>
            <p>The 52-tile board, 8 countries, 8 venues, 96 players, 15-player squad, 11-player XI and T20 format remain intact.</p></div>
        </Panel>
      )}

      {tab === 'about' && (
        <Panel title="Content & licensing policy" subtitle="Safe by design" icon="🛡️">
          <div className="policy-grid">
            <div><span>✅</span><strong>Fictional roster</strong><p>All 96 player names and attributes are original fictional data.</p></div>
            <div><span>✅</span><strong>No official logos</strong><p>Venues use names only. No league, team or broadcast marks are bundled.</p></div>
            <div><span>✅</span><strong>Editable data</strong><p>Hosts can rename players and tune ratings for their own private league.</p></div>
            <div><span>✅</span><strong>Virtual currency only</strong><p>FC is a game ledger. Nothing here accepts deposits, wagers or payouts.</p></div>
          </div>
          {filtered.length === 0 && <Empty title="No players" />}
        </Panel>
      )}
    </div>
  )
}
