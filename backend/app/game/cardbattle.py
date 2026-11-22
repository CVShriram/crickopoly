"""Pure rules engine for Cricket Card Battle (ruleset 3).

Each round every manager secretly commits one real cricketer card and one
reusable tactic. The card's batting rating adds runs to that manager's
innings; every opponent's bowling rating adds wickets to it. Pitch conditions
and the two tactics then adjust the innings before the highest score takes the
round. After a fixed number of rounds, round wins decide the champion and
total score breaks ties.

No network, database or socket code lives here.
"""

from __future__ import annotations

import random
from copy import deepcopy
from typing import Any

from . import data52

RULES_VERSION = 3

DEFAULT_SETTINGS: dict[str, Any] = {
    "max_players": 6,
    "rounds": 6,
    "difficulty": "medium",
}

PITCH_EFFECTS: dict[str, dict[str, Any]] = {
    "flat": {"runs": 10, "wickets": 0,
             "note": "True bounce — the batting card adds 10 runs."},
    "green": {"runs": 0, "wickets": 2,
              "note": "Seam movement — bowlers add 2 wickets."},
    "dry": {"runs": -10, "wickets": 1,
            "note": "Turn — spinners take 1 wicket and save 10 runs."},
    "slow": {"runs": 0, "wickets": 0,
             "note": "Low, slow carry — placement cards are rewarded."},
}

PITCH_KEYS = tuple(PITCH_EFFECTS)

# Exactly three reusable tactics. `pitch` names the surface on which the
# tactic's pitch_run / pitch_wicket bonus applies.
TACTICS: dict[str, dict[str, Any]] = {
    "attack": {
        "id": "attack", "name": "Attack", "icon": "⚡",
        "desc": "Flat-out batting: +25 runs, +1 wicket risk. Extra runs on a flat pitch.",
        "run_mod": 25, "wicket_mod": 1,
        "pitch": "flat", "pitch_run": 10, "pitch_wicket": 0,
    },
    "anchor": {
        "id": "anchor", "name": "Anchor", "icon": "⚓",
        "desc": "Steady accumulation: +10 runs, -1 wicket risk. Rewards a slow pitch.",
        "run_mod": 10, "wicket_mod": -1,
        "pitch": "slow", "pitch_run": 12, "pitch_wicket": 0,
    },
    "slog": {
        "id": "slog", "name": "Slog", "icon": "🚀",
        "desc": "Big swing: +34 runs, +3 wicket risk. Weak on a green pitch.",
        "run_mod": 34, "wicket_mod": 3,
        "pitch": "green", "pitch_run": -18, "pitch_wicket": 2,
    },
}

TACTIC_IDS = tuple(TACTICS)

STATE_KEYS = (
    "ruleset", "started", "finished", "phase", "round", "rounds", "order",
    "turn_index", "current_player_id", "pitch", "franchises", "plays",
    "revealed", "pending", "last_result", "settings", "data_overrides",
    "log", "events", "winner_id", "host_id",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def add_log(state: dict, text: str, kind: str = "info") -> None:
    """Append one shared entry to both the public log and the socket events."""
    entry = {"text": text, "kind": kind, "round": int(state.get("round", 1))}
    state.setdefault("log", []).append(entry)
    state.setdefault("events", []).append(deepcopy(entry))
    state["log"] = state["log"][-100:]
    state["events"] = state["events"][-50:]


def _clamp_int(value: Any, low: int, high: int, fallback: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return fallback


def _settings(raw: dict | None) -> dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)
    settings.update(raw or {})
    settings["max_players"] = _clamp_int(
        settings.get("max_players"), 2, 6, DEFAULT_SETTINGS["max_players"])
    settings["rounds"] = _clamp_int(
        settings.get("rounds"), 2, 12, DEFAULT_SETTINGS["rounds"])
    if not isinstance(settings.get("difficulty"), str) or not settings["difficulty"]:
        settings["difficulty"] = DEFAULT_SETTINGS["difficulty"]
    return settings


def player_map(overrides: dict | None = None) -> dict[str, dict]:
    return {p["id"]: p for p in data52.merged_players(overrides)}


def rng_for(state: dict, label: str = "") -> random.Random:
    """Stable per-round randomness without leaking state through the API."""
    seed = "|".join([
        str(state.get("host_id", "GAME")),
        str(state.get("round", 1)),
        ",".join(str(pid) for pid in state.get("order", [])),
        label,
    ])
    return random.Random(seed)


def _deal_hands(order: list[str], overrides: dict | None,
                host_id: str) -> dict[str, list[str]]:
    """Give every manager eight unique real cricketers from the room's data."""
    pool = list(player_map(overrides))
    rng = random.Random(f"deal|{host_id}|{','.join(order)}")
    rng.shuffle(pool)
    hands: dict[str, list[str]] = {}
    for index, pid in enumerate(order):
        hands[pid] = pool[index * 8:(index + 1) * 8]
        # A heavily edited room could theoretically run out of players.
        while len(hands[pid]) < 8 and pool:
            hands[pid].append(pool.pop())
    return hands


def _pitch_for(settings: dict) -> str:
    pitch = settings.get("pitch", "flat")
    return pitch if pitch in PITCH_EFFECTS else "flat"


def _next_pitch(pitch: str) -> str:
    if pitch not in PITCH_KEYS:
        return PITCH_KEYS[0]
    return PITCH_KEYS[(PITCH_KEYS.index(pitch) + 1) % len(PITCH_KEYS)]


def _replenish_hands(state: dict) -> None:
    """Keep a long match playable after the initial eight cards run out."""
    if not any(not f.get("hand") for f in state.get("franchises", {}).values()):
        return
    pool = list(player_map(state.get("data_overrides")))
    rng = rng_for(state, "replenish")
    rng.shuffle(pool)
    for franchise in state.get("franchises", {}).values():
        if not franchise.get("hand") and pool:
            franchise["hand"] = [pool.pop()]


# ---------------------------------------------------------------------------
# State construction and standings
# ---------------------------------------------------------------------------

def new_state(lobby: dict, overrides: dict | None = None) -> dict:
    settings = _settings(lobby.get("settings"))
    members = list((lobby.get("members") or {}).values())
    order = [str(member["id"]) for member in members if member.get("id")]
    host_id = str(lobby.get("host_id") or (order[0] if order else ""))
    hands = _deal_hands(order, overrides, host_id)

    franchises: dict[str, dict] = {}
    for pid in order:
        member = next((m for m in members if str(m.get("id")) == pid), {})
        franchises[pid] = {
            "id": pid,
            "name": member.get("name", "Manager"),
            "avatar": member.get("avatar", "🏏"),
            "color": member.get("color", "#c8a24b"),
            "is_bot": bool(member.get("is_bot")),
            "hand": list(hands.get(pid, [])),
            "points": 0,
            "total_score": 0,
            "played": 0,
        }

    state: dict[str, Any] = {
        "ruleset": RULES_VERSION,
        "started": True,
        "finished": False,
        "phase": "battle",
        "round": 1,
        "rounds": settings["rounds"],
        "order": order,
        "turn_index": 0,
        "current_player_id": order[0] if order else None,
        "pitch": _pitch_for(settings),
        "franchises": franchises,
        "plays": {},
        "revealed": False,
        "pending": None,
        "last_result": None,
        "settings": settings,
        "data_overrides": deepcopy(overrides or {}),
        "log": [],
        "events": [],
        "winner_id": None,
        "host_id": host_id,
    }
    add_log(state, "Battle begins. Pick one cricketer and one tactic.", "round")
    return state


def standings(state: dict) -> list[dict]:
    rows: list[dict] = []
    for pid, franchise in (state.get("franchises") or {}).items():
        rows.append({
            "pid": pid,
            "id": pid,
            "name": franchise.get("name", "Manager"),
            "avatar": franchise.get("avatar", "🏏"),
            "color": franchise.get("color", "#c8a24b"),
            "points": int(franchise.get("points", 0)),
            "total_score": int(franchise.get("total_score", 0)),
            "rank": 0,
        })
    rows.sort(key=lambda row: (-row["points"], -row["total_score"], row["name"]))
    for index, row in enumerate(rows, 1):
        row["rank"] = index
    return rows


# ---------------------------------------------------------------------------
# Round resolution
# ---------------------------------------------------------------------------

def _resolve_round(state: dict) -> dict:
    order = [pid for pid in state.get("order", []) if pid in state.get("plays", {})]
    pmap = player_map(state.get("data_overrides"))
    pitch = state.get("pitch", "flat")
    effect = PITCH_EFFECTS.get(pitch, PITCH_EFFECTS["flat"])

    ratings: dict[str, tuple[int, int]] = {}
    for pid in order:
        play = state["plays"][pid]
        player = pmap.get(play.get("player_id"), {}) or {}
        ratings[pid] = (int(player.get("batting", 50)), int(player.get("bowling", 50)))

    rows: list[dict] = []
    for pid in order:
        play = state["plays"][pid]
        tactic = TACTICS[play["tactic_id"]]
        bat, _ = ratings[pid]

        run_mod = int(tactic["run_mod"]) + int(effect["runs"])
        wicket_mod = int(tactic["wicket_mod"]) + int(effect["wickets"])
        if tactic["pitch"] == pitch:
            run_mod += int(tactic["pitch_run"])
            wicket_mod += int(tactic["pitch_wicket"])

        # Every rival's card is bowling at this innings.
        pressure = sum(ratings[other][1] // 20 for other in order if other != pid)
        runs = max(0, 100 + (bat * 3) // 5 + run_mod)
        wickets = max(0, min(10, 2 + pressure + wicket_mod))
        score = max(0, runs - wickets * 5)

        rows.append({
            "pid": pid,
            "name": state["franchises"][pid].get("name", "Manager"),
            "avatar": state["franchises"][pid].get("avatar", "🏏"),
            "color": state["franchises"][pid].get("color", "#c8a24b"),
            "runs": runs,
            "wickets": wickets,
            "score": score,
            "player_id": play["player_id"],
            "tactic_id": play["tactic_id"],
            "won": False,
        })

    best = max((row["score"] for row in rows), default=0)
    winner = next((row for row in rows if row["score"] == best), None)
    winner_id = winner["pid"] if winner else None
    for row in rows:
        row["won"] = row["pid"] == winner_id
        franchise = state["franchises"][row["pid"]]
        franchise["total_score"] = int(franchise.get("total_score", 0)) + row["score"]
    if winner_id:
        state["franchises"][winner_id]["points"] = int(
            state["franchises"][winner_id].get("points", 0)) + 1

    state["last_result"] = {
        "round": int(state.get("round", 1)),
        "pitch": pitch,
        "rows": rows,
        "winner_id": winner_id,
    }
    state["revealed"] = True
    state["pending"] = {"type": "result", "viewers": list(order)}
    if winner:
        add_log(state, f"Round {state['round']}: {winner['name']} wins on {pitch} pitch "
                       f"({winner['score']} pts).", "round")
    else:
        add_log(state, f"Round {state['round']} ends with no scores.", "round")
    return state["last_result"]


# ---------------------------------------------------------------------------
# Public actions
# ---------------------------------------------------------------------------

def play_card(state: dict, pid: str, player_id: str, tactic_id: str) -> str:
    """Commit the current manager's cricketer and tactic for this round."""
    if state.get("finished") or state.get("phase") == "over":
        raise ValueError("Battle is complete.")
    if pid not in (state.get("order") or []):
        raise ValueError("You are not in this battle.")
    if state.get("revealed") or state.get("pending"):
        raise ValueError("Round is already revealed.")
    if state.get("current_player_id") != pid:
        raise ValueError("Wait for your turn.")
    if pid in (state.get("plays") or {}):
        raise ValueError("You already played this round.")
    franchise = (state.get("franchises") or {}).get(pid)
    if not franchise or player_id not in franchise.get("hand", []):
        raise ValueError("That cricketer is not in your hand.")
    if tactic_id not in TACTICS:
        raise ValueError("Unknown tactic.")

    franchise["hand"].remove(player_id)
    state.setdefault("plays", {})[pid] = {
        "player_id": player_id,
        "tactic_id": tactic_id,
    }
    franchise["played"] = int(franchise.get("played", 0)) + 1
    add_log(state, f"{franchise.get('name', pid)} locked in a card.", "card")

    order = list(state.get("order") or [])
    pending_turn = next((index for index, member in enumerate(order)
                         if member not in state["plays"]), None)
    if pending_turn is None:
        state["turn_index"] = max(0, len(order) - 1)
        _resolve_round(state)
    else:
        state["turn_index"] = pending_turn
        state["current_player_id"] = order[pending_turn]
    return "ok"


def advance_turn(state: dict) -> dict:
    """Close the result, then start the next round or finish the battle."""
    state["plays"] = {}
    state["revealed"] = False
    state["pending"] = None

    if state.get("finished"):
        return state
    rounds = _clamp_int(
        state.get("settings", {}).get("rounds", state.get("rounds")),
        2, 12, DEFAULT_SETTINGS["rounds"])
    state["rounds"] = rounds

    if int(state.get("round", 1)) >= rounds:
        state["finished"] = True
        state["phase"] = "over"
        table = standings(state)
        state["winner_id"] = table[0]["pid"] if table else None
        if table:
            add_log(state, f"Battle complete — {table[0]['name']} takes the title.", "final")
        return state

    state["round"] = int(state.get("round", 1)) + 1
    state["pitch"] = _next_pitch(state.get("pitch", "flat"))
    order = list(state.get("order") or [])
    if order:
        order = order[1:] + order[:1]
        state["order"] = order
        state["turn_index"] = 0
        state["current_player_id"] = order[0]
    _replenish_hands(state)
    add_log(state, f"Round {state['round']} begins on a {state['pitch']} pitch.", "round")
    return state


def bot_action(state: dict, pid: str) -> None:
    """One decision for an automated manager. Safe to call on every tick."""
    if state.get("finished") or pid not in (state.get("franchises") or {}):
        return
    if state.get("pending"):
        if state["pending"].get("type") == "result":
            advance_turn(state)
        return
    if state.get("revealed") or state.get("current_player_id") != pid:
        return

    hand = state["franchises"][pid].get("hand") or []
    if not hand:
        _replenish_hands(state)
        hand = state["franchises"][pid].get("hand") or []
    if not hand:
        return

    rng = rng_for(state, f"bot|{pid}")
    card = rng.choice(hand)
    tactic = rng.choice(TACTIC_IDS)
    try:
        play_card(state, pid, card, tactic)
    except ValueError:
        return
