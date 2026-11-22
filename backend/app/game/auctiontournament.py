"""Pure rules engine for Auction + Tournament (ruleset 7).

A room starts with a sealed-bid auction of real cricketers, followed by a short
round-robin tournament. There is no board, rent, dice or random match outcome:
scores come from the players' published BAT and BOWL ratings.

No network, database or socket code lives here. Every decision is recorded in a
plain JSON-serialisable state dict so the API can persist it and broadcast
snapshots without mutating the authoritative game.
"""

from __future__ import annotations

import random
from copy import deepcopy
from typing import Any

from . import data52

RULES_VERSION = 7

DEFAULT_SETTINGS: dict[str, Any] = {
    "max_players": 6,
    "budget": 1200,
    "lots": 18,
}

# Exact authoritative state contract. No other top-level keys are added.
STATE_KEYS = (
    "ruleset", "started", "finished", "phase", "turn", "order",
    "turn_index", "current_player_id", "lot_index", "lots", "budget",
    "current_lot", "bids", "last_result", "pending", "franchises",
    "fixtures", "match_index", "match_results", "settings",
    "data_overrides", "log", "events", "winner_id", "host_id",
    "last_event",
)

FRANCHISE_KEYS = (
    "id", "name", "avatar", "color", "is_bot", "fc", "squad",
    "captain", "tactic", "points", "total_score", "wins", "losses",
)

STANDING_KEYS = (
    "id", "name", "avatar", "color", "points", "total_score",
    "wins", "losses", "squad_size", "fc", "rank",
)

TACTICS: dict[str, dict[str, int]] = {
    "attack": {"runs": 25, "wickets": 0},
    "balanced": {"runs": 10, "wickets": -3},
    "defensive": {"runs": -5, "wickets": -8},
}

_LOT_SEED_LABEL = "auction-lots"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def add_log(state: dict, text: str, kind: str = "info") -> None:
    """Append one entry to both the public log and the socket event stream."""
    entry = {
        "text": str(text),
        "kind": kind,
        "turn": int(state.get("turn", 1) or 1),
    }
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
    """Clamp host-editable settings while preserving harmless extra keys."""
    settings = dict(DEFAULT_SETTINGS)
    settings.update(raw or {})
    settings["max_players"] = _clamp_int(
        settings.get("max_players"), 2, 6, DEFAULT_SETTINGS["max_players"])
    settings["budget"] = _clamp_int(
        settings.get("budget"), 600, 3000, DEFAULT_SETTINGS["budget"])
    settings["lots"] = _clamp_int(
        settings.get("lots"), 8, 30, DEFAULT_SETTINGS["lots"])
    return settings


def _lot_queue(host_id: Any, order: list[str], lots: int,
               overrides: dict | None) -> list[dict]:
    """Deterministically derive the lot queue from the room and player data.

    The queue is derived rather than stored: the authoritative state keeps only
    the exact top-level keys published by the ruleset while remaining stable for
    every read during a room's lifetime.
    """
    seed = "|".join([
        str(host_id),
        ",".join(str(pid) for pid in order),
        _LOT_SEED_LABEL,
    ])
    rng = random.Random(seed)
    players = data52.merged_players(overrides)
    rng.shuffle(players)
    return players[:max(0, int(lots))]


def _lot_queue_for(state: dict) -> list[dict]:
    return _lot_queue(
        state.get("host_id", "GAME"),
        list(state.get("order") or []),
        int(state.get("lots", DEFAULT_SETTINGS["lots"]) or DEFAULT_SETTINGS["lots"]),
        state.get("data_overrides"),
    )


def _lot_at(state: dict, index: int) -> dict | None:
    queue = _lot_queue_for(state)
    if 0 <= index < len(queue):
        return deepcopy(queue[index])
    return None


def _live_lot(state: dict) -> dict | None:
    """Return the active lot with the room's current host overrides applied."""
    lot = state.get("current_lot")
    if not isinstance(lot, dict) or not lot.get("id"):
        return None
    for candidate in _lot_queue_for(state):
        if str(candidate.get("id")) == str(lot["id"]):
            return deepcopy(candidate)
    return deepcopy(lot)


def _require_active(state: dict) -> None:
    if state.get("finished") or state.get("phase") == "over":
        raise ValueError("Auction + Tournament is complete.")


def _require_member(state: dict, pid: str) -> None:
    if pid not in (state.get("franchises") or {}):
        raise ValueError("You are not in this game.")
    if pid not in (state.get("order") or []):
        raise ValueError("You are not in this game.")


def _advance_marker(state: dict) -> None:
    """Rotate the turn marker and increment the turn counter."""
    order = list(state.get("order") or [])
    state["turn"] = int(state.get("turn", 0) or 0) + 1
    if not order:
        state["turn_index"] = 0
        state["current_player_id"] = None
        return
    index = (int(state.get("turn_index", 0) or 0) + 1) % len(order)
    state["turn_index"] = index
    state["current_player_id"] = order[index]


def _build_fixtures(order: list[str]) -> list[list[str]]:
    """Every manager plays every other manager once (all i < j pairs)."""
    return [[str(a), str(b)] for i, a in enumerate(order) for b in order[i + 1:]]


def _franchise_name(state: dict, pid: str) -> str:
    franchise = (state.get("franchises") or {}).get(pid) or {}
    return str(franchise.get("name", pid) or pid)


# ---------------------------------------------------------------------------
# State construction and standings
# ---------------------------------------------------------------------------

def new_state(lobby: dict, overrides: dict | None = None) -> dict:
    """Create a fresh Auction + Tournament game from a lobby payload."""
    settings = _settings(lobby.get("settings"))
    members = list((lobby.get("members") or {}).values())
    order = [str(member["id"]) for member in members if member.get("id")]
    host_id = str(lobby.get("host_id") or (order[0] if order else ""))

    franchises: dict[str, dict] = {}
    for pid in order:
        member = next((m for m in members if str(m.get("id")) == pid), {})
        franchises[pid] = {
            "id": pid,
            "name": member.get("name", "Manager"),
            "avatar": member.get("avatar", "🏏"),
            "color": member.get("color", "#c8a24b"),
            "is_bot": bool(member.get("is_bot")),
            "fc": int(settings["budget"]),
            "squad": [],
            "captain": None,
            "tactic": "balanced",
            "points": 0,
            "total_score": 0,
            "wins": 0,
            "losses": 0,
        }

    queue = _lot_queue(host_id, order, int(settings["lots"]), overrides)
    state: dict[str, Any] = {
        "ruleset": RULES_VERSION,
        "started": True,
        "finished": False,
        "phase": "auction",
        "turn": 1,
        "order": order,
        "turn_index": 0,
        "current_player_id": order[0] if order else None,
        "lot_index": 0,
        "lots": int(settings["lots"]),
        "budget": int(settings["budget"]),
        "current_lot": deepcopy(queue[0]) if queue else None,
        "bids": {pid: None for pid in order},
        "last_result": None,
        "pending": None,
        "franchises": franchises,
        "fixtures": [],
        "match_index": 0,
        "match_results": [],
        "settings": settings,
        "data_overrides": deepcopy(overrides or {}),
        "log": [],
        "events": [],
        "winner_id": None,
        "host_id": host_id,
        "last_event": None,
    }
    lot = state["current_lot"] or {}
    text = (f"Auction + Tournament begins — lot 1 of {state['lots']}: "
            f"{lot.get('name', lot.get('id', 'a cricketer'))}.")
    state["last_event"] = {"type": "game", "text": text}
    add_log(state, text, "game")
    return state


def standings(state: dict) -> list[dict]:
    """League table: points, then total score, then remaining FC."""
    rows: list[dict] = []
    for pid, franchise in (state.get("franchises") or {}).items():
        rows.append({
            "id": pid,
            "name": franchise.get("name", "Manager"),
            "avatar": franchise.get("avatar", "🏏"),
            "color": franchise.get("color", "#c8a24b"),
            "points": int(franchise.get("points", 0) or 0),
            "total_score": int(franchise.get("total_score", 0) or 0),
            "wins": int(franchise.get("wins", 0) or 0),
            "losses": int(franchise.get("losses", 0) or 0),
            "squad_size": len(franchise.get("squad") or []),
            "fc": int(franchise.get("fc", 0) or 0),
            "rank": 0,
        })
    rows.sort(key=lambda row: (-row["points"], -row["total_score"], -row["fc"]))
    for index, row in enumerate(rows, 1):
        row["rank"] = index
    return rows


# ---------------------------------------------------------------------------
# Auction
# ---------------------------------------------------------------------------

def bid(state: dict, pid: str, amount: Any) -> str:
    """Seal one bid (0 passes) for the current lot."""
    _require_active(state)
    _require_member(state, pid)
    if state.get("phase") != "auction":
        raise ValueError("Bidding is only allowed during the auction.")
    if (state.get("pending") or {}).get("type") == "next":
        raise ValueError("This lot has already been resolved.")
    lot = _live_lot(state)
    if not lot:
        raise ValueError("No cricketer is up for auction.")
    if state.get("bids", {}).get(pid) is not None:
        raise ValueError("You have already bid on this lot.")
    if not isinstance(amount, int) or isinstance(amount, bool):
        raise ValueError("Bid must be a whole number of FC.")
    amount = int(amount)
    franchise = (state.get("franchises") or {}).get(pid) or {}
    fc = int(franchise.get("fc", 0) or 0)
    if amount < 0 or amount > fc:
        raise ValueError(f"Bid must be between 0 and {fc} FC.")

    state["bids"][pid] = {
        "player_id": str(lot["id"]),
        "amount": amount,
    }
    # Never log the amount while bids are sealed: the event stream is public.
    state["last_event"] = {
        "type": "bid",
        "text": f"{_franchise_name(state, pid)} submitted a sealed bid.",
    }
    add_log(state, state["last_event"]["text"], "bid")

    order = list(state.get("order") or [])
    if order and all((state.get("bids") or {}).get(member) is not None
                     for member in order):
        resolve_lot(state)
    return "ok"


def resolve_lot(state: dict) -> str:
    """Resolve the current lot; ties go to the earlier manager in the rotation."""
    _require_active(state)
    if state.get("phase") != "auction":
        raise ValueError("There is no auction lot to resolve.")
    if (state.get("pending") or {}).get("type") == "next":
        raise ValueError("This lot has already been resolved.")
    lot = _live_lot(state)
    if not lot:
        raise ValueError("There is no auction lot to resolve.")

    player_id = str(lot["id"])
    name = str(lot.get("name", player_id) or player_id)
    order = list(state.get("order") or [])
    bids: dict[str, int] = {}
    for pid in order:
        entry = (state.get("bids") or {}).get(pid)
        amount = 0
        if isinstance(entry, dict) and str(entry.get("player_id")) == player_id:
            try:
                amount = max(0, int(entry.get("amount", 0) or 0))
            except (TypeError, ValueError):
                amount = 0
        bids[pid] = amount

    winner_id: str | None = None
    winning_amount = 0
    positive = [(index, pid, bids[pid]) for index, pid in enumerate(order)
                if bids.get(pid, 0) > 0]
    if positive:
        winning_amount = max(amount for _, _, amount in positive)
        winner_id = min((item for item in positive if item[2] == winning_amount),
                        key=lambda item: item[0])[1]

    if winner_id:
        winner = (state.get("franchises") or {}).get(winner_id) or {}
        winner["fc"] = int(winner.get("fc", 0) or 0) - winning_amount
        winner.setdefault("squad", []).append(player_id)
        text = (f"{name} sold to {_franchise_name(state, winner_id)} "
                f"for {winning_amount} FC.")
    else:
        text = f"{name} received no bids and remains unsigned."

    state["last_result"] = {
        "type": "lot",
        "player_id": player_id,
        "name": name,
        "winner_id": winner_id,
        "amount": winning_amount,
        "bids": bids,
    }
    state["pending"] = {"type": "next"}
    state["last_event"] = {"type": "lot_result", "text": text}
    add_log(state, text, "lot")
    return "ok"


# ---------------------------------------------------------------------------
# Tournament
# ---------------------------------------------------------------------------

def _side_score(state: dict, pid: str) -> tuple[int, int, int]:
    players = {str(player.get("id")): player
               for player in data52.merged_players(state.get("data_overrides"))}
    franchise = (state.get("franchises") or {}).get(pid) or {}
    squad = [str(item) for item in (franchise.get("squad") or [])]
    rated = [players.get(player_id) or {} for player_id in squad]

    batting = sorted((int(player.get("batting", 0) or 0) for player in rated),
                     reverse=True)[:6]
    bowling = sorted((int(player.get("bowling", 0) or 0) for player in rated),
                     reverse=True)[:3]
    tactic = TACTICS.get(franchise.get("tactic"), TACTICS["balanced"])

    runs = sum(batting) + int(tactic["runs"])
    wickets = int(sum(bowling) // 4) + int(tactic["wickets"])

    captain = franchise.get("captain")
    if captain is not None and str(captain) in squad:
        captain_data = players.get(str(captain)) or {}
        runs += 2 * int(captain_data.get("batting", 0) or 0)
        wickets += int(captain_data.get("bowling", 0) or 0) // 10

    score = runs - wickets * 4
    return runs, wickets, score


def _simulate_match(state: dict, a: str, b: str) -> dict:
    a_runs, a_wickets, a_score = _side_score(state, a)
    b_runs, b_wickets, b_score = _side_score(state, b)

    if a_score > b_score:
        winner_id: str | None = a
        loser_id: str | None = b
    elif b_score > a_score:
        winner_id = b
        loser_id = a
    else:
        winner_id = None
        loser_id = None

    for pid, score in ((a, a_score), (b, b_score)):
        franchise = (state.get("franchises") or {}).get(pid) or {}
        franchise["total_score"] = int(franchise.get("total_score", 0) or 0) + score
        if pid == winner_id:
            franchise["points"] = int(franchise.get("points", 0) or 0) + 2
            franchise["wins"] = int(franchise.get("wins", 0) or 0) + 1
        elif pid == loser_id:
            franchise["losses"] = int(franchise.get("losses", 0) or 0) + 1
        elif winner_id is None:
            franchise["points"] = int(franchise.get("points", 0) or 0) + 1

    return {
        "type": "match",
        "a": a,
        "b": b,
        "a_runs": a_runs,
        "a_wickets": a_wickets,
        "a_score": a_score,
        "b_runs": b_runs,
        "b_wickets": b_wickets,
        "b_score": b_score,
        "winner_id": winner_id,
    }


# ---------------------------------------------------------------------------
# Public actions
# ---------------------------------------------------------------------------

def next_step(state: dict, pid: str) -> str:
    """Advance one LOT / MATCH step. Never auto-advances more than one step."""
    _require_active(state)
    _require_member(state, pid)
    pending = state.get("pending")
    phase = state.get("phase")

    if phase == "auction":
        if (pending or {}).get("type") != "next":
            raise ValueError("Nothing is waiting for NEXT.")
        if int(state.get("lot_index", 0) or 0) + 1 < int(state.get("lots", 0) or 0):
            index = int(state.get("lot_index", 0) or 0) + 1
            state["lot_index"] = index
            state["current_lot"] = _lot_at(state, index)
            state["bids"] = {member: None for member in (state.get("order") or [])}
            state["last_result"] = None
            state["pending"] = None
            _advance_marker(state)
            lot = state["current_lot"] or {}
            text = (f"Lot {index + 1} of {state['lots']} — "
                    f"{lot.get('name', lot.get('id', 'a cricketer'))} is up for auction.")
            state["last_event"] = {"type": "lot", "text": text}
            add_log(state, text, "auction")
            return "ok"

        # Final lot: open the round-robin stage. The tournament's first fixture
        # starts on the next NEXT call (no stale auction pending survives).
        state["phase"] = "tournament"
        state["fixtures"] = _build_fixtures(list(state.get("order") or []))
        state["match_index"] = 0
        state["current_lot"] = None
        state["bids"] = {}
        state["last_result"] = None
        state["pending"] = None
        state["turn_index"] = 0
        state["current_player_id"] = (state.get("order") or [None])[0]
        text = (f"Auction complete — {len(state['fixtures'])} round-robin "
                f"fixtures await. Pick your captain and tactic.")
        state["last_event"] = {"type": "tournament", "text": text}
        add_log(state, text, "tournament")
        return "ok"

    if phase == "tournament":
        if pending and pending.get("type") != "next":
            raise ValueError("Resolve the pending decision first.")
        fixtures = list(state.get("fixtures") or [])
        index = int(state.get("match_index", 0) or 0)
        if index < len(fixtures):
            a, b = fixtures[index]
            result = _simulate_match(state, a, b)
            state["match_results"].append(result)
            state["last_result"] = result
            state["match_index"] = index + 1
            state["pending"] = {"type": "next"}
            state["turn"] = int(state.get("turn", 0) or 0) + 1
            state["turn_index"] = (list(state.get("order") or []).index(a)
                                   if a in (state.get("order") or []) else state.get("turn_index", 0))
            state["current_player_id"] = a
            a_name = _franchise_name(state, a)
            b_name = _franchise_name(state, b)
            if result["winner_id"]:
                winner_name = _franchise_name(state, result["winner_id"])
                text = (f"{a_name} {result['a_score']} – {result['b_score']} {b_name} — "
                        f"{winner_name} takes 2 points.")
            else:
                text = (f"{a_name} {result['a_score']} – {result['b_score']} {b_name} — "
                        f"a draw, 1 point each.")
            state["last_event"] = {"type": "match", "text": text}
            add_log(state, text, "match")
            return "ok"

        table = standings(state)
        winner_id = table[0]["id"] if table else None
        winner_name = table[0]["name"] if table else "No manager"
        state["finished"] = True
        state["phase"] = "over"
        state["winner_id"] = winner_id
        state["pending"] = None
        text = f"{winner_name} wins the Auction + Tournament cup!"
        state["last_event"] = {"type": "finish", "text": text}
        add_log(state, text, "final")
        return "ok"

    raise ValueError("This game is not in a playable phase.")


def set_captain(state: dict, pid: str, player_id: Any) -> str:
    """Choose (or clear) your captain; only one of your own squad members."""
    _require_active(state)
    _require_member(state, pid)
    if state.get("phase") not in ("auction", "tournament"):
        raise ValueError("Captains can only be set during a live game.")
    franchise = (state.get("franchises") or {}).get(pid) or {}
    squad = [str(item) for item in (franchise.get("squad") or [])]
    if player_id is None or not str(player_id).strip():
        franchise["captain"] = None
        label = "none"
    else:
        player_id = str(player_id)
        if player_id not in squad:
            raise ValueError("Choose a player from your own squad.")
        franchise["captain"] = player_id
        label = player_id
    text = f"{_franchise_name(state, pid)} set captain to {label}."
    state["last_event"] = {"type": "captain", "text": text}
    add_log(state, text, "setup")
    return "ok"


def set_tactic(state: dict, pid: str, tactic_id: Any) -> str:
    """Choose a scoring tactic from attack / balanced / defensive."""
    _require_active(state)
    _require_member(state, pid)
    if state.get("phase") not in ("auction", "tournament"):
        raise ValueError("Tactics can only be set during a live game.")
    tactic_id = str(tactic_id or "")
    if tactic_id not in TACTICS:
        raise ValueError("Unknown tactic.")
    franchise = (state.get("franchises") or {}).get(pid) or {}
    franchise["tactic"] = tactic_id
    text = f"{_franchise_name(state, pid)} adopted the {tactic_id} tactic."
    state["last_event"] = {"type": "tactic", "text": text}
    add_log(state, text, "setup")
    return "ok"


def bot_action(state: dict, pid: str) -> None:
    """Take one deterministic decision for an automated manager."""
    if state.get("finished") or pid not in (state.get("franchises") or {}):
        return
    phase = state.get("phase")

    if phase == "auction":
        if (state.get("pending") or {}).get("type") == "next":
            return
        lot = _live_lot(state)
        if not lot or (state.get("bids") or {}).get(pid) is not None:
            return
        try:
            batting = int(lot.get("batting", 0) or 0)
            bowling = int(lot.get("bowling", 0) or 0)
        except (TypeError, ValueError):
            batting = bowling = 0
        quality = 40 + (batting + bowling) // 4
        order = list(state.get("order") or [])
        position = order.index(pid) if pid in order else 0
        spread = ((position * 7) % 15) - 7
        amount = max(0, quality + spread)
        franchise = (state.get("franchises") or {}).get(pid) or {}
        fc = max(0, int(franchise.get("fc", 0) or 0))
        bid(state, pid, max(0, min(fc, amount)))
        return

    if phase == "tournament" and (state.get("pending") or {}).get("type") == "next":
        next_step(state, pid)
