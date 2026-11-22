import React, { useMemo, useState } from 'react'
import { useApp } from '../store'
import { Badge, Button, Empty, Panel, Segmented, Stat } from '../components/UI'
import { money, signed, timeAgo, titleCase } from '../utils'

export function Ledger() {
  const { app, send, continueRoom, refreshSaved, dispatch } = useApp()
  const state = app.state!
  const [fid, setFid] = useState(state.you || 'all')
  const [kind, setKind] = useState<'all' | 'credit' | 'debit'>('all')

  const rows = useMemo(() => {
    return [...(state.transactions || [])]
      .filter(t => fid === 'all' || t.franchise_id === fid || t.fid === fid)
      .filter(t => kind === 'all' || (kind === 'credit' ? t.amount > 0 : t.amount < 0))
      .reverse()
  }, [state.transactions, fid, kind])

  const totalIn = rows.filter(r => r.amount > 0).reduce((a, r) => a + r.amount, 0)
  const totalOut = rows.filter(r => r.amount < 0).reduce((a, r) => a + Math.abs(r.amount), 0)
  const isHost = state.host_id === app.session?.playerId

  return (
    <div className="page ledger-page">
      <div className="page-head">
        <div><small>FINANCIAL CONTROL</small><h1>FC ledger & saved seasons</h1>
          <p>Every credit and debit is immutable, timestamped and attributed to a round and action.</p></div>
        <Button variant="subtle" onClick={refreshSaved}>Refresh saves</Button>
      </div>

      <div className="dashboard-strip compact">
        <Stat label="Entries" value={rows.length} icon="📒" />
        <Stat label="Credits" value={money(totalIn)} tone="green" icon="⬆️" />
        <Stat label="Debits" value={money(totalOut)} tone="danger" icon="⬇️" />
        <Stat label="Net flow" value={signed(totalIn - totalOut)} tone="gold" icon="💹" />
      </div>

      <Panel title="Transaction ledger" subtitle="Round · date · type · description · amount · balance after" icon="📒"
        action={<div className="filter-row">
          <select value={fid} onChange={e => setFid(e.target.value)}>
            <option value="all">All franchises</option>
            {Object.values(state.franchises).map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
          <Segmented value={kind} onChange={setKind} options={[
            { value: 'all', label: 'All' }, { value: 'credit', label: 'Credits' }, { value: 'debit', label: 'Debits' },
          ]} />
        </div>}>
        {rows.length === 0 ? <Empty title="No matching transactions" /> : (
          <table className="data-table ledger-table">
            <thead><tr><th>ID</th><th>Round</th><th>Franchise</th><th>Type</th><th>Description</th><th>Amount</th><th>Balance after</th><th>Time</th></tr></thead>
            <tbody>{rows.map(t => <tr key={t.id}>
              <td><small>{t.id}</small></td><td>R{t.round}</td>
              <td>{state.franchises?.[t.franchise_id || t.fid]?.name || '—'}</td>
              <td><Badge tone={t.amount > 0 ? 'green' : 'danger'}>{titleCase(t.kind || t.type || 'transfer')}</Badge></td>
              <td>{t.desc || t.description}</td>
              <td className={t.amount > 0 ? 'positive' : 'negative'}>{signed(t.amount)}</td>
              <td>{money(t.balance_after ?? t.balanceAfter)}</td>
              <td>{t.ts ? timeAgo(t.ts) : '—'}</td>
            </tr>)}</tbody>
          </table>
        )}
      </Panel>

      <div className="save-layout">
        <Panel title="Continue / history" subtitle="Saves survive refresh, server restarts and browser reloads" icon="💾">
          {app.saved.length === 0 ? <Empty title="No saved rooms" /> : (
            <div className="saved-list">
              {app.saved.map(row => (
                <button key={row.room_id} type="button" className="saved-row" onClick={() => continueRoom(row)}>
                  <span className="saved-icon">{row.finished ? '🏆' : '💾'}</span>
                  <span className="saved-info"><strong>{row.code} · Round {row.round}</strong>
                    <small>{row.franchises.join(' vs ')} · {row.matches} matches · {row.phase}</small></span>
                  <span className="saved-time">{timeAgo(row.updated_at)}</span>
                </button>
              ))}
            </div>
          )}
        </Panel>
        <Panel title="Season controls" subtitle="Host-only destructive actions" icon="⚙️">
          <div className="callout"><strong>Autosave is always on</strong>
            <p>Every WebSocket action is persisted immediately. Use Continue or open the invite link to rejoin this room.</p></div>
          <div className="invite-box">{window.location.origin}{window.location.pathname}?code={state.code}&token={app.session?.playerId}</div>
          {isHost && <Button variant="danger" block onClick={() => {
            if (window.confirm('Restart this season? All current progress will be replaced.')) {
              send('restart', {}); refreshSaved(); dispatch({ type: 'VIEW', view: 'draft' })
            }
          }}>🔁 Restart this season</Button>}
        </Panel>
      </div>
    </div>
  )
}
