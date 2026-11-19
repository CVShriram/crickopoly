import { useApp } from '../store'
import { BatsmanAvatar } from '../components/BatsmanAvatar'
import { activeBatsman } from '../types'

const ACHIEVEMENTS: Record<string, string> = {
  first_purchase: 'First signing — buy your first property',
  century: 'Century — reach 100 runs',
  five_wickets: 'Five-fer — take 5 wickets',
  stadium_owner: 'Groundskeeper — own a stadium',
  survivor: 'Survivor — reach round 5',
}

export function Profile() {
  const { app, dispatch } = useApp()
  const state = app.state
  const me = state?.players.find(p => p.id === app.session?.playerId)
  if (!state || !me) return <div className="screen-bg loading-screen">Loading profile…</div>
  const usable = me.batsmen.filter(b => b.usable)
  const wicketsLeft = usable.reduce((sum, b) => sum + b.wickets, 0)
  const active = activeBatsman(me)
  const myTx = state.transactions.filter(t => t.player_id === me.id).slice(-12).reverse()

  return (
    <div className="screen-bg sub-screen">
      <header className="screen-topbar">
        <div className="brand-mark small"><span className="brand-ball">🏏</span> CRICKET <b>MONOPOLY</b></div>
        <nav className="topbar-nav">
          <button className="active">Profile</button>
          <button onClick={() => dispatch({ type: 'VIEW', view: 'game' })}>← Back to board</button>
        </nav>
      </header>
      <div className="sub-wrap narrow">
        <div className="profile-hero">
          <div className="lobby-avatar huge" style={{ background: me.color }}>{me.avatar}</div>
          <div>
            <span className="eyebrow">MANAGER PROFILE</span>
            <h1>{me.name}</h1>
            <p className="muted">{me.is_host ? 'Room host' : 'Player'} · {state.code} · {me.eliminated ? 'Eliminated' : 'In the tournament'}</p>
            {active && <div className="profile-active-batsman">
              <BatsmanAvatar person={active} size="tiny" showNumber={false} />
              <span>Active: <b>{active.name}</b> · L{active.level} · {active.wickets}/{active.max_wickets} wickets</span>
            </div>}
          </div>
        </div>

        <div className="profile-stats">
          {[
            ['Coins', me.money.toLocaleString()], ['Total runs', me.runs],
            ['Wickets left', `${wicketsLeft}`], ['Batsmen', `${me.batsmen.length}/5`],
            ['Properties', me.property_count], ['Six runs', me.stats.six_runs || 0],
            ['No-ball bonus', me.stats.no_ball_bonus_runs || 0], ['Money earned', me.stats.money_earned || 0],
            ['Money spent', me.stats.money_spent || 0], ['Wickets taken', me.stats.wickets_taken || 0],
            ['Wickets lost', me.stats.wickets_lost || 0], ['Batsman upgrades', me.stats.batsman_upgrades || 0],
            ['Recruitments', me.stats.batsmen_recruited || 0], ['Highest score', me.stats.highest_score || 0],
          ].map(([label, value]) => (
            <div key={label} className="profile-stat"><span>{label}</span><strong>{value}</strong></div>
          ))}
        </div>

        <section className="profile-section">
          <div className="panel-heading"><span className="eyebrow">HONOURS</span><h3>Achievements</h3></div>
          <div className="achievement-grid">
            {Object.entries(app.config?.achievements || ACHIEVEMENTS).map(([key, text]) => (
              <div key={key} className={`achievement ${me.achievements.includes(key) ? 'unlocked' : ''}`}>
                <span>{me.achievements.includes(key) ? '🏅' : '🔒'}</span><p>{text}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="profile-section">
          <div className="panel-heading"><span className="eyebrow">LEDGER</span><h3>Recent transactions</h3></div>
          <div className="ledger">
            {myTx.length === 0 && <p className="muted">No transactions yet.</p>}
            {myTx.map((tx, i) => (
              <div key={i} className="ledger-row">
                <span className={tx.type === 'credit' ? 'credit' : 'debit'}>{tx.type === 'credit' ? '+' : '−'}{tx.amount}</span>
                <span>{tx.reason}</span>
                <strong>{tx.balance}</strong>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}
