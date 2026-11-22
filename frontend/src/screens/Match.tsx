import React, { useMemo, useState } from 'react'
import { useApp } from '../store'
import { BATTING_OPTIONS, BOWLING_OPTIONS, FIELD_OPTIONS, PHASES, PHASE_LABELS } from '../constants'
import { Badge, Button, Empty, Panel, PlayerPortrait, Stat } from '../components/UI'
import { money, playerLabel, titleCase } from '../utils'
import type { MatchRecord } from '../types'

type Plan = Record<string, { bat: string; bowl: string; field: string }>
const defaultPlan = (): Plan => Object.fromEntries(PHASES.map(p => [p, { bat: 'balanced', bowl: 'defensive', field: 'balanced' }]))

export function Match() {
  const { app, send, dispatch } = useApp()
  const state = app.state!
  const f = state.you ? state.franchises[state.you] : undefined
  const [opponent, setOpponent] = useState('')
  const [plan, setPlan] = useState<Plan>(defaultPlan())
  const [card, setCard] = useState('')
  const [openResult, setOpenResult] = useState<string | null>(null)

  const pending = state.pending?.type === 'match_setup' ? state.pending : null
  const participants: string[] = pending ? [pending.a, pending.b] : []
  const inMatch = state.you ? participants.includes(state.you) : false
  const submitted = state.tactics_submitted || []
  const mySubmitted = Boolean(state.you && submitted.includes(state.you))
  const opponentSubmitted = submitted.filter(id => id !== state.you)
  const rivals = Object.values(state.franchises).filter(x => x.id !== state.you)
  const last = state.matches?.[state.matches.length - 1] as MatchRecord | undefined
  const result = state.matches?.find(m => m.id === openResult) || last

  const pitch = state.gamedata?.pitches?.[state.pitch]
  const myXI = useMemo(() => (f?.xi || []).map(id => state.gamedata?.players?.find(p => p.id === id)).filter(Boolean), [f, state.gamedata])
  const invalidXI = (f?.xi?.length || 0) !== 11 || myXI.some(p => f?.conditions?.[p!.id]?.injury)

  const update = (phase: string, key: string, value: string) =>
    setPlan({ ...plan, [phase]: { ...plan[phase], [key]: value } })

  return (
    <div className="page match-page">
      <div className="page-head">
        <div><small>T20 MATCH CONTROL</small><h1>{pending ? 'Concealed tactics lobby' : 'Matchday arena'}</h1>
          <p>{pending ? 'Both managers submit plans before any tactic is revealed.' : 'Challenge a rival, or wait for a Matchday tile to open the arena.'}</p></div>
        <div className="pitch-badge"><span>{pitch?.icon || '🏏'}</span><div><small>CURRENT PITCH</small><strong>{pitch?.name || state.pitch}</strong></div></div>
      </div>

      <div className="dashboard-strip compact">
        <Stat label="Matches played" value={state.matches?.length || 0} icon="🏏" />
        <Stat label="Your record" value={`${f?.record?.wins || 0}–${f?.record?.losses || 0}`} tone="green" icon="📊" />
        <Stat label="Match prize" value="60 FC" tone="gold" icon="💰" />
        <Stat label="Your XI" value={`${f?.xi?.length || 0}/11`} tone={invalidXI ? 'danger' : 'green'} icon="✅" />
        <Stat label="Tactical cards" value={f?.cards?.length || 0} tone="gold" icon="🧠" />
      </div>

      {pending && (
        <Panel title="Match lobby" subtitle={`Seed ${pending.seed} · plans are concealed until both are locked in`} icon="🔒"
          action={<Badge tone={mySubmitted ? 'green' : 'gold'}>{mySubmitted ? 'PLAN LOCKED' : 'AWAITING YOUR PLAN'}</Badge>}>
          <div className="matchup-bar">
            {participants.map((id, i) => {
              const fr = state.franchises[id]
              const isSubmitted = submitted.includes(id)
              return <React.Fragment key={id}>
                {i > 0 && <span className="versus">VS</span>}
                <div className="matchup-team">
                  <span style={{ background: fr?.color }}>{fr?.avatar}</span>
                  <div><strong>{fr?.name}</strong><small>{fr?.is_bot ? `${fr.difficulty} AI` : 'Human manager'}</small></div>
                  {isSubmitted ? <Badge tone="green" icon="✓">SUBMITTED</Badge> : <Badge tone="gold">THINKING…</Badge>}
                </div>
              </React.Fragment>
            })}
          </div>
          {inMatch ? (
            <div className="tactics-builder">
              <div className="tactics-grid">
                {PHASES.map(phase => (
                  <div key={phase} className="phase-card">
                    <h3>{PHASE_LABELS[phase]}</h3>
                    <div className="tactic-group"><label>Batting</label>
                      <div className="option-row">{BATTING_OPTIONS.map(o => (
                        <button key={o.value} type="button" className={plan[phase].bat === o.value ? 'active' : ''}
                          onClick={() => update(phase, 'bat', o.value)}>{o.icon} {o.label}</button>))}</div>
                    </div>
                    <div className="tactic-group"><label>Bowling</label>
                      <div className="option-row">{BOWLING_OPTIONS.map(o => (
                        <button key={o.value} type="button" className={plan[phase].bowl === o.value ? 'active' : ''}
                          onClick={() => update(phase, 'bowl', o.value)}>{o.icon} {o.label}</button>))}</div>
                    </div>
                    <div className="tactic-group"><label>Field</label>
                      <div className="option-row">{FIELD_OPTIONS.map(o => (
                        <button key={o.value} type="button" className={plan[phase].field === o.value ? 'active' : ''}
                          onClick={() => update(phase, 'field', o.value)}>{o.icon} {o.label}</button>))}</div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="tactics-footer">
                <label className="field card-picker"><span>Tactical card (consumed on reveal)</span>
                  <select value={card} onChange={e => setCard(e.target.value)}>
                    <option value="">No card</option>
                    {(f?.cards || []).map(id => <option key={id} value={id}>
                      {state.gamedata?.tactical_cards?.[id]?.icon} {state.gamedata?.tactical_cards?.[id]?.name}
                    </option>)}
                  </select>
                </label>
                <div className="button-row">
                  <Button variant="subtle" onClick={() => send('cancel_match', {})}>Cancel match</Button>
                  <Button variant="gold" onClick={() => send('submit_tactics', { tactics: plan, card: card || undefined })}>
                    {mySubmitted ? 'Update plan' : '🔒 Submit concealed plan'}
                  </Button>
                  {opponentSubmitted.length > 0 && <Button variant="success" onClick={() => send('reveal_tactics', {})}>Reveal & play</Button>}
                </div>
              </div>
              <p className="muted">Opponent submission count: {opponentSubmitted.length}/1. Their tactic choices are not visible to you.</p>
            </div>
          ) : <div className="callout"><strong>You are not in this match</strong><p>Wait for the participants to lock their plans.</p></div>}
        </Panel>
      )}

      {!pending && (
        <Panel title="Challenge a rival" subtitle="Both teams must have a legal XI before the match can open" icon="⚔️"
          action={state.pending?.type === 'matchday' ? <Badge tone="gold" icon="🏟️">MATCHDAY TILE</Badge> : undefined}>
          {invalidXI && <div className="callout danger"><strong>Fix your XI first</strong>
            <p>You need exactly 11 available players. Invalid XIs cannot start a match.</p>
            <Button variant="subtle" small onClick={() => dispatch({ type: 'VIEW', view: 'squad' })}>Open squad</Button>
          </div>}
          <div className="challenge-grid">
            {rivals.map(r => (
              <button key={r.id} type="button" className={`challenge-card ${opponent === r.id ? 'active' : ''}`}
                onClick={() => setOpponent(r.id)}>
                <span style={{ background: r.color }}>{r.avatar}</span>
                <div><strong>{r.name}</strong><small>{r.record?.wins || 0} wins · {r.is_bot ? `${r.difficulty} AI` : 'Human'}</small></div>
                <Badge tone="blue">#{state.standings?.find(x => x.id === r.id)?.rank || '—'}</Badge>
              </button>
            ))}
          </div>
          <div className="button-row">
            <Button variant="gold" disabled={!opponent || invalidXI} onClick={() => send('open_match', { opponent })}>
              🏏 Open concealed match lobby
            </Button>
            <Button variant="subtle" onClick={() => dispatch({ type: 'VIEW', view: 'board' })}>Back to board</Button>
          </div>
        </Panel>
      )}

      {result && (
        <Panel title="Latest result" subtitle={`${result.id} · round ${result.round} · seed ${result.seed}`} icon="📊"
          action={<Badge tone="gold">{result.playoff_stage || 'League'}</Badge>}>
          <div className="scoreboard">
            <div className="score-team"><span>{state.franchises[result.a]?.avatar}</span><strong>{result.a_name}</strong>
              <h2>{result.a_runs}/{result.a_wickets}</h2><small>{result.a_runs === result.b_runs ? 'Tie' : result.winner === result.a ? 'Won' : 'Lost'}</small></div>
            <div className="score-mid"><span>VS</span><p>{result.winner_name || 'Tie'}</p></div>
            <div className="score-team"><span>{state.franchises[result.b]?.avatar}</span><strong>{result.b_name}</strong>
              <h2>{result.b_runs}/{result.b_wickets}</h2><small>{result.winner === result.b ? 'Won' : result.a_runs === result.b_runs ? 'Tie' : 'Lost'}</small></div>
          </div>
          <div className="phase-summary">
            {['phases_a', 'phases_b'].map((key, idx) => (
              <div key={key}><h4>{(idx === 0 ? result.a_name : result.b_name)} innings</h4>
                {((result as any)[key] || []).map((p: any, i: number) => (
                  <div key={i}><span>{p.name || PHASE_LABELS[PHASES[i]] || p.phase}</span>
                    <strong>{p.runs || 0}/{p.wickets || 0}</strong><small>RR {p.run_rate || p.rr || '—'}</small></div>))}
              </div>
            ))}
          </div>
          <div className="analysis"><span>📋</span><p>{result.analysis}</p></div>
          <div className="result-foot"><span>Player of the match: <strong>{playerLabel(state, result.player_of_match)}</strong></span>
            <span>Pitch: <strong>{titleCase(result.pitch)}</strong></span></div>
        </Panel>
      )}

      <Panel title="Match archive" subtitle="Every T20 result is stored with its tactics and seed" icon="🗂️">
        {(state.matches || []).length === 0 ? <Empty title="No matches yet" /> : (
          <div className="match-list">
            {[...state.matches].reverse().map(m => (
              <button key={m.id} type="button" className={`match-row ${openResult === m.id ? 'active' : ''}`} onClick={() => setOpenResult(m.id)}>
                <span>R{m.round}</span><strong>{m.a_name} {m.a_runs}/{m.a_wickets}</strong>
                <em>vs</em><strong>{m.b_name} {m.b_runs}/{m.b_wickets}</strong>
                <Badge tone={m.winner ? 'green' : 'default'}>{m.winner_name || 'Tie'}</Badge>
              </button>
            ))}
          </div>
        )}
      </Panel>
    </div>
  )
}
