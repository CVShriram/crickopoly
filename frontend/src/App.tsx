import { useApp } from './store'
import { Shell } from './components/Shell'
import { Toasts } from './components/Toasts'
import { Landing } from './screens/Landing'
import { Lobby } from './screens/Lobby'
import { Draft } from './screens/Draft'
import { Board } from './screens/Board'
import { Squad } from './screens/Squad'
import { Auctions } from './screens/Auctions'
import { Markets } from './screens/Markets'
import { Match } from './screens/Match'
import { Tournament } from './screens/Tournament'
import { Ledger } from './screens/Ledger'
import { Admin } from './screens/Admin'
import { Results } from './screens/Results'
import { HowTo } from './screens/HowTo'
import React from 'react'

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('Crickopoly UI error', error, info)
    // A bad saved session must never trap the manager in an error loop.
    // Clear only local pointers; the room itself stays safe on the server.
    try {
      localStorage.removeItem('fg-session')
      localStorage.removeItem('fg-sessions')
      Object.keys(sessionStorage).forEach(key => {
        if (key.startsWith('fg-tile-intro-')) sessionStorage.removeItem(key)
      })
    } catch { /* storage unavailable */ }
  }

  private recover = () => {
    try {
      localStorage.removeItem('fg-session')
      localStorage.removeItem('fg-sessions')
    } catch { /* storage unavailable */ }
    window.location.assign(window.location.pathname)
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24,
          background: '#071421', color: '#e8eef3', fontFamily: 'system-ui, sans-serif', textAlign: 'center' }}>
          <div>
            <h1 style={{ margin: '0 0 8px' }}>Something went wrong</h1>
            <p style={{ opacity: .75, maxWidth: 520 }}>{this.state.error.message}</p>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap', marginTop: 16 }}>
              <button type="button" onClick={this.recover}
                style={{ padding: '10px 18px', borderRadius: 10, border: '1px solid #c8a24b',
                  background: '#c8a24b', color: '#08131d', fontWeight: 700, cursor: 'pointer' }}>
                Back to saved games
              </button>
              <button type="button" onClick={() => window.location.reload()}
                style={{ padding: '10px 18px', borderRadius: 10, border: '1px solid #35546b',
                  background: 'transparent', color: '#e8eef3', fontWeight: 700, cursor: 'pointer' }}>
                Reload game
              </button>
            </div>
            <details style={{ marginTop: 18, maxWidth: 560, textAlign: 'left', opacity: .6 }}>
              <summary style={{ cursor: 'pointer' }}>Error details</summary>
              <pre style={{ whiteSpace: 'pre-wrap', fontSize: 11, maxHeight: 160, overflow: 'auto' }}>
                {this.state.error.stack || this.state.error.message}
              </pre>
            </details>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

export default function App() {
  const { app, dispatch } = useApp()
  const started = Boolean(app.state?.started)
  const view = started || app.view === 'howto' || app.view === 'lobby'
    ? app.view
    : 'landing'

  let screen: React.ReactNode
  switch (view) {
    case 'lobby': screen = <Lobby />; break
    case 'draft': screen = <Draft />; break
    case 'board': screen = <Board />; break
    case 'squad': screen = <Squad />; break
    case 'auction': screen = <Auctions />; break
    case 'markets': screen = <Markets />; break
    case 'match': screen = <Match />; break
    case 'tournament': screen = <Tournament />; break
    case 'ledger': screen = <Ledger />; break
    case 'admin': screen = <Admin />; break
    case 'results': screen = <Results />; break
    case 'howto': screen = <HowTo />; break
    default: screen = <Landing />
  }

  return (
    <ErrorBoundary>
      <>
        <Shell>{screen}</Shell>
        <Toasts />
        {app.error && (
          <div className="error-banner" onClick={() => dispatch({ type: 'ERROR', error: null })}>
            <span>⚠️ {app.error}</span><small>click to dismiss</small>
          </div>
        )}
      </>
    </ErrorBoundary>
  )
}
