import React from 'react'
import { useApp } from '../store'
import { Avatar, Badge, Button, Empty, Panel, Stat } from '../components/UI'
import { money } from '../utils'

export function Results() {
  const { app, send, dispatch, refreshSaved } = useApp()
  const state = app.state!
  const champion = state.winner_id ? state.franchises?.[state.winner_id] : undefined
  const finals = state.final_points || []
  const isHost = state.host_id === app.session?.playerId

  if (!state.finished) return (
    <div className="page">
      <Panel title="Season in progress" subtitle="The finale unlocks when the champion is decided" icon="⏳">
        <Empty title="No final results yet" text="Finish the league and playoffs to see the champion." />
        <Button onClick={() => dispatch({ type: 'VIEW', view: 'tournament' })}>View tournament table</Button>
      </Panel>
    </div>
  )

  return (
    <div className="page results-page">
      <div className="trophy-hero">
        <div className="confetti">{Array.from({ length: 18 }).map((_, i) => <i key={i} style={{ '--i': i } as React.CSSProperties} />)}</div>
        <span className="trophy">🏆</span>
        <small>SEASON {state.season} CHAMPION</small>
        <h1>{champion?.name || 'Champion'}</h1>
        <p>{state.mode === 'classic' ? 'The last franchise standing in Classic Survival.' : 'Highest combined championship, finance, squad, infrastructure and collection score.'}</p>
        {champion && <div className="winner-stats">
          <Stat label="Final points" value={finals.find(r => r.id === champion.id)?.total || 0} tone="gold" icon="⭐" />
          <Stat label="Balance" value={money(champion.balance)} icon="💰" />
          <Stat label="Record" value={`${champion.record.wins}–${champion.record.losses}`} icon="🏏" />
          <Stat label="Assets" value={champion.markets.length + Object.keys(champion.stadiums).length} icon="🏟️" />
        </div>}
      </div>

      <div className="results-grid">
        <Panel title="Final standings" subtitle="Standard Season 100-point scale" icon="🏆">
          <table className="data-table">
            <thead><tr><th>#</th><th>Franchise</th><th>Champ</th><th>Finance</th><th>Squad</th><th>Infra</th><th>Collect</th><th>Total</th></tr></thead>
            <tbody>{finals.map(r => <tr key={r.id} className={r.id === state.winner_id ? 'champion' : ''}>
              <td>{r.final_rank}</td><td><span className="team-color" style={{ background: r.color }} />{r.name}</td>
              <td>{r.championship}</td><td>{r.finance}</td><td>{r.squad}</td><td>{r.infrastructure}</td>
              <td>{r.collections}</td><td><strong>{r.total}</strong></td>
            </tr>)}</tbody>
          </table>
        </Panel>

        <Panel title="Franchise summaries" subtitle="Final position, record and portfolio" icon="📋">
          <div className="summary-list">
            {Object.values(state.franchises).map(f => (
              <div key={f.id} className="summary-row">
                <Avatar franchise={f} />
                <div><strong>{f.name}</strong><small>{f.record.wins}W · {f.record.losses}L · {f.record.points + f.record.bonus} pts</small></div>
                <Badge tone={f.id === state.winner_id ? 'gold' : 'default'}>{money(f.balance)}</Badge>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <div className="end-actions">
        <Button variant="gold" onClick={() => dispatch({ type: 'VIEW', view: 'tournament' })}>Full tournament table</Button>
        {isHost && <Button variant="subtle" onClick={() => { send('restart', {}); refreshSaved(); dispatch({ type: 'VIEW', view: 'draft' }) }}>
          🔁 Restart season
        </Button>}
        <Button variant="subtle" onClick={() => dispatch({ type: 'VIEW', view: 'ledger' })}>Review ledger</Button>
      </div>
    </div>
  )
}
