import React from 'react'
import { useApp, type View } from '../store'
import { me } from '../types'
import { money } from '../utils'
import { Avatar, Badge } from './UI'

const NAV: Array<{ id: View; label: string; icon: string }> = [
  { id: 'board', label: 'Board', icon: '🎲' },
  { id: 'squad', label: 'Squad', icon: '👥' },
  { id: 'auction', label: 'Auctions', icon: '🔨' },
  { id: 'markets', label: 'Assets', icon: '🏟️' },
  { id: 'match', label: 'Matches', icon: '🏏' },
  { id: 'tournament', label: 'Table', icon: '🏆' },
  { id: 'ledger', label: 'Ledger', icon: '📒' },
  { id: 'admin', label: 'Studio', icon: '⚙️' },
]

export function Shell({ children }: { children: React.ReactNode }) {
  const { app, dispatch, setSession } = useApp()
  const f = me(app.state)
  const view = app.view
  const publicView = !app.state?.started || view === 'howto' || view === 'results'

  return (
    <div className="app-shell">
      <header className="topbar">
        <button type="button" className="brand" onClick={() => dispatch({ type: 'VIEW', view: 'board' })}>
          <span className="brand-mark">🏏</span>
          <span><strong>CRICKOPOLY</strong><small>FRANCHISE LEAGUE</small></span>
        </button>

        {!publicView && (
          <nav className="nav">
            {NAV.map(item => (
              <button key={item.id} type="button"
                className={view === item.id ? 'active' : ''}
                onClick={() => dispatch({ type: 'VIEW', view: item.id })}>
                <span>{item.icon}</span><em>{item.label}</em>
              </button>
            ))}
          </nav>
        )}

        <div className="top-actions">
          {app.state?.started && (
            <span className={`conn ${app.connected ? 'online' : 'offline'}`}
              title={app.connected ? 'Live connection' : 'Reconnecting…'} />
          )}
          {f && (
            <div className="manager-chip">
              <Avatar franchise={f} size="sm" />
              <div><strong>{f.name}</strong><small>{money(f.balance)}</small></div>
            </div>
          )}
          {app.state && <Badge tone="gold">R{app.state.round}</Badge>}
          <button type="button" className="icon-btn" title="How to play"
            onClick={() => dispatch({ type: 'VIEW', view: 'howto' })}>?</button>
          {app.session && (
            <button type="button" className="icon-btn" title="Exit room"
              onClick={() => { setSession(null); dispatch({ type: 'STATE', state: null }) }}>⏻</button>
          )}
        </div>
      </header>
      {!publicView && (
        <div className="subbar">
          <span className="live-dot" />
          <strong>{app.state?.mode === 'classic' ? 'CLASSIC SURVIVAL' : 'STANDARD SEASON'}</strong>
          <span className="sep">/</span>
          <span>{app.state?.phase === 'playoffs' ? 'PLAYOFFS' : app.state?.phase?.toUpperCase()}</span>
          <span className="sep">/</span>
          <span>Pitch: {app.state?.gamedata?.pitches?.[app.state?.pitch]?.name || app.state?.pitch}</span>
          <span className="grow" />
          {app.state?.pending?.type === 'match_setup' && <Badge tone="gold" icon="🏏">Match lobby open</Badge>}
          {app.state?.auction && <Badge tone="danger" icon="🔨">Auction live</Badge>}
          {app.state?.transfer_window?.open && <Badge tone="green" icon="🤝">Transfer window</Badge>}
        </div>
      )}
      <main className="main-content">{children}</main>
      <footer className="footer">
        <span>Cricket Monopoly · Real names 2015-2023 · Virtual FC only</span>
        <span>Season {app.state?.season || 1} · Code {app.session?.code || '—'}</span>
      </footer>
    </div>
  )
}
