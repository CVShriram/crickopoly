import React from 'react'
import { useApp } from '../store'
import { Badge, Empty, Panel, Stat } from '../components/UI'
import { money, titleCase } from '../utils'

export function Tournament() {
  const { app, dispatch } = useApp()
  const state = app.state!
  const rows = state.standings || []
  const bracket = state.playoff_bracket
  const finals = state.final_points || []
  const champion = state.winner_id ? state.franchises[state.winner_id] : undefined
  const leader = rows[0]

  return (
    <div className="page tournament-page">
      <div className="page-head">
        <div><small>LEAGUE · PLAYOFFS · FINALE</small><h1>Tournament table</h1>
          <p>Standings are ranked by league points, net run rate and runs scored.</p></div>
        {state.mode === 'classic'
          ? <Badge tone="danger" icon="💀">CLASSIC SURVIVAL</Badge>
          : <Badge tone="gold" icon="🏆">100 POINT FINAL</Badge>}
      </div>

      {champion && <div className="champion-banner">
        <span>{champion.avatar}</span>
        <div><small>SEASON {state.season} CHAMPION</small><h2>{champion.name}</h2>
          <p>{state.mode === 'classic' ? 'Last franchise standing' : `${finals.find(r => r.id === champion.id)?.total || 0}/100 final points`}</p></div>
        <ButtonLike onClick={() => dispatch({ type: 'VIEW', view: 'results' })}>View finale →</ButtonLike>
      </div>}

      <div className="dashboard-strip compact">
        <Stat label="League leader" value={leader?.name || '—'} sub={`${leader?.points || 0} pts`} tone="gold" icon="🥇" />
        <Stat label="Matches" value={state.matches?.length || 0} icon="🏏" />
        <Stat label="League rounds" value={`${Math.min(state.round, state.settings?.season_rounds || 8)}/${state.settings?.season_rounds || 8}`} icon="📅" />
        <Stat label="Phase" value={titleCase(state.phase)} tone="green" icon="🚦" />
      </div>

      <div className="tournament-grid">
        <Panel title="League standings" subtitle="Points + NRR decide playoff seeds" icon="📊">
          {rows.length === 0 ? <Empty title="No standings" /> : (
            <table className="data-table">
              <thead><tr><th>#</th><th>Franchise</th><th>P</th><th>W</th><th>L</th><th>T</th><th>Pts</th><th>NRR</th><th>Record</th></tr></thead>
              <tbody>{rows.map(r => <tr key={r.id} className={r.id === state.you ? 'mine' : ''}>
                <td><span className={`rank rank-${r.rank}`}>{r.rank}</span></td>
                <td><span className="team-color" style={{ background: r.color }} />{r.name}</td>
                <td>{r.played}</td><td>{r.wins}</td><td>{r.losses}</td><td>{r.ties}</td>
                <td><strong>{r.points}</strong></td><td>{r.nrr >= 0 ? '+' : ''}{r.nrr}</td><td>{r.record}</td>
              </tr>)}</tbody>
            </table>
          )}
        </Panel>

        <Panel title="Playoff bracket" subtitle={bracket ? titleCase(bracket.type) : 'Built after the league stage'} icon="🌳">
          {!bracket ? <Empty title="Bracket pending" text="Complete all league rounds to seed the playoffs." /> : (
            <div className="bracket">
              {bracket.semis?.length > 0 && <div className="bracket-round"><h4>Semi-finals</h4>
                {bracket.semis.map((pair: string[], i: number) => <div key={i} className="bracket-pair">
                  {pair.map(id => <span key={id || i}>{id ? state.franchises[id]?.name : 'TBD'}</span>)}
                </div>)}
              </div>}
              {bracket.final?.length > 0 && <div className="bracket-round final"><h4>Final</h4>
                <div className="bracket-pair">{bracket.final.map((id: string | null, i: number) =>
                  <span key={i}>{id ? state.franchises[id]?.name : 'TBD'}</span>)}</div>
              </div>}
            </div>
          )}
        </Panel>
      </div>

      <Panel title="Standard Season final scorecard" subtitle="Championship 40 · Finance 25 · Squad 20 · Infrastructure 10 · Collections 5" icon="🏅">
        {finals.length === 0 ? <Empty title="Final table unlocks at season end" text="All five categories are computed from authoritative game state." /> : (
          <table className="data-table final-table">
            <thead><tr><th>#</th><th>Franchise</th><th>Championship</th><th>Finance</th><th>Squad</th>
              <th>Infrastructure</th><th>Collections</th><th>Total</th></tr></thead>
            <tbody>{finals.map(r => <tr key={r.id} className={r.id === champion?.id ? 'champion' : ''}>
              <td>{r.final_rank}</td><td><span className="team-color" style={{ background: r.color }} />{r.name}</td>
              <td>{r.championship}</td><td>{r.finance}</td><td>{r.squad}</td><td>{r.infrastructure}</td>
              <td>{r.collections}</td><td><strong>{r.total}</strong></td>
            </tr>)}</tbody>
          </table>
        )}
      </Panel>
    </div>
  )
}

function ButtonLike({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
  return <button type="button" className="btn btn-gold" onClick={onClick}>{children}</button>
}
