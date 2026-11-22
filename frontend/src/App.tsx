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

export default function App() {
  const { app, dispatch } = useApp()
  const started = Boolean(app.state?.started)
  const view = started || app.view === 'howto' ? app.view : 'landing'

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
    <>
      <Shell>{screen}</Shell>
      <Toasts />
      {app.error && (
        <div className="error-banner" onClick={() => dispatch({ type: 'ERROR', error: null })}>
          <span>⚠️ {app.error}</span><small>click to dismiss</small>
        </div>
      )}
    </>
  )
}
