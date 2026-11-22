# Crickopoly: Stadium Tycoon — legacy ruleset 2

> Superseded by `docs/CARD_BATTLE_RULES.md` (ruleset 3). Kept only as a record of the previous build.

Replaces the old draft/economy/tournament rules. Keeps the existing real-cricketer roster, 52-tile board, 8 stadiums, 2–6 managers, rooms, sockets and save table. New rooms use ruleset 2.

## Feel

Monopoly movement and ownership, with a cricket decision at every contest. You roll, move, buy grounds, pay to sign real cricketers, and when rent is due you play a **tactic duel** instead of watching an automatic number change.

## Core loop

1. Roll dice, move 1–6 tiles.
2. Resolve the tile you land on:
   - **Stadium** — unowned: buy it. Owned by a rival: start a duel for rent.
   - **Player market** — sign one of three real cricketers from that country/role for a fixed fee.
   - **Auction** — sealed bid for a featured star.
   - **Matchday** — challenge the AI or the ground owner; choose a tactic.
   - **Pitch report / sponsor / event** — small FC swing, free card, or tactic upgrade.
   - **Season start** — collect stipend.
3. Play the duel: both managers secretly choose one tactic card.
4. Read one scorecard, pay the adjusted rent, end turn.

No submenus, no hidden spreadsheets. One board, one action bar, one modal at a time.

## Squad

- Every manager starts with 6 free real cricketers: 2 batters, 2 bowlers, 1 wicketkeeper, 1 all-rounder. Starter countries rotate, so no two managers begin with the same squad.
- Market and auction tiles add players, up to 15.
- The best XI is auto-selected by role and rating. No manual XI screen.
- Squad strength is shown as three numbers: **BAT / BOWL / FIELD**.

## Tactic cards

Each manager holds 5 cards. After use, draw a replacement from the deck.

Batting cards:
- **Powerplay Charge** — +24 runs early, +2 wicket risk.
- **Anchor Chase** — +10 runs, −2 wicket risk, strong on slow pitches.
- **Death Over Slog** — +34 runs late, +3 wicket risk.

Bowling cards:
- **Swing Assault** — +3 wickets early, +8 runs conceded, strong on green pitches.
- **Spin Web** — +1 wicket, −18 runs conceded, strong on dry pitches.
- **Yorker Rampage** — +2 wickets late, +12 runs conceded.

Balanced:
- **All-Round Pressure** — +8 runs, +1 wicket, works on every pitch.

## Pitch conditions

Pitch changes each full round and is shown on the board:

| Pitch | Effect |
| --- | --- |
| Flat | Batting cards +10 runs |
| Green | Swing Assault +2 wickets |
| Dry | Spin Web −10 extra runs conceded |
| Slow | Anchor Chase +12 runs, Powerplay Charge −8 runs |

## Duel resolution

Both cards are revealed together. The UI shows one scorecard:

```
You         178/6   Powerplay Charge
Owner       164/8   Spin Web
You win by 14 runs · Rent 120 FC → 60 FC
```

Simplified model:

- `bat = squad.BAT/4 + card.runBonus + pitch.runBonus`
- `bowl = rival.BOWL/6 + rival.card.wicketBonus + homeGroundBonus`
- `runs = clamp(112 + bat - bowl/2 + roll(-8..8) - rival.card.suppression, 70, 250)`
- `wickets = clamp(4 + bowl/8 - bat/12 + card.risk + roll(0..2), 0, 10)`
- Higher score wins. Score = `runs - wickets * 4`.

Rent after a duel:

| Result | Rent paid |
| --- | --- |
| Challenger wins | 50% of printed rent |
| Owner wins | 100% |
| Owner wins by 40+ runs | 150% |

If a manager cannot pay, they automatically sell their cheapest signed players (never below the six free starters). If they still cannot pay, their cheapest ground transfers to the creditor at 70% value.

## Auctions

One star at a time. Three bid buttons: **base**, **+20**, **+50**, plus **Pass**. Highest bidder pays and signs the player. Ties are broken by turn order.

## Winning

After 8 rounds, highest **Brand Value** wins:

```
Brand Value = cash
            + 1.5 × (sum of owned stadium prices)
            + 20 × (number of signed players)
            + 200 × (number of match duels won)
```

A live standings panel always shows this number, so the goal is never a surprise.

## Safety

Virtual FC only. No deposits, withdrawals, wagering, real-money value, player photos, likenesses, logos or league branding.
