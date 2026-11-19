import { useApp } from '../store'

const RULES = [
  { icon: '🧑‍🤝‍🧑', title: 'Draft your opener', text: 'Choose one famous cricketer or build a custom batsman before the match. Every identity has identical stats: 3 wickets, level 1, and the same upgrade path. Two managers cannot pick the same famous cricketer.' },
  { icon: '🎲', title: 'Roll & move', text: 'Roll two dice on your turn. Doubles earn another roll, up to three in a row. Your active batsman is the one who moves and scores.' },
  { icon: '🔁', title: 'Manage your roster', text: 'You can own up to five batsmen. Switch your active batsman before rolling to protect a low-wicket player or promote a upgraded one. Retired batsmen cannot return.' },
  { icon: '1️⃣', title: 'Run tiles', text: '1 RUN, 2 RUNS and 4 RUNS award that exact number of runs. Coins and runs are separate currencies.' },
  { icon: '🚀', title: 'Sixes scale', text: 'Landing on 6 RUNS scores 6 × your active batsman level. Upgrade a batsman from level 1 to 5 to double and triple this reward. Wickets never change when upgrading.' },
  { icon: '🚫', title: 'No Ball', text: 'Bonus runs = normal turns since the last No Ball × 6. You also get an extra turn and one wicket protection. Landing turns restart the count; extra turns do not.' },
  { icon: '🎯', title: 'Bowlers', text: 'A bowler is a stationary property. Landing on a rival bowler pays its landing fee and costs your active batsman one wicket — unless No Ball protection absorbs it. The owner always receives the fee.' },
  { icon: '🥎', title: 'Fielders', text: 'Fielders charge a landing fee only. No wicket and no runs are lost. Useful for steady income with no risk to your batsmen.' },
  { icon: '🧤', title: 'Wicketkeepers', text: 'Keepers transfer coins and deduct runs from the visitor. They never take a wicket. Higher tiers deduct more runs.' },
  { icon: '🛒', title: 'Recruitment', text: 'Recruitment tiles open a transfer market. Sign a globally unclaimed cricketer for 250 coins if you have fewer than five batsmen. You may decline.' },
  { icon: '⚠️', title: 'Debt recovery', text: 'If you cannot pay a fee, sell or downgrade properties to raise coins. If you cannot recover, you are eliminated, settle what you can, and your properties transfer to the creditor.' },
  { icon: '🏆', title: 'Victory', text: 'By default, the last manager standing wins. The host can choose turn-limit ranking instead, comparing runs, wickets, batsmen, coins, properties and upgrades.' },
]

export function HowToPlay() {
  const { dispatch } = useApp()
  return (
    <div className="screen-bg sub-screen">
      <header className="screen-topbar">
        <div className="brand-mark small"><span className="brand-ball">🏏</span> CRICKET <b>MONOPOLY</b></div>
        <nav className="topbar-nav"><button onClick={() => dispatch({ type: 'VIEW', view: 'landing' })}>← Home</button></nav>
      </header>
      <div className="sub-wrap">
        <span className="eyebrow">THE RULEBOOK</span>
        <h1>How to play</h1>
        <p className="muted lead">A cricket economy where survival beats wealth. Here is everything you need to know.</p>
        <div className="rules-grid">
          {RULES.map((rule, i) => (
            <article key={i} className="rule-card">
              <span className="rule-icon">{rule.icon}</span>
              <h3>{rule.title}</h3>
              <p>{rule.text}</p>
            </article>
          ))}
        </div>
        <div className="rules-footer">
          <h3>Special spaces</h3>
          <p>Free Hit nullifies the next bowling attack. Injury stops a batsman scoring. Event cards and challenges can change everything in an instant. Auction House sells an unowned property to the highest bidder.</p>
        </div>
      </div>
    </div>
  )
}
