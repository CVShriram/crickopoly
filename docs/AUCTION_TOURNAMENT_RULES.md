# Crickopoly: Auction + Tournament — legacy ruleset 7

> Superseded by `docs/CRICKET_STRATEGY_MONOPOLY_RULES.md` (ruleset 8). Kept only as a record of the previous build.


A fantasy cricket drafting game. No board, no rent, no property. Build a squad from real cricketers, then win a short tournament.

## The 30-second explanation

> Everyone gets **1,200 FC**. Eighteen real cricketers come up for auction one by one. Secretly bid on the current player — highest bid wins them. Then pick a **captain** and a **tactic**, and play a quick round-robin tournament. Your cricketers' real **BAT** and **BOWL** ratings decide the scores. Most tournament points wins.

## Phase 1 — Auction

- 2–6 managers. Each starts with **1,200 FC**.
- **18 lots**, each a different real cricketer active 2015–2023.
- For each lot, every manager submits one sealed bid (or passes).
- Highest bid wins the player and pays the bid. Ties go to the manager earlier in the rotation.
- Bots bid automatically using the player's rating and their remaining budget.
- Tap **NEXT** after each result to show the next lot.

## Phase 2 — Tournament

- Every manager plays every other manager once.
- Before each match you may change:
  - **Captain** — their BAT counts double and their BOWL adds to your attack.
  - **Tactic** — Attack: +25 runs. Balanced: +10 runs, −3 wickets. Defensive: −5 runs, −8 wickets.
- Match score:
  - `runs = sum of your top 6 BAT + captain BAT × 2 + tactic runs`
  - `wickets = (sum of your top 3 BOWL) / 4 + captain BOWL / 10 + tactic wickets`
  - `score = runs − wickets × 4`
- Higher score wins. Win = **2 points**, tie = **1 point** each.
- Most points wins the cup. Ties break on total score.

## Why it is not luck

The auction is about **budget judgement**: spend early on a star or save for several good players. The tournament is about **squad building**, **captain choice** and **tactic selection**. Scores come from real ratings, not dice.

## Safety

Virtual FC only. No deposits, withdrawals, wagering, real-money prizes, player photos, likenesses, logos or league branding. Player names are factual data only.
