import { useApp } from './store'
import { Landing } from './screens/Landing'
import { Lobby } from './screens/Lobby'
import { Game } from './screens/Game'
import { Squad } from './screens/Squad'
import { Profile } from './screens/Profile'
import { Results } from './screens/Results'
import { HowToPlay } from './screens/HowToPlay'
import { Leaderboard } from './screens/Leaderboard'
import { Toasts } from './components/Toasts'

export default function App() {
  const { app, dispatch } = useApp()
  let screen
  switch (app.view) {
    case 'lobby': screen = <Lobby />; break
    case 'game': screen = <Game />; break
    case 'squad': screen = <Squad />; break
    case 'profile': screen = <Profile />; break
    case 'results': screen = <Results />; break
    case 'howto': screen = <HowToPlay />; break
    case 'leaderboard': screen = <Leaderboard />; break
    default: screen = <Landing />
  }
  return (
    <>
      {screen}
      <Toasts />
      {app.error && (
        <div className="error-banner" onClick={() => dispatch({ type: 'ERROR', error: null })}>
          ⚠️ {app.error} <span>× dismiss</span>
        </div>
      )}
    </>
  )
}
