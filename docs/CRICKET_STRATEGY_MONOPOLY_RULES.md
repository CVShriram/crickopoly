# Crickopoly: Strategy League (ruleset 8)

Monopoly's board and buying, but every meeting with a rival is a **cricket decision**, not a fixed rent.

## The 30-second explanation

> Roll, move and buy squares like Monopoly. When you land on a rival's **player square**, you don't just pay rent — you play a ball. You pick a **shot**, the owner picks a **bowling plan**, and your players' real **BAT/BOWL** ratings decide the runs and wickets. Own a full set to unlock upgrades, trade squares, and win with the most runs after 3 laps.

## Board

- 52 squares: 32 country player markets (BAT / BOWL / WK / ALL-ROUNDER), 8 grounds, 8 event squares, 4 corners.
- Buy unowned squares when you land on them. Starting FC: **1,500**. Starting wickets: **3**.

## The cricket contest (the strategy)

Land on a rival's **player market**:

- **You bat** — choose `ATTACK`, `STEADY` or `DEFEND`.
- **The owner bowls** — choose `YORKER`, `LENGTH` or `SPIN` (bots choose automatically).
- Both choices are hidden until they are both in.

Runs and wicket chance come from:

- your best signed batter's **BAT** rating,
- the market star's **BOWL** rating (improved by upgrades),
- a small match-up bonus/penalty for the shot vs plan,
- a tiny seeded variation so the same move is not identical every time.

| Shot | Runs | Wicket risk |
|---|---|---|
| ATTACK | most | highest |
| STEADY | medium | medium |
| DEFEND | fewest | lowest |

| Plan | Runs conceded | Wicket chance |
|---|---|---|
| YORKER | fewer | higher |
| LENGTH | balanced | balanced |
| SPIN | more | lower |

Extra outcomes:

- 🧤 **Wicketkeeper market** — you also **miss your next turn**.
- If a wicket falls, you lose **1 wicket** and pay the owner extra runs.
- Grounds still charge simple FC rent; your first ground is your **home ground** (+50% FC rent, +100 FC and +50 runs when you land on it).

## Upgrades and squads

- You may upgrade only after you own **a batsman, a bowler, a wicketkeeper and a ground**.
- Upgrades raise the market star's BOWL rating (and charge more runs), max level 4. Cost: `60 + 40 × level`.
- Auctions and events can sign real players, strengthening your batting and bowling ratings.

## Trading

On your turn, **TRADE** swaps one of your squares for one rival's square. No money changes hands. The rival accepts or declines; bots decide automatically.

## Winning

After **3 laps**, the manager with the **most runs** wins. Ties break on FC. Lose all 3 wickets and you are out; last manager standing also wins.

## Safety

Virtual FC and runs only. No deposits, withdrawals, wagering, real-money prizes, player photos, likenesses, logos or league branding. Player names are factual data only.
