import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApp } from '../store'

export function Results() {
  const { app, dispatch } = useApp()
  const state = app.state
  const [history, setHistory] = useState<any[]>([])
  useEffect(() => { api.history().then(setHistory).catch(() => setHistory([])) }, [])
  const winner = state?.players.find(p => p.id === state.winner_id)
  const victory = [...(state?.log || [])].reverse().find(e => e.type === 'victory')
  const ranked = [...(state?.players || [])].sort((a, b) => {
    if (a.id === state?.winner_id) return -1
    if (b.id === state?.winner_id) return 1
    if (a.eliminated !== b.eliminated) return a.eliminated ? 1 : -1
    return b.runs - a.runs
  })
  const rankingRows = state?.ranking?.length ? state.ranking : ranked.map(p => ({
    player_id: p.id, name: p.name, avatar: p.avatar, runs: p.runs, money: p.money,
    batsmen: p.active_batsmen, wickets: p.batsmen.filter(b => b.usable).reduce((s, b) => s + b.wickets, 0),
    properties: p.property_count, upgrades: p.assets.reduce((s, a) => s + a.level, 0),
    eliminated: p.eliminated,
  }))

  return (
    <div className="screen-bg sub-screen">
      <header className="screen-topbar">
        <div className="brand-mark small"><span className="brand-ball">🏏</span> CRICKET <b>MONOPOLY</b></div>
        <nav className="topbar-nav">
          <button className="active">Results</button>
          {state?.started && <button onClick={() => dispatch({ type: 'VIEW', view: 'game' })}>← Back to board</button>}
          <button onClick={() => { dispatch({ type: 'STATE', state: null }); dispatch({ type: 'SESSION', session: null }); dispatch({ type: 'VIEW', view: 'landing' }) }}>Exit</button>
        </nav>
      </header>

      {!state?.started ? (
        <div className="sub-wrap">
          <div className="panel-heading"><span className="eyebrow">MATCH ARCHIVE</span><h1>Past tournaments</h1></div>
          <div className="history-list">
            {history.length === 0 && <p className="muted">No completed matches yet.</p>}
            {history.map((m, i) => (
              <div key={i} className="history-row">
                <strong>{m.winner_name || 'Unknown'}</strong>
                <span>{m.players?.length} managers · {m.round} rounds</span>
                <span className="muted">{m.finished_at}</span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="sub-wrap">
          <div className="winner-banner">
            <div className="trophy">🏆</div>
            <span className="eyebrow">{state.phase === 'over' ? 'TOURNAMENT WINNER' : 'CURRENT LEADER'}</span>
            <h1>{winner?.name || ranked[0]?.name || '—'}</h1>
            <p>{victory?.payload?.reason || (state.victory_mode === 'turn_limit' ? `Turn-limit ranking · ${state.turn_limit} rounds` : 'Last manager standing')} · {ranked[0]?.runs ?? 0} runs · {ranked[0]?.money ?? 0} coins</p>
            {state.started_at && <small>Match started {new Date(state.started_at).toLocaleString()}</small>}
          </div>

          <div className="results-grid">
            <div className="result-card wide-result">
              <div className="panel-heading"><span className="eyebrow">FINAL STANDINGS</span><h3>Ranking</h3></div>
              <div className="final-ranking">
                <div className="final-head"><span>#</span><span>Manager</span><span>Runs</span><span>Batsmen</span><span>Wickets</span><span>Coins</span><span>Assets</span></div>
                {rankingRows.map((row, i) => (
                  <div key={row.player_id} className={`final-row ${row.player_id === state.winner_id ? 'winner' : ''}`}>
                    <span>{i + 1}</span>
                    <span>{row.avatar} {row.name}{row.eliminated ? ' (OUT)' : ''}</span>
                    <span>{row.runs}</span><span>{row.batsmen}</span><span>{row.wickets}</span>
                    <span>{row.money}</span><span>{row.properties + row.upgrades}</span>
                  </div>
                ))}
              </div>
              <p className="hint">Ranking order: runs → wickets → batsmen → coins → properties & upgrades.</p>
            </div>
            <div className="result-card">
              <div className="panel-heading"><span className="eyebrow">RUNS</span><h3>Scoring chart</h3></div>
              {[...ranked].sort((a, b) => b.runs - a.runs).map(p => (
                <div key={p.id} className="bar-row">
                  <span>{p.name}</span>
                  <div className="bar-track"><i style={{ width: `${Math.min(100, p.runs * 2)}%`, background: p.color }} /></div>
                  <strong>{p.runs}</strong>
                </div>
              ))}
            </div>
            <div className="result-card">
              <div className="panel-heading"><span className="eyebrow">WICKETS</span><h3>Bowling figures</h3></div>
              {[...ranked].sort((a, b) => (b.stats.wickets_taken || 0) - (a.stats.wickets_taken || 0)).map(p => (
                <div key={p.id} className="bar-row">
                  <span>{p.name}</span>
                  <div className="bar-track"><i style={{ width: `${Math.min(100, (p.stats.wickets_taken || 0) * 12)}%`, background: p.color }} /></div>
                  <strong>{p.stats.wickets_taken || 0}</strong>
                </div>
              ))}
            </div>
            <div className="result-card">
              <div className="panel-heading"><span className="eyebrow">ECONOMY</span><h3>Wealth</h3></div>
              {[...ranked].sort((a, b) => b.money - a.money).map(p => (
                <div key={p.id} className="bar-row">
                  <span>{p.name}</span>
                  <div className="bar-track"><i style={{ width: `${Math.min(100, p.money / 25)}%`, background: p.color }} /></div>
                  <strong>{p.money}</strong>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
