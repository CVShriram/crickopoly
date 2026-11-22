"""Pure rules engine for Wicket Rush (ruleset 4).

A fast, Uno-style cricket card game built on the real 96-cricketer roster.
Every cricketer is a card: match the current role (or play an all-rounder, the
wild card), resolve that card's cricket action, and try to empty your hand
first. Runs and wickets are only a score strip; the winner is the manager who
gets rid of their cards first.

No network, database or socket code lives here. Every decision that matters
(which card, which run-out victim, when to draw) belongs to the player.
"""

from __future__ import annotations

import random
from copy import deepcopy
from typing import Any

from . import data52

RULES_VERSION = 4

DEFAULT_SETTINGS: dict[str, Any] = {
    "max_players": 6,
    "hand_size": 7,
}

WILD_ROLE = "allrounder"
BOWLER_ROLE = "bowler"

STATE_KEYS = (
    "ruleset", "started", "finished", "phase", "turn", "order", "turn_index",
    "direction", "current_player_id", "current_role", "forced_role", "deck",
    "discard", "last_card", "franchises", "pending", "last_event", "settings",
    "data_overrides", "log", "events", "winner_id", "host_id",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def add_log(state: dict, text: str, kind: str = "info") -> None:
    """Append one shared entry to both the public log and the socket events."""
    entry = {"text": text, "kind": kind, "turn": int(state.get("turn", 1))}
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
    settings["hand_size"] = _clamp_int(
        settings.get("hand_size"), 5, 12, DEFAULT_SETTINGS["hand_size"])
    return settings


def player_map(overrides: dict | None = None) -> dict[str, dict]:
    return {p["id"]: p for p in data52.merged_players(overrides)}


def _rng(state: dict, label: str) -> random.Random:
    """Stable room-local randomness: no outcome is re-rolled by a client."""
    seed = "|".join([
        str(state.get("host_id", "GAME")),
        str(state.get("turn", 1)),
        ",".join(str(pid) for pid in state.get("order", [])),
        label,
    ])
    return random.Random(seed)


def _reshuffle_discard(state: dict) -> bool:
    """Recycle the pile, leaving the current card on top of the discard."""
    discard = list(state.get("discard") or [])
    if not discard:
        return False
    current = (state.get("last_card") or {}).get("player_id") or discard[-1]
    pool = [card for card in discard if card != current]
    if not pool:
        return False
    _rng(state, "reshuffle").shuffle(pool)
    state["deck"] = list(state.get("deck") or []) + pool
    state["discard"] = [card for card in discard if card == current]
    add_log(state, f"Draw pile reshuffled — {len(pool)} cards back in play.", "deck")
    return True


def _draw_cards(state: dict, pid: str, count: int) -> list[str]:
    """Draw up to `count` cards, reshuffling the discard as the pile runs dry."""
    franchise = (state.get("franchises") or {}).get(pid)
    if not franchise:
        return []
    drawn: list[str] = []
    for _ in range(max(0, int(count))):
        if not state.get("deck") and not _reshuffle_discard(state):
            break
        if not state.get("deck"):
            break
        drawn.append(state["deck"].pop(0))
    franchise.setdefault("hand", []).extend(drawn)
    return drawn


def _player_data(state: dict, card_id: str) -> dict:
    return player_map(state.get("data_overrides")).get(card_id, {}) or {}


def _role_of(state: dict, card_id: str) -> str:
    return str(_player_data(state, card_id).get("role", ""))


def _is_legal(state: dict, pid: str, card_id: str) -> bool:
    """A card is legal if it matches the role, is wild, or opens the game."""
    franchise = (state.get("franchises") or {}).get(pid)
    if not franchise or card_id not in franchise.get("hand", []):
        return False
    role = _role_of(state, card_id)
    if state.get("forced_role"):
        return role in (BOWLER_ROLE, WILD_ROLE)
    current = state.get("current_role")
    if current is None:
        return True
    return role == current or role == WILD_ROLE


def _finish(state: dict, pid: str) -> None:
    franchise = (state.get("franchises") or {}).get(pid, {})
    text = f"{franchise.get('name', pid)} emptied their hand and wins Wicket Rush!"
    state["finished"] = True
    state["phase"] = "over"
    state["winner_id"] = pid
    state["last_event"] = {"type": "finish", "text": text}
    add_log(state, text, "final")


def _rivals_with_cards(state: dict, pid: str) -> list[str]:
    return [
        other for other in (state.get("order") or [])
        if other != pid and (state.get("franchises", {}).get(other) or {}).get("hand")
    ]


# ---------------------------------------------------------------------------
# State construction and standings
# ---------------------------------------------------------------------------

def new_state(lobby: dict, overrides: dict | None = None) -> dict:
    settings = _settings(lobby.get("settings"))
    members = list((lobby.get("members") or {}).values())
    order = [str(member["id"]) for member in members if member.get("id")]
    host_id = str(lobby.get("host_id") or (order[0] if order else ""))

    pool = [p["id"] for p in data52.merged_players(overrides)]
    _rng({"host_id": host_id, "turn": 1, "order": order}, "deal").shuffle(pool)
    size = settings["hand_size"]
    hands: dict[str, list[str]] = {}
    offset = 0
    for pid in order:
        hands[pid] = pool[offset:offset + size]
        offset += size

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
            "runs": 0,
            "wickets": 0,
            "drawn": 0,
        }

    state: dict[str, Any] = {
        "ruleset": RULES_VERSION,
        "started": True,
        "finished": False,
        "phase": "play",
        "turn": 1,
        "order": order,
        "turn_index": 0,
        "direction": 1,
        "current_player_id": order[0] if order else None,
        "current_role": None,
        "forced_role": None,
        "deck": pool[offset:],
        "discard": [],
        "last_card": None,
        "franchises": franchises,
        "pending": None,
        "last_event": None,
        "settings": settings,
        "data_overrides": deepcopy(overrides or {}),
        "log": [],
        "events": [],
        "winner_id": None,
        "host_id": host_id,
    }
    add_log(state, "Wicket Rush begins — match the role or play an all-rounder.", "game")
    return state


def standings(state: dict) -> list[dict]:
    rows: list[dict] = []
    for pid, franchise in (state.get("franchises") or {}).items():
        runs = int(franchise.get("runs", 0))
        wickets = int(franchise.get("wickets", 0))
        rows.append({
            "id": pid,
            "name": franchise.get("name", "Manager"),
            "avatar": franchise.get("avatar", "🏏"),
            "color": franchise.get("color", "#c8a24b"),
            "runs": runs,
            "wickets": wickets,
            "cards": len(franchise.get("hand", []) or []),
            "score": runs - wickets * 5,
            "rank": 0,
        })
    rows.sort(key=lambda row: (-row["score"], row["name"]))
    for index, row in enumerate(rows, 1):
        row["rank"] = index
    return rows


# ---------------------------------------------------------------------------
# Turn flow
# ---------------------------------------------------------------------------

def advance_turn(state: dict, steps: int = 1) -> dict:
    """Move the marker by `steps` places in the current direction."""
    order = list(state.get("order") or [])
    if not order:
        return state
    count = len(order)
    index = int(state.get("turn_index", 0)) + int(state.get("direction", 1)) * int(steps)
    state["turn_index"] = index % count
    state["current_player_id"] = order[state["turn_index"]]
    state["turn"] = int(state.get("turn", 0)) + 1
    return state


def _require_active(state: dict) -> None:
    if state.get("finished") or state.get("phase") == "over":
        raise ValueError("Wicket Rush is complete.")


def _resolve_target(state: dict, pid: str, target_id: str) -> None:
    """Apply the wicketkeeper's run-out: steal a card, then make them draw."""
    pending = state.get("pending") or {}
    if pending.get("type") != "target" or pending.get("pid") != pid:
        raise ValueError("Only the actor can resolve this run-out.")
    if target_id not in pending.get("candidates", []):
        raise ValueError("That rival is not a valid run-out target.")

    actor = state["franchises"][pid]
    victim = state["franchises"][target_id]
    if not victim.get("hand"):
        raise ValueError("That rival has no cards to steal.")

    ratings = player_map(state.get("data_overrides"))
    stolen = max(
        victim["hand"],
        key=lambda card: (int(ratings.get(card, {}).get("batting", 0)), card),
    )
    victim["hand"].remove(stolen)
    actor.setdefault("hand", []).append(stolen)
    drawn = _draw_cards(state, target_id, 1)
    stolen_name = ratings.get(stolen, {}).get("name", stolen)
    text = (f"{actor.get('name', pid)} ran out {victim.get('name', target_id)} "
            f"and stole {stolen_name}; they draw {len(drawn)} card(s).")
    state["pending"] = None
    state["last_event"] = {"type": "run_out", "text": text}
    add_log(state, text, "steal")


# ---------------------------------------------------------------------------
# Public actions
# ---------------------------------------------------------------------------

def play_card(state: dict, pid: str, player_id: str,
              target_id: str | None = None) -> str:
    """Play one cricketer from the current manager's hand."""
    _require_active(state)
    if pid not in (state.get("franchises") or {}):
        raise ValueError("You are not in this game.")
    if state.get("pending"):
        raise ValueError("Resolve the pending run-out first.")
    if state.get("current_player_id") != pid:
        raise ValueError("Wait for your turn.")

    franchise = state["franchises"][pid]
    if player_id not in franchise.get("hand", []):
        raise ValueError("That cricketer is not in your hand.")
    if not _is_legal(state, pid, player_id):
        if state.get("forced_role"):
            raise ValueError("That card does not match the current role — a bowler or all-rounder is required.")
        raise ValueError("That card does not match the current role.")

    card = _player_data(state, player_id)
    role = str(card.get("role", ""))
    name = card.get("name", player_id)
    keeper_targets = _rivals_with_cards(state, pid) if role == "wicketkeeper" else []
    if target_id is not None and role == "wicketkeeper" and target_id not in keeper_targets:
        raise ValueError("That rival is not a valid run-out target.")

    franchise["hand"].remove(player_id)
    state.setdefault("discard", []).append(player_id)
    state["last_card"] = {
        "player_id": player_id,
        "name": name,
        "role": role,
        "effect": role,
        "owner_id": pid,
    }
    # The wild card clears the required role; the same manager plays again and
    # their next card chooses the new role to match.
    if role == WILD_ROLE:
        state["current_role"] = None
    else:
        state["current_role"] = role
    state["forced_role"] = None
    text = f"{franchise.get('name', pid)} played {name} ({role})."
    add_log(state, text, "card")
    state["last_event"] = {"type": "play", "text": text}

    # Emptying your hand ends the game immediately — no effect, no advance.
    if not franchise.get("hand"):
        _finish(state, pid)
        return "ok"

    if role == "batsman":
        runs = 10 + int(card.get("batting", 50)) // 5
        franchise["runs"] = int(franchise.get("runs", 0)) + runs
        state["forced_role"] = BOWLER_ROLE
        effect_text = f"{name} adds {runs} runs — the next player must bowl."
        state["last_event"] = {"type": "batsman", "text": effect_text}
        add_log(state, effect_text, "runs")
        advance_turn(state)
    elif role == BOWLER_ROLE:
        order = list(state.get("order") or [])
        if order:
            victim_id = order[(int(state.get("turn_index", 0))
                               + int(state.get("direction", 1))) % len(order)]
            victim = state["franchises"][victim_id]
            victim["wickets"] = int(victim.get("wickets", 0)) + 1
            effect_text = (f"{name} bowls {victim.get('name', victim_id)} — "
                           f"+1 wicket, turn skipped.")
            state["last_event"] = {"type": "bowler", "text": effect_text}
            add_log(state, effect_text, "wicket")
        advance_turn(state, 2)
    elif role == "wicketkeeper":
        candidates = keeper_targets
        if not candidates:
            effect_text = f"{name} keeps wicket — no rival has a card to steal."
            add_log(state, effect_text, "keeper")
            state["last_event"] = {"type": "wicketkeeper", "text": effect_text}
            advance_turn(state)
        elif target_id is not None and target_id in candidates:
            _resolve_target(state, pid, target_id)
            advance_turn(state)
        else:
            state["pending"] = {
                "type": "target", "pid": pid, "effect": "run_out",
                "candidates": candidates,
            }
            effect_text = f"{name} calls a run-out — {franchise.get('name', pid)} must choose a rival."
            add_log(state, effect_text, "keeper")
            state["last_event"] = {"type": "target", "text": effect_text}
            # The actor still owns the turn until the target is chosen.
    elif role == WILD_ROLE:
        franchise["runs"] = int(franchise.get("runs", 0)) + 5
        state["direction"] = -1 if int(state.get("direction", 1)) == 1 else 1
        effect_text = (f"{name} is the wild all-rounder: +5 runs, direction "
                       f"reversed, role reset — play again.")
        add_log(state, effect_text, "wild")
        state["last_event"] = {"type": "allrounder", "text": effect_text}
        # Same manager plays again; the card itself prevents an endless loop.
    return "ok"


def draw(state: dict, pid: str) -> str:
    """Draw two cards, concede the forced bowler, and pass the turn on."""
    _require_active(state)
    if pid not in (state.get("franchises") or {}):
        raise ValueError("You are not in this game.")
    if state.get("pending"):
        raise ValueError("Resolve the pending run-out first.")
    if state.get("current_player_id") != pid:
        raise ValueError("Wait for your turn.")

    franchise = state["franchises"][pid]
    drawn = _draw_cards(state, pid, 2)
    franchise["drawn"] = int(franchise.get("drawn", 0)) + 1
    state["forced_role"] = None
    text = f"{franchise.get('name', pid)} draws {len(drawn)} card(s) and passes."
    add_log(state, text, "draw")
    state["last_event"] = {"type": "draw", "text": text}
    advance_turn(state)
    return "ok"


def choose_target(state: dict, pid: str, target_id: str) -> str:
    """Resolve a wicketkeeper's pending run-out against one rival."""
    _require_active(state)
    pending = state.get("pending") or {}
    if pending.get("type") != "target":
        raise ValueError("No run-out is pending.")
    if pending.get("pid") != pid:
        raise ValueError("Only the actor can choose the run-out target.")
    if target_id not in pending.get("candidates", []):
        raise ValueError("That rival is not a valid run-out target.")
    _resolve_target(state, pid, target_id)
    advance_turn(state)
    return "ok"


def bot_action(state: dict, pid: str) -> None:
    """One deterministic decision for an automated manager."""
    if state.get("finished"):
        return
    pending = state.get("pending") or {}
    if pending:
        if pending.get("type") == "target" and pending.get("pid") == pid:
            candidates = [c for c in pending.get("candidates", [])
                          if (state.get("franchises", {}).get(c) or {}).get("hand")]
            if candidates:
                victim = max(
                    candidates,
                    key=lambda c: (len(state["franchises"][c]["hand"]), c),
                )
                try:
                    choose_target(state, pid, victim)
                except ValueError:
                    pass
        return

    if pid not in (state.get("franchises") or {}) or state.get("current_player_id") != pid:
        return

    franchise = state["franchises"][pid]
    hand = list(franchise.get("hand") or [])
    legal = [card for card in hand if _is_legal(state, pid, card)]
    if not legal:
        draw(state, pid)
        return

    def role_of(card: str) -> str:
        return _role_of(state, card)

    wilds = [card for card in legal if role_of(card) == WILD_ROLE]
    if wilds:
        card = wilds[0]
    elif state.get("forced_role") == BOWLER_ROLE:
        bowlers = [card for card in legal if role_of(card) == BOWLER_ROLE]
        card = bowlers[0] if bowlers else legal[0]
    elif state.get("current_role") is None:
        # Opening the game (or following a wild): name a role we can sustain.
        # Wicketkeepers win ties, so they are still preferred when sensible.
        counts: dict[str, int] = {}
        for held in hand:
            held_role = role_of(held)
            if held_role != WILD_ROLE:
                counts[held_role] = counts.get(held_role, 0) + 1

        def rank(option: str) -> tuple[int, int]:
            held_role = role_of(option)
            return (counts.get(held_role, 0), int(held_role == "wicketkeeper"))

        card = max(legal, key=rank)
    else:
        keepers = [card for card in legal if role_of(card) == "wicketkeeper"]
        card = keepers[0] if keepers else legal[0]

    target_id: str | None = None
    if role_of(card) == "wicketkeeper":
        candidates = _rivals_with_cards(state, pid)
        if candidates:
            target_id = max(
                candidates,
                key=lambda c: (len(state["franchises"][c]["hand"]), c),
            )

    try:
        play_card(state, pid, card, target_id)
    except ValueError:
        if not state.get("pending") and state.get("current_player_id") == pid:
            draw(state, pid)
