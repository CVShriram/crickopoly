import { useState } from 'react'
import { useApp } from '../store'
import { sound } from '../sound'
import { BatsmanAvatar } from '../components/BatsmanAvatar'
import { UpgradeModal } from '../components/Modals'
import { activeBatsman, type Asset, type Batsman } from '../types'

const GROUPS: Array<{ kind: Asset['kind']; label: string; icon: string }> = [
  { kind: 'bowler', label: 'Bowlers', icon: '🎯' },
  { kind: 'keeper', label: 'Wicket Keepers', icon: '🧤' },
  { kind: 'fielder', label: 'Fielders', icon: '🥎' },
  { kind: 'stadium', label: 'Stadiums', icon: '🏟️' },
]

export function Squad() {
  const { app, dispatch, send } = useApp()
  const state = app.state
  const me = state?.players.find(p => p.id === app.session?.playerId)
  const [target, setTarget] = useState('')
  const [giveAssets, setGiveAssets] = useState<string[]>([])
  const [wantAssets, setWantAssets] = useState<string[]>([])
  const [giveMoney, setGiveMoney] = useState(0)
  const [wantMoney, setWantMoney] = useState(0)
  const [upgrade, setUpgrade] = useState<Batsman | null>(null)

  if (!state || !me) return <div className="screen-bg loading-screen">Loading squad…</div>

  const toggle = (list: string[], set: (v: string[]) => void, id: string) =>
    set(list.includes(id) ? list.filter(x => x !== id) : [...list, id])

  const propose = () => {
    if (!target || (giveAssets.length === 0 && giveMoney === 0 && wantAssets.length === 0 && wantMoney === 0)) return
    sound.play('click')
    send('trade', { to: target, give_assets: giveAssets, give_money: giveMoney,
      want_assets: wantAssets, want_money: wantMoney })
    setGiveAssets([]); setWantAssets([]); setGiveMoney(0); setWantMoney(0); setTarget('')
  }

  const otherPlayers = state.players.filter(p => p.id !== me.id && !p.eliminated)
  const theirAssets = otherPlayers.find(p => p.id === target)?.assets.filter(a => a.space_id !== null) || []
  const active = activeBatsman(me)

  return (
    <div className="screen-bg sub-screen">
      <header className="screen-topbar">
        <div className="brand-mark small"><span className="brand-ball">🏏</span> CRICKET <b>MONOPOLY</b></div>
        <nav className="topbar-nav">
          <button className="active" onClick={() => dispatch({ type: 'VIEW', view: 'squad' })}>Squad</button>
          <button onClick={() => dispatch({ type: 'VIEW', view: 'game' })}>← Back to board</button>
        </nav>
      </header>

      <div className="sub-wrap">
        <div className="sub-head">
          <div>
            <span className="eyebrow">TEAM MANAGEMENT</span>
            <h1>Your squad</h1>
            <p className="muted">Upgrade batsmen to multiply sixes, manage defensive properties, or negotiate a trade.</p>
          </div>
          <div className="head-metrics">
            <div><span>Money</span><strong>{me.money.toLocaleString()}</strong></div>
            <div><span>Runs</span><strong>{me.runs}</strong></div>
            <div><span>Properties</span><strong>{me.property_count}</strong></div>
          </div>
        </div>

        <section className="squad-roster">
          <div className="panel-heading">
            <span className="eyebrow">🏏 BATSMEN</span>
            <h3>{me.batsmen.length} / 5 signed · {active?.name ?? 'none active'}</h3>
          </div>
          <div className="squad-roster-grid">
            {me.batsmen.map(b => (
              <article key={b.id} className={`squad-batsman ${b.id === active?.id ? 'active' : ''} ${!b.usable ? 'retired' : ''}`}
                style={{ ['--jersey' as any]: b.jersey_color }}>
                <BatsmanAvatar person={b} size="small" />
                <strong>{b.name}</strong>
                <span>{b.country} · Level {b.level}</span>
                <div className="batsman-mini-stats">
                  <span>🏏 {b.wickets}/{b.max_wickets}</span>
                  <span>🚀 {b.six_runs}</span>
                </div>
                <button className="btn small gold" disabled={b.retired || b.level >= 5}
                  onClick={() => { sound.play('click'); setUpgrade(b) }}>
                  {b.level >= 5 ? 'Max level' : `Upgrade · ${b.upgrade_cost ?? 0}`}
                </button>
              </article>
            ))}
            {me.batsmen.length === 0 && <p className="muted">No batsmen signed yet.</p>}
          </div>
        </section>

        <div className="squad-grid">
          {GROUPS.map(group => {
            const assets = me.assets.filter(a => a.kind === group.kind && a.space_id !== null)
            return (
              <section key={group.kind} className="squad-group">
                <div className="panel-heading">
                  <span className="eyebrow">{group.icon} {group.label.toUpperCase()}</span>
                  <h3>{assets.length} owned</h3>
                </div>
                <div className="asset-list">
                  {assets.length === 0 && <p className="muted empty-note">No {group.label.toLowerCase()} owned yet.</p>}
                  {assets.map(asset => (
                    <article key={asset.id} className="asset-card">
                      <div className="asset-top">
                        <span className="asset-icon">{group.icon}</span>
                        <div className="asset-title">
                          <strong>{asset.name}</strong>
                          <span className="muted">{asset.config?.blurb || 'Club player'}</span>
                        </div>
                        <span className="level-tag">LVL {asset.level + 1}</span>
                      </div>
                      <div className="asset-stats">
                        <span>Landing fee <b>{asset.effective_fee ?? 0}</b></span>
                        {asset.kind === 'keeper' && <span>Run penalty <b>{asset.run_penalty ?? 0}</b></span>}
                        {asset.kind === 'stadium' && <span>Boost <b>{Math.round((asset.effective_boost ?? 0) * 100)}%</b></span>}
                        <span>Value <b>{asset.sale_value ?? 0}</b></span>
                      </div>
                      <div className="asset-actions">
                        <button className="btn small" disabled={asset.level >= 3 || me.money < (asset.upgrade_cost ?? 9999)}
                          onClick={() => { sound.play('buy'); send('upgrade', { asset_id: asset.id }) }}>
                          Upgrade property · {asset.upgrade_cost ?? 0}
                        </button>
                        <button className="btn small ghost" onClick={() => { sound.play('money'); send('sell', { asset_id: asset.id }) }}>
                          Sell · +{asset.sale_value ?? 0}
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            )
          })}
        </div>

        <section className="trade-builder">
          <div className="panel-heading">
            <span className="eyebrow">NEGOTIATION TABLE</span>
            <h3>Propose a trade</h3>
          </div>
          <div className="trade-grid">
            <div>
              <label className="field"><span>Trade with</span>
                <select value={target} onChange={e => { setTarget(e.target.value); setWantAssets([]) }}>
                  <option value="">Select a manager…</option>
                  {otherPlayers.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </label>
              <h4>You give</h4>
              <div className="trade-assets">
                {me.assets.filter(a => a.space_id !== null).map(a => (
                  <button key={a.id} className={`chip ${giveAssets.includes(a.id) ? 'selected' : ''}`}
                    onClick={() => toggle(giveAssets, setGiveAssets, a.id)}>{a.name}</button>
                ))}
              </div>
              <label className="field"><span>Your coins</span>
                <input type="number" min={0} max={me.money} value={giveMoney}
                  onChange={e => setGiveMoney(Math.max(0, Number(e.target.value)))} />
              </label>
            </div>
            <div className="trade-divider">⇄</div>
            <div>
              <h4>You receive</h4>
              <div className="trade-assets">
                {theirAssets.map(a => (
                  <button key={a.id} className={`chip ${wantAssets.includes(a.id) ? 'selected' : ''}`}
                    onClick={() => toggle(wantAssets, setWantAssets, a.id)}>{a.name}</button>
                ))}
              </div>
              <label className="field"><span>Their coins</span>
                <input type="number" min={0} value={wantMoney}
                  onChange={e => setWantMoney(Math.max(0, Number(e.target.value)))} />
              </label>
            </div>
          </div>
          <button className="btn primary" disabled={!target} onClick={propose}>Send trade offer</button>
          <p className="hint">Both managers must agree. Assets and coins are validated again when accepted.</p>
        </section>
      </div>

      {upgrade && <UpgradeModal batsman={upgrade} me={me} config={app.config} send={send}
        onClose={() => setUpgrade(null)} />}
    </div>
  )
}
