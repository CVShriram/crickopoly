import React, { useEffect, useMemo, useState } from 'react'
import { useApp } from '../store'
import type { PlayerData, Role } from '../types'
import { Badge, Button, Empty, Meter, Modal, Panel, PlayerPortrait, Segmented, Stat } from '../components/UI'
import { conditionOf, effective, money, roleClass, titleCase } from '../utils'

export function Squad() {
  const { app, send } = useApp()
  const state = app.state!
  const f = state.you ? state.franchises?.[state.you] : undefined
  const [xi, setXi] = useState<string[]>(f?.xi || [])
  const [captain, setCaptain] = useState<string | null>(f?.captain || null)
  const [vice, setVice] = useState<string | null>(f?.vice || null)
  const [filter, setFilter] = useState<'all' | Role>('all')
  const [trainingPlayer, setTrainingPlayer] = useState<string | null>(null)
  const [trainingType, setTrainingType] = useState('batting')

  useEffect(() => { setXi(f?.xi || []); setCaptain(f?.captain || null); setVice(f?.vice || null) }, [f?.xi, f?.captain, f?.vice])

  const squad = useMemo(() => Object.keys(f?.squad || {}).map(id => {
    const p = state.gamedata?.players?.find(x => x.id === id)
    return p ? { player: p, contract: f!.squad[id], cond: conditionOf(f, id) } : null
  }).filter(Boolean) as Array<{ player: PlayerData; contract: any; cond: any }>, [f, state.gamedata])

  const filtered = squad.filter(x => filter === 'all' || x.player.role === filter)
  const selected = new Set(xi)
  const roleCounts = (ids: string[]) => ids.reduce<Record<string, number>>((acc, id) => {
    const role = squad.find(x => x.player.id === id)?.player.role
    if (role) acc[role] = (acc[role] || 0) + 1
    return acc
  }, {})
  const counts = roleCounts(xi)
  const limits = state.gamedata?.rules?.xi_roles || {
    batsman: { min: 3, max: 5 }, bowler: { min: 3, max: 5 },
    wicketkeeper: { min: 1, max: 2 }, allrounder: { min: 1, max: 3 },
  }
  const violations: string[] = []
  if (xi.length !== 11) violations.push(`Playing XI must have exactly 11 players (currently ${xi.length})`)
  ;(Object.keys(limits) as Role[]).forEach(role => {
    const n = counts[role] || 0
    const lim = limits[role]
    if (n < lim.min) violations.push(`Need at least ${lim.min} ${lim.lowercase || titleCase(role).toLowerCase()}(s)`)
    if (n > lim.max) violations.push(`At most ${lim.max} ${titleCase(role).toLowerCase()}(s) allowed`)
  })
  if (captain && !selected.has(captain)) violations.push('Captain must be in the XI')
  if (vice && !selected.has(vice)) violations.push('Vice-captain must be in the XI')
  if (captain && vice && captain === vice) violations.push('Captain and vice must be different')
  const injuredSelected = xi.some(id => conditionOf(f, id).injury)
  if (injuredSelected) violations.push('Injured players cannot be selected')

  const toggle = (id: string) => {
    if (selected.has(id)) {
      setXi(xi.filter(x => x !== id))
      if (captain === id) setCaptain(null)
      if (vice === id) setVice(null)
    } else if (xi.length < 11) {
      setXi([...xi, id])
    }
  }

  const save = () => send('set_xi', { xi, captain, vice })
  const trainingPlayerObj = squad.find(x => x.player.id === trainingPlayer)

  return (
    <div className="page squad-page">
      <div className="page-head">
        <div><small>SQUAD & SELECTION</small><h1>Build your Playing XI</h1>
          <p>Exactly 11 players, valid role mix, fit bodies and a clear leadership group.</p></div>
        <div className="button-row">
          <Button variant="subtle" onClick={() => send('auto_xi', {})}>✨ Auto-select XI</Button>
          <Button variant="gold" onClick={save} disabled={violations.length > 0}>Save XI ({xi.length}/11)</Button>
        </div>
      </div>

      <div className="dashboard-strip compact">
        <Stat label="Squad size" value={`${squad.length}/15`} icon="👥" />
        <Stat label="XI selected" value={xi.length} tone={xi.length === 11 ? 'green' : 'gold'} icon="✅" />
        <Stat label="Injured" value={squad.filter(x => x.cond.injury).length} tone="danger" icon="🚑" />
        <Stat label="Avg fatigue" value={`${Math.round(squad.reduce((a, x) => a + x.cond.fatigue, 0) / Math.max(1, squad.length))}%`} icon="🔋" />
        <Stat label="Spent on contracts" value={money(squad.reduce((a, x) => a + (x.contract.price || 0), 0))} icon="💸" />
      </div>

      <div className="squad-layout">
        <Panel title="Contracted players" subtitle="Click to toggle your XI · use the action button to train or recover" icon="👥"
          action={<Segmented value={filter} onChange={setFilter} options={[
            { value: 'all', label: 'All' }, { value: 'batsman', label: 'Bat' },
            { value: 'bowler', label: 'Bowl' }, { value: 'wicketkeeper', label: 'WK' },
            { value: 'allrounder', label: 'AR' },
          ]} />}>
          {filtered.length === 0 ? <Empty title="No players in this role" /> : (
            <div className="squad-grid">
              {filtered.map(({ player, contract, cond }) => {
                const inXI = selected.has(player.id)
                return (
                  <div key={player.id} className={`squad-card ${inXI ? 'selected' : ''} ${cond.injury ? 'injured' : ''}`}>
                    <button type="button" className="squad-select" onClick={() => toggle(player.id)}>
                      <PlayerPortrait player={player} injured={Boolean(cond.injury)} />
                      <div className="squad-card-main">
                        <strong>{player.name} {player.id === captain && <span className="captain-tag">C</span>}
                          {player.id === vice && <span className="captain-tag vice">VC</span>}</strong>
                        <small>{player.flag} {titleCase(player.role)} · {player.tier} · {money(contract.price)}</small>
                      </div>
                      <span className={`role-tag ${roleClass(player.role)}`}>{state.gamedata?.role_short?.[player.role]}</span>
                    </button>
                    <div className="squad-ratings">
                      <span>OVR <b>{effective(player, cond, 'overall')}</b></span>
                      <span>BAT <b>{effective(player, cond, 'batting')}</b></span>
                      <span>BWL <b>{effective(player, cond, 'bowling')}</b></span>
                      <span>FRM <b>{cond.form}</b></span>
                    </div>
                    <div className="squad-bars">
                      <Meter value={cond.fatigue} tone={cond.fatigue > 60 ? 'danger' : 'blue'} label={`Fatigue ${cond.fatigue}`} />
                      <Meter value={cond.fitness} tone="green" label={`Fitness ${cond.fitness}`} />
                      <Meter value={cond.confidence} tone="gold" label={`Confidence ${cond.confidence}`} />
                    </div>
                    {cond.injury && <div className="injury-note">{cond.injury.icon} {cond.injury.type} · {cond.injury.matches_left} match(es)</div>}
                    <div className="squad-actions">
                      <button type="button" onClick={() => setTrainingPlayer(player.id)}>🏋️ Train</button>
                      {cond.injury
                        ? <button type="button" onClick={() => send('rehabilitate', { player_id: player.id })}>🩹 Rehab {money(cond.injury.cost)}</button>
                        : <button type="button" onClick={() => send('rest', { player_id: player.id })}>💤 Rest</button>}
                      {player.id === captain
                        ? <button type="button" onClick={() => setCaptain(null)}>Remove C</button>
                        : <button type="button" onClick={() => setCaptain(player.id)} disabled={!inXI}>Set C</button>}
                      {player.id === vice
                        ? <button type="button" onClick={() => setVice(null)}>Remove VC</button>
                        : <button type="button" onClick={() => setVice(player.id)} disabled={!inXI}>Set VC</button>}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Panel>

        <aside className="selection-side">
          <Panel title="XI validator" subtitle="Role constraints and selection checks" icon="✅"
            action={violations.length === 0 ? <Badge tone="green">VALID</Badge> : <Badge tone="danger">{violations.length} ISSUES</Badge>}>
            <div className="role-counts">
              {(Object.keys(limits) as Role[]).map(role => {
                const n = counts[role] || 0
                const lim = limits[role]
                const ok = n >= lim.min && n <= lim.max
                return <div key={role} className={ok ? 'ok' : 'bad'}>
                  <span>{state.gamedata?.role_labels?.[role] || titleCase(role)}</span>
                  <strong>{n} / {lim.min}–{lim.max}</strong>
                </div>
              })}
            </div>
            {violations.length === 0
              ? <div className="callout success"><strong>Ready for matchday</strong><p>Your XI satisfies every selection rule.</p></div>
              : <ul className="issue-list">{violations.map((v, i) => <li key={i}>{v}</li>)}</ul>}
            <div className="xi-list">
              {xi.map(id => {
                const p = squad.find(x => x.player.id === id)?.player
                if (!p) return null
                return <div key={id} className="xi-row">
                  <PlayerPortrait player={p} size="sm" />
                  <span>{p.name}</span>
                  <small>{id === captain ? 'C' : id === vice ? 'VC' : state.gamedata?.role_short?.[p.role]}</small>
                </div>
              })}
              {Array.from({ length: Math.max(0, 11 - xi.length) }).map((_, i) =>
                <div key={`empty-${i}`} className="xi-row empty">Empty slot</div>)}
            </div>
          </Panel>
          <Panel title="Training & recovery" subtitle="Attributes improve before your eyes" icon="🏋️">
            <p className="muted">Select a player card then choose a camp. Training costs FC and adds fatigue; injured players require rehabilitation instead.</p>
            <div className="training-rates">
              {Object.entries(state.gamedata?.training || {}).map(([key, spec]: any) =>
                <div key={key}><span>{spec.icon} {spec.name}</span><strong>{money(spec.cost)}</strong></div>)}
            </div>
          </Panel>
        </aside>
      </div>

      {trainingPlayer && (
        <Modal title={`Train ${trainingPlayerObj?.player.name || ''}`} subtitle="Choose a development camp" onClose={() => setTrainingPlayer(null)}>
          <div className="training-options">
            {Object.entries(state.gamedata?.training || {}).map(([key, spec]: any) => (
              <button key={key} type="button" onClick={() => { send('train', { player_id: trainingPlayer, type: key }); setTrainingPlayer(null) }}>
                <span className="train-icon">{spec.icon}</span>
                <span><strong>{spec.name}</strong><small>{spec.desc || `Improve ${spec.attr} by up to ${spec.gain}`}</small></span>
                <b>{money(spec.cost)}</b>
              </button>
            ))}
          </div>
        </Modal>
      )}
    </div>
  )
}
