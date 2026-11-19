import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApp } from '../store'
import type { LeaderboardRow } from '../types'

export function Leaderboard() {
  const { dispatch } = useApp()
  const [rows, setRows] = useState<LeaderboardRow[]>([])
  const [matches, setMatches] = useState<any[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([api.leaderboard(50), api.history()])
      .then(([ladder, history]) => { setRows(ladder); setMatches(history) })
      .catch(() => setError('Could not load the global leaderboard.'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="screen-bg sub-screen leaderboard-screen">
      <header className="screen-topbar">
        <div className="brand-mark small"><span className="brand-ball">🏏</span> CRICKET <b>MONOPOLY</b></div>
        <nav className="topbar-nav"><button onClick={() => dispatch({ type: 'VIEW', view: 'landing' })}>← Home</button></nav>
      </header>
      <div className="sub-wrap">
        <div className="sub-head">
          <div>
            <span className="eyebrow">GLOBAL HALL OF FAME</span>
            <h1>Leaderboard</h1>
            <p className="muted">Persistent manager rankings from every completed match on this server.</p>
          </div>
          <div className="head-metrics">
            <div><span>Manager</span><strong>{rows.length}</strong></div>
            <div><span>Victories</span><strong>{rows.reduce((sum, r) => sum + r.wins, 0)}</strong></div>
            <div><span>Total runs</span><strong>{rows.reduce((sum, r) => sum + r.runs, 0)}</strong></div>
          </div>
        </div>
        {error && <p className="form-error">{error}</p>}

        <div className="panel-heading"><span className="eyebrow">CAREER STANDINGS</span><h3>Top managers</h3></div>
        <div className="ladder-card">
          <div className="ladder-head">
            <span>#</span><span>Manager</span><span>Matches</span><span>Wins</span>
            <span>Total runs</span><span>Best</span><span>Coins</span><span>Wickets</span>
          </div>
          {loading && <p className="muted ladder-empty">Loading rankings…</p>}
          {!loading && rows.length === 0 && (
            <p className="muted ladder-empty">No completed tournaments yet. Play a match to open the ladder.</p>
          )}
          {rows.map((row, i) => (
            <div key={row.player_key} className={`ladder-row ${i < 3 ? `podium podium-${i + 1}` : ''}`}>
              <span className="ladder-rank">{i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : i + 1}</span>
              <span className="ladder-name"><i style={{ background: row.color }} />{row.avatar} {row.name}</span>
              <span>{row.matches_played}</span>
              <span className="gold-text">{row.wins}</span>
              <span className="green-text">{row.runs}</span>
              <span>{row.best_runs}</span>
              <span>💰 {row.coins.toLocaleString()}</span>
              <span>🎯 {row.wickets_taken}</span>
            </div>
          ))}
        </div>

        <div className="panel-heading history-heading">
          <span className="eyebrow">MATCH ARCHIVE</span><h3>Recent tournaments</h3>
        </div>
        <div className="leaderboard-list">
          {matches.length === 0 && <p className="muted">No completed tournaments yet. Be the first!</p>}
          {matches.map((match, index) => (
            <div key={match.room_id ?? index} className="leaderboard-row">
              <span className="leaderboard-rank">{index + 1}</span>
              <span className="leaderboard-trophy">{index === 0 ? '🥇' : index === 1 ? '🥈' : index === 2 ? '🥉' : '🏏'}</span>
              <div><strong>{match.winner_name || 'Unknown manager'}</strong>
                <small>{new Date(match.finished_at).toLocaleString()}</small></div>
              <span className="muted">{match.round} rounds · {match.players?.length} managers</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
