import { useApp } from './store'
import { GameScreen } from './components/GameScreen'
import { Toasts } from './components/Toasts'
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
  return (
    <ErrorBoundary>
      <>
        <GameScreen />
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
