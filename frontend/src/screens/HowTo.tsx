import React from 'react'
import { useApp } from '../store'
import { Button, Panel } from '../components/UI'

export function HowTo() {
  const { app, dispatch } = useApp()
  return (
    <div className="page howto-page">
      <div className="page-head">
        <div><small>FIELD GUIDE</small><h1>How to play</h1>
          <p>Everything you need to run a complete franchise season.</p></div>
        {app.state?.started && <Button onClick={() => dispatch({ type: 'VIEW', view: 'board' })}>← Back to game</Button>}
      </div>
      <div className="howto-grid">
        {[
          { icon: '📝', title: '1 · Draft', text: 'Each franchise drafts 15 fictional players in snake order. Build role depth: 5 batters, 5 bowlers, 2 keepers and 3 all-rounders.' },
          { icon: '🎲', title: '2 · Move', text: 'On your turn roll two dice and move clockwise around 52 tiles. Passing Season Start pays 200 FC.' },
          { icon: '🌍', title: '3 · Own', text: 'Buy unowned player markets and stadiums. Rivals pay fees when they land; completing all four roles in a country pays 120 FC.' },
          { icon: '✨', title: '4 · Events', text: 'Eight special tiles mutate state: auctions, matchday, injury reserve, training camp, sponsorship, qualifier, strategy room and recovery.' },
          { icon: '🏏', title: '5 · Match', text: 'Submit three-phase batting, bowling and field plans secretly. Once both managers lock in, a seeded T20 engine simulates every ball.' },
          { icon: '🤝', title: '6 · Trade', text: 'During transfer windows, offer players, venues, sponsors, cards and FC. The rival must explicitly confirm before anything moves.' },
          { icon: '🏋️', title: '7 · Develop', text: 'Train attributes, rehab injuries and rest fatigued players. Conditions carry into matches and affect ratings.' },
          { icon: '🏆', title: '8 · Win', text: 'After the league rounds, playoffs seed by points and NRR. Standard Season scores exactly 100 final points; Classic is pure survival.' },
        ].map(item => (
          <Panel key={item.title} title={item.title} icon={item.icon}>
            <p>{item.text}</p>
          </Panel>
        ))}
      </div>
      <Panel title="Currency & safety" subtitle="Virtual FC only" icon="💰">
        <p>Crickopoly uses a virtual ledger for gameplay. There are no deposits, withdrawals, wagering, real-money prizes or unofficial player likenesses.</p>
      </Panel>
    </div>
  )
}
