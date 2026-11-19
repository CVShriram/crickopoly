# CRICKET MONOPOLY — Development Plan & Status

## Overview

A server-authoritative, real-time multiplayer cricket-themed Monopoly game.
Players roll dice, build a cricket squad (batsmen, bowlers, wicket keepers,
fielders, stadiums), earn money and runs, take wickets from opponents, and
survive until only one manager remains.

## Architecture

```
crickopoly/
├── backend/
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py            # ALL balance values & rules (single source of truth)
│   │   ├── models.py            # dataclasses: Player, Asset, GameState, events
│   │   ├── game/
│   │   │   ├── __init__.py
│   │   │   ├── board.py         # 32-space configurable board
│   │   │   ├── engine.py        # authoritative game engine (pure, deterministic w/ rng)
│   │   │   ├── events.py        # event card deck & effects
│   │   │   ├── economy.py       # transactions, milestones, bankruptcy
│   │   │   └── validation.py    # input validation helpers
│   │   ├── bots.py              # server-side AI managers (smart / random)
│   │   ├── rooms.py             # room registry, host/ready/start, bots, reconnection
│   │   ├── persistence.py       # SQLite snapshots + match history
│   │   ├── ws.py                # WebSocket connection manager & message router
│   │   └── main.py              # FastAPI REST + WebSocket endpoints
│   └── tests/
│       ├── conftest.py
│       ├── test_engine.py
│       ├── test_rooms.py
│       └── test_api.py
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    ├── index.html
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── types.ts
        ├── net/socket.ts        # WS client w/ auto-reconnect
        ├── store.tsx            # centralized game state (useReducer/context)
        ├── components/          # Board, Dice, PlayerPanel, ActionPanel, etc.
        ├── screens/             # Landing, Lobby, Game, Squad, Profile, Results
        └── styles/              # premium theme CSS
```

### Design decisions

- **Backend**: Python + FastAPI + WebSockets. SQLite is used for persistence so
  the game runs with zero external database setup; the persistence layer is
  isolated so PostgreSQL can replace it later.
- **Frontend**: React + TypeScript + Vite. Custom CSS design system (dark navy,
  cricket green, gold). No heavy UI framework needed.
- **Authority**: dice, movement, money, wickets, ownership, events, auctions and
  victory are ALL computed server-side. Clients only send intents (`roll`,
  `buy`, `bid`, `upgrade`, ...) which the server validates against turn/phase,
  identity and balances.
- **Determinism**: the engine accepts an injected `rng`, so tests are fully
  deterministic and reproducible.

## Game rules summary

- 32 spaces; corners at 0/8/16/24.
- 2–4 players, room code, ready status, host starts, reconnect by player token.
- Every player begins with a **Starter Batsman (3 wickets)** so elimination is
  meaningful from turn one.
- Landing on unowned property → buy / skip / auction.
- Landing on an opponent's **batsman** → visitor pays rent; owner earns money +
  runs (modified by stadiums, fielders, upgrades).
- Landing on an opponent's **bowler** → one of visitor's active batsmen loses a
  wicket (fair server-side random target, announced clearly); owner earns a
  reward. Special abilities use bounded probabilities.
- **Wicket keepers** can block wickets; **fielders** reduce opponent income;
  **stadiums** boost batsman income & give sponsorship money.
- Batsman reaching 0 wickets is OUT (no income, no runs). Player eliminated when
  all their batsmen are OUT or they go bankrupt. Last player standing wins.
- Runs milestones (50/100/...) give money bonuses; runs matter for standings.
- Event cards, challenges, auctions, trades, upgrades and selling are supported.
- Doubles grant an extra roll (max 3 consecutive).

## Feature status

### Phase 1 — Core Game — COMPLETE
- [x] Project setup (FastAPI backend + Vite/React frontend)
- [x] Centralized configuration file
- [x] 32-space configurable board
- [x] Player system (money, runs, wickets, assets, stats, avatars)
- [x] Rooms: create / join / ready / host / start / reconnect
- [x] Server-authoritative dice, movement, turn management, doubles
- [x] Basic properties + purchase / skip / auction
- [x] Batsmen with individual wickets, income and runs
- [x] Bowlers with wicket-taking attacks and rewards
- [x] Money transactions + history
- [x] Elimination and last-player-standing victory
- [x] SQLite persistence for rooms/snapshots/match history
- [x] Engine + API tests

### Phase 2 — Complete Cricket Mechanics — COMPLETE
- [x] Wicket keepers (block chance, event prevention)
- [x] Fielders (income/reward reduction)
- [x] Stadiums (income boosts, sponsorship)
- [x] Event card deck (positive + negative) and challenges
- [x] Special abilities (yorker, bouncer, swing, spin, hat-trick)
- [x] Upgrades with max levels
- [x] Run milestones & streaks

### Phase 3 — Economy & Strategy — COMPLETE
- [x] Timed auctions with validated bids
- [x] Two-party trades with accept/decline
- [x] Selling assets, bankruptcy handling
- [x] Squad inspection & leaderboards
- [x] Achievements / match statistics

### Phase 4 — Visual Polish — COMPLETE
- [x] Premium responsive UI (desktop + mobile)
- [x] Dice, movement, wicket, run, purchase, elimination, victory animations
- [x] Optional sound effects with mute + volume
- [x] Landing / Lobby / Game / Squad / Profile / Results screens

### Phase 5 — Testing — COMPLETE
- [x] Engine unit tests for all major mechanics
- [x] API / WebSocket integration tests
- [x] Balance configuration centralized

### Phase 6 — Bots & Test Endpoints — COMPLETE
- [x] Server-side AI managers (`smart` and `random` strategies)
- [x] Bots use the same validated engine actions as human clients
- [x] `POST /api/rooms/{code}/bots` adds bots to an existing lobby
- [x] `POST /api/test/match` creates + starts a bot match with a direct URL
- [x] Landing page "Play vs Bots" one-click match
- [x] BOT badges in lobby and standings

## Bot / test endpoints

Add bots to a lobby you already created, then start normally as host:

```bash
curl -X POST http://localhost:8000/api/rooms/YOURCODE/bots \
  -H 'Content-Type: application/json' \
  -d '{"count": 2, "strategy": "smart"}'
```

Create and start a match immediately against bots. The response `url` opens
straight into the game as the human manager:

```bash
curl -X POST http://localhost:8000/api/test/match \
  -H 'Content-Type: application/json' \
  -d '{"name": "Tester", "bots": 2, "strategy": "smart"}'
```

`FRONTEND_URL` optionally overrides the returned URL. If it is unset, the
backend uses the request's `Origin` header (or its own base URL in a
same-origin deployment), so local and online links work without extra config.
Strategies: `smart` (value-aware buys, bids, recruitment, upgrades and debt
recovery) or `random` (legal random decisions for stress testing).

## How to run

### Backend
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
API docs: http://localhost:8000/docs

### Frontend
```bash
cd frontend
npm install
npm run dev
```
Open http://localhost:5173. `frontend/.env.development.local` points the dev
server at `http://localhost:8000`; production builds leave `VITE_API_URL`
empty and use the same FastAPI origin for `/api` and `/ws`. Set
`VITE_API_URL`/`VITE_WS_URL` before building only for a split deployment.

### Tests
```bash
cd backend
pytest -q
```

## Browser validation (live smoke test)

A two-client room was driven end-to-end in a real browser:

- Host created room, guest joined and readied, host started the match.
- Both clients received live state over WebSockets; the game screen replaced the
  lobby automatically once the server reported `started: true`.
- Dice roll, movement, run scoring (sixer), purchase offer, **Buy player**,
  squad **Train**, profile, results, event feed, toasts and live commentary were
  all exercised against the running backend.
- AFK auto-roll, decision timeouts and timed auctions were observed working.
- No browser console errors were reported during the session.
- A `POST /api/test/match` room was opened via its direct URL; two smart bots
  rolled, scored runs, bought assets and appeared with BOT badges in the live
  standings.

Issues found and fixed during validation:

1. A started match did not switch the client from lobby/landing to the game
   screen — the reducer now enters `game` when a live state has `started`.
2. A session restored from `localStorage` never opened its WebSocket on a
   refresh; the socket effect now owns connect/cleanup correctly (including
   React StrictMode's development double-mount).
3. Squad screen showed base (level-0) stats and an incorrect affordability
   check for training. The backend now serializes effective level-scaled
   values (`effective_rent`, `effective_reward`, `effective_block`,
   `effective_cut`, `effective_boost`, `upgrade_cost`, `sale_value`) and the UI
   uses them.

Final verification after fixes:

- `python -m pytest -q` → **47 passed**, 1 dependency warning.
- `npm run build` → successful production build.

## Phase 7 — Major Gameplay Overhaul — COMPLETE

Backend mechanics, deterministic tests and the complete frontend UI are done.
Live bot matches, draft/customisation, roster actions and turn-limit victory
were validated in the browser against the running FastAPI server.

- [x] Cricketer catalog + custom batsman draft with uniqueness (backend)
- [x] Dedicated batsman roster, active switching, max five, retirement (backend)
- [x] New board tiles: 1/2/4/6 runs, No-ball, recruitment, tiered properties (backend)
- [x] Six-only level multiplier and fixed 1/2/4 scoring (backend)
- [x] No-ball counter, bonus, extra turn and wicket protection (backend)
- [x] Bowler fee + wicket, fielder fee, keeper fee + run penalty (backend)
- [x] Batsman upgrades to level 5 with explicit costs (backend)
- [x] Recruitment market with global uniqueness (backend)
- [x] Debt/bankruptcy recovery workflow and downgrading (backend)
- [x] Selectable last-standing / turn-limit victory (backend)
- [x] New UI panels, modals, animations and responsive styling
- [x] Deterministic engine + API tests for all new mechanics

Validation: `cd backend && python -m pytest -q` → **65 passed**, 1 dependency
warning (no sleeps or RNG-dependent assertions). `cd frontend && npm run build`
→ successful production build.

Phase 7 browser validation (live server):

- A two-smart-bot instant match was opened by direct URL. Both bots advanced
  automatically through dice, movement, run tiles, purchases and recruitment;
  the 32-tile board and Phase 7 tile labels rendered correctly.
- The human manager bought a property (coins deducted, asset added), opened the
  batsman upgrade modal (level 1 → 2, six reward 6 → 12, cost 200, coins shown),
  confirmed the upgrade and saw level/reward/money update immediately.
- Draft flow was driven through the UI: custom batsman name, country, jersey
  number, hairstyle and expression were applied; the lobby showed the custom
  identity as locked in; one smart bot was added with one API call; the host
  started the match over WebSocket and the game screen replaced the lobby.
- A one-round `turn_limit` match reached the victory screen with the ranking
  table, winner reason and New match / Full results actions.
- No browser console errors were observed in any Phase 7 screen.

Two live-loop regressions found during validation were fixed:

1. Older persisted snapshots had partial `stats`/`effects` dictionaries, so a
   single room throwing `KeyError` killed the shared timer loop and stalled every
   bot match. Restore now merges missing defaults; each room tick is isolated so
   one bad snapshot cannot stop the loop.
2. A restart briefly dropped rooms because snapshot restoration failed on the
   same partial dictionaries. The merge fix covers restore as well.

## Phase 8 — Social, leaderboard, polish and deployment — COMPLETE

- [x] Live all-player scoreboard (coins, runs, wickets, batsmen, properties,
      no-ball bonus) available from the game header and driven by server state
- [x] Persistent global leaderboard aggregated from completed matches; bots are
      excluded by default and can be included with `?include_bots=true`
- [x] Bounded coin gifting: 50–500 coins, one gift per round, 100-coin reserve,
      debt/elimination checks, atomic transfer and event/stats recording
- [x] Smarter bots: context-aware cash reserves, late-game run valuation,
      recruitment depth, payback-ranked upgrades, yield-aware debt recovery and
      value-based auction ceilings
- [x] Premium arcade styling: glass panels, gold/cyan/violet accents, coin
      chips, quick-amount buttons, podium rows and animated buttons
- [x] Same-origin production build: FastAPI serves `frontend/dist`, including
      SPA fallback; request-based quick-match URLs; graceful tick-loop shutdown
- [x] Render blueprint with one web process, managed PostgreSQL, build and
      health check
- [x] Deterministic tests for gifting, leaderboard aggregation, social API and
      smarter-bot decisions

Validation: `cd backend && python -m pytest -q` → **74 passed**, 1 dependency
warning. `cd frontend && npm run build` → successful production build.

All coins, gifts and leaderboard points are virtual game metrics only. There
are no deposits, withdrawals, wagering or real-money transactions.

## Deploy to Render

The root `render.yaml` defines a single web service plus a managed PostgreSQL
database. One web process is required because room state and WebSocket
connections live in that process. Do not enable multiple instances/workers.

1. Push this folder to a Git repository (Render Blueprints require Git; there
   is no local Git repository in this workspace yet).
2. In Render, choose **New → Blueprint** and select that repository.
3. Review the generated `crickopoly` web service and `crickopoly-db` database,
   then apply. Render builds the Vite app, installs Python dependencies and
   starts `uvicorn` on `$PORT`.
4. Open the web service URL. `/api/health` returns the health payload;
   `/api/docs` exposes the API; the root URL serves the React app.

How it works:

- `DATABASE_URL` is injected from the Render database. SQLite is used locally
  when that variable is absent; `DB_PATH` can override the SQLite location.
- The frontend build has no hard-coded backend URL, so browser calls stay on
  the same HTTPS host and WebSockets automatically use `wss://`.
- `FRONTEND_URL` and `CORS_ORIGINS` are deliberately empty in the blueprint.
  Set them only if the React app is hosted separately from the API.
- Match history and the global leaderboard are written to PostgreSQL, so they
  survive web-service restarts. Active rooms are restored from the same store.

Final publish still requires a Render account/repository connection or a
Render API token; the local configuration is complete.

## Known limitations / pending
- No external authentication (guest names + avatar selection only).
- Bots cannot be added after a match has started (they must be in the lobby).
- A free Render web service sleeps when idle; the first friend to connect after
  a quiet period may wait for a cold start.
- Browser smoke testing used a desktop viewport; automated mobile viewport
  checks are not part of the test suite (responsive CSS is implemented).
