# Crickopoly: Cricket Card Battle

A complete rules replacement for Stadium Tycoon. Same real cricketers, rooms, sockets and saves; a much simpler game that can be explained in 30 seconds.

## The 30-second explanation

> Each round, every manager secretly picks one real cricketer card and one tactic. Your card's **BAT** rating adds runs to your innings; your card's **BOWL** rating makes opponents lose wickets. The pitch changes the score. Highest score wins the round. After 6 rounds, most round wins takes the title.

## Setup

- 2–6 managers, human or AI.
- Each manager gets **8 unique real cricketer cards** from the preserved 2015–2023 roster.
- Three tactics are always available: **Attack**, **Anchor**, **Slog**.
- The pitch rotates each round: **Flat**, **Green**, **Dry**, **Slow**.

## One round

1. Everyone picks one cricketer card and one tactic.
2. All picks are revealed together.
3. Each innings is scored as:
   - `runs = 100 + card.BAT + tactic.runs + pitch.runs + small variance`
   - `wickets = opponents' average BOWL / 6 + tactic.wickets + pitch.wickets`
   - `score = runs - wickets × 4`
4. Highest score wins the round. Ties are broken by higher total score.
5. Click **CONTINUE** to reveal the next round.

## Tactics

| Tactic | Effect | Best on |
| --- | --- | --- |
| ⚡ Attack | +25 runs, +1 wicket risk | Flat |
| ⚓ Anchor | +10 runs, −1 wicket risk | Slow |
| 🚀 Slog | +34 runs, +3 wicket risk | Flat; poor on Green |

## Pitches

| Pitch | Effect |
| --- | --- |
| 🏏 Flat | Batters +10 runs |
| 🌿 Green | Bowlers +1 wicket |
| 🏜️ Dry | Batters −10 runs |
| 🐢 Slow | Anchor +12 runs, Attack −8 runs |

## Winning

After all rounds, the manager with the most round wins is champion. Ties are broken by total score across all rounds. The standings bar is always visible.

## Safety

Virtual FC only. No deposits, withdrawals, wagering, real-money prizes, player photos, likenesses, logos or league branding. Player names are factual data only.
