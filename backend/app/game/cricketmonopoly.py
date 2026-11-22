"""Pure rules engine for Cricket Monopoly (ruleset 6).

Roll two dice, move clockwise around the 52-square board, buy grounds and real
cricketer markets, upgrade them, charge rivals runs (and sometimes FC), and
protect your wickets. The manager with the most runs after the configured number
of laps wins.

No network, database or socket code lives here. Every decision that matters is
recorded in a plain, JSON-serialisable state dict so the API can persist it and
broadcast snapshots without mutating the authoritative game.
"""

from __future__ import annotations

import random
from copy import deepcopy
from typing import Any

from . import data52

RULES_VERSION = 6

DEFAULT_SETTINGS: dict[str, Any] = {
    "max_players": 6,
    "laps": 3,
    "difficulty": "medium",
}

# Economy constants published by the rules document.
STARTING_FC = 1500
STARTING_WICKETS = 3
MAX_WICKETS = 6
MAX_LEVEL = 4
AUCTION_PRICE = 180
LAP_FC = 100
LAP_RUNS = 100
UPGRADE_BASE_COST = 60
UPGRADE_STEP_COST = 40
HOME_GROUND_FC = 100
HOME_GROUND_RUNS = 50
HOME_GROUND_RENT_FACTOR = 3  # floor(due_fc * 3 / 2) when a ground is owned

STATE_KEYS = (
    "ruleset", "started", "finished", "phase", "turn", "laps", "order",
    "turn_index", "current_player_id", "dice", "rolled", "pending", "board",
    "properties", "franchises", "last_event", "settings", "data_overrides",
    "log", "events", "winner_id", "host_id",
)

FRANCHISE_KEYS = (
    "id", "name", "avatar", "color", "is_bot", "pos", "fc", "runs",
    "wickets", "max_wickets", "laps", "squad", "skipped", "injured",
    "owned", "out", "unlocked", "home_ground",
)

STANDING_KEYS = (
    "id", "name", "avatar", "color", "runs", "fc", "wickets", "laps", "rank",
)


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
    """Clamp the host-editable settings while preserving harmless extra keys."""
    settings = dict(DEFAULT_SETTINGS)
    settings.update(raw or {})
    settings["max_players"] = _clamp_int(
        settings.get("max_players"), 2, 6, DEFAULT_SETTINGS["max_players"])
    settings["laps"] = _clamp_int(
        settings.get("laps"), 2, 5, DEFAULT_SETTINGS["laps"])
    return settings


def _rng(state: dict, label: str) -> random.Random:
    """Room-local, reproducible randomness derived from the turn and order."""
    seed = "|".join([
        str(state.get("host_id", "GAME")),
        str(state.get("turn", 1)),
        ",".join(str(pid) for pid in state.get("order", [])),
        label,
    ])
    return random.Random(seed)


def _dice(state: dict) -> list[int]:
    """Roll two six-sided dice deterministically for the current turn."""
    rng = _rng(state, "dice")
    return [rng.randint(1, 6), rng.randint(1, 6)]


# Kept as a private alias so engine tests can pre-compute a landing square.
_roll_dice = _dice


def _franchise(state: dict, pid: str) -> dict:
    return (state.get("franchises") or {}).get(pid) or {}


def _name(franchise: dict, pid: str) -> str:
    return str(franchise.get("name", pid) or pid)


def _tile_at(state: dict, pos: int) -> dict:
    board = state.get("board") or []
    if not board:
        return {}
    return board[int(pos) % len(board)]


def _tile_label(state: dict, tile_id: str) -> str:
    tile = next((t for t in (state.get("board") or [])
                 if str(t.get("id")) == str(tile_id)), {})
    return str(tile.get("name", tile_id) or tile_id)


def _require_active(state: dict) -> None:
    if state.get("finished") or state.get("phase") == "over":
        raise ValueError("Cricket Monopoly is complete.")


def _require_member(state: dict, pid: str) -> None:
    if pid not in (state.get("franchises") or {}):
        raise ValueError("You are not in this game.")


def _require_turn(state: dict, pid: str) -> None:
    if state.get("current_player_id") != pid:
        raise ValueError("Wait for your turn.")


def _settle_out(state: dict, pid: str) -> None:
    franchise = _franchise(state, pid)
    if int(franchise.get("wickets", 0)) <= 0:
        franchise["wickets"] = 0
        franchise["out"] = True


def _active_ids(state: dict) -> list[str]:
    return [
        pid for pid in (state.get("order") or [])
        if not _franchise(state, pid).get("out")
    ]


def recompute_franchise(state: dict, pid: str) -> None:
    """Refresh ownership-derived fields after any property changes hands.

    A franchise is unlocked only with a batsman market, a bowler market, a
    wicketkeeper market and at least one stadium. Its home ground is the first
    stadium it bought, kept stable while that ground remains owned.
    """
    franchise = _franchise(state, pid)
    if not franchise:
        return
    properties = state.get("properties") or {}
    owned: list[str] = []
    for tile_id in list(franchise.get("owned") or []) + list(properties):
        tile_id = str(tile_id)
        if tile_id not in owned and (properties.get(tile_id) or {}).get("owner") == pid:
            owned.append(tile_id)

    meta = {str(tile.get("id")): tile for tile in (state.get("board") or [])}
    stadiums = [
        tile_id for tile_id in owned
        if (meta.get(tile_id) or {}).get("kind") == "stadium"
    ]
    roles = {
        str((meta.get(tile_id) or {}).get("role") or "")
        for tile_id in owned
        if (meta.get(tile_id) or {}).get("kind") == "market"
    }
    franchise["unlocked"] = (
        {"batsman", "bowler", "wicketkeeper"} <= roles and bool(stadiums)
    )
    current = franchise.get("home_ground")
    if current is None or str(current) not in stadiums:
        franchise["home_ground"] = stadiums[0] if stadiums else None
    else:
        franchise["home_ground"] = str(current)


def _owns_stadium(state: dict, pid: str) -> bool:
    """True while the manager still owns at least one stadium."""
    properties = state.get("properties") or {}
    return any(
        (properties.get(str(tile.get("id"))) or {}).get("owner") == pid
        for tile in (state.get("board") or [])
        if tile.get("kind") == "stadium"
    )


def _fc_rent_due(state: dict, owner_pid: str, due_fc: int) -> int:
    """Apply the +50% home-ground multiplier to FC rent (floored)."""
    due = max(0, int(due_fc))
    if _owns_stadium(state, owner_pid):
        return (due * HOME_GROUND_RENT_FACTOR) // 2
    return due


def _upgrade_missing(state: dict, pid: str) -> list[str]:
    """Human-readable list of missing franchise requirements."""
    franchise = _franchise(state, pid)
    properties = state.get("properties") or {}
    owned = [
        str(tile_id) for tile_id in (franchise.get("owned") or [])
        if (properties.get(str(tile_id)) or {}).get("owner") == pid
    ]
    meta = {str(tile.get("id")): tile for tile in (state.get("board") or [])}
    roles = {
        str((meta.get(tile_id) or {}).get("role") or "")
        for tile_id in owned
        if (meta.get(tile_id) or {}).get("kind") == "market"
    }
    missing: list[str] = []
    for role, label in (("batsman", "a batsman market"),
                        ("bowler", "a bowler market"),
                        ("wicketkeeper", "a wicketkeeper market")):
        if role not in roles:
            missing.append(label)
    if not any((meta.get(tile_id) or {}).get("kind") == "stadium" for tile_id in owned):
        missing.append("a ground")
    return missing


def _maybe_finish(state: dict) -> bool:
    """End the game on a completed lap or when one manager is left standing."""
    if state.get("finished"):
        return True
    lap_limit = int(state.get("laps", DEFAULT_SETTINGS["laps"]))
    lap_done = any(
        int(f.get("laps", 0)) >= lap_limit
        for f in (state.get("franchises") or {}).values()
    )
    if len(_active_ids(state)) > 1 and not lap_done:
        return False

    table = standings(state)
    winner = table[0] if table else None
    winner_id = winner["id"] if winner else None
    winner_name = winner["name"] if winner else "No manager"
    runs = winner["runs"] if winner else 0
    text = f"{winner_name} wins Cricket Monopoly with {runs} runs!"
    state["finished"] = True
    state["phase"] = "over"
    state["winner_id"] = winner_id
    state["last_event"] = {"type": "finish", "text": text}
    add_log(state, text, "final")
    return True


def _start_status(state: dict, pid: str) -> bool:
    """Consume a turn spent out, injured or skipped. Returns True if consumed."""
    franchise = _franchise(state, pid)
    if franchise.get("out") or int(franchise.get("wickets", 0)) <= 0:
        franchise["out"] = True
        advance_turn(state)
        return True
    if int(franchise.get("injured", 0)) > 0:
        franchise["injured"] = int(franchise["injured"]) - 1
        text = f"{_name(franchise, pid)} is injured and misses a turn ({franchise['injured']} left)."
        state["last_event"] = {"type": "injury", "text": text}
        add_log(state, text, "skip")
        advance_turn(state)
        return True
    if int(franchise.get("skipped", 0)) > 0:
        franchise["skipped"] = int(franchise["skipped"]) - 1
        text = f"{_name(franchise, pid)} was run out and misses a turn."
        state["last_event"] = {"type": "skip", "text": text}
        add_log(state, text, "skip")
        advance_turn(state)
        return True
    return False


# ---------------------------------------------------------------------------
# State construction and standings
# ---------------------------------------------------------------------------

def new_state(lobby: dict, overrides: dict | None = None) -> dict:
    """Create a fresh Cricket Monopoly game from a lobby payload."""
    settings = _settings(lobby.get("settings"))
    members = list((lobby.get("members") or {}).values())
    order = [str(member["id"]) for member in members if member.get("id")]
    host_id = str(lobby.get("host_id") or (order[0] if order else ""))

    board = deepcopy(data52.BOARD)
    properties: dict[str, dict] = {}
    for tile in board:
        if tile.get("kind") in ("market", "stadium"):
            properties[str(tile["id"])] = {
                "owner": None,
                "level": 0,
                "price": int(tile.get("price", 0)),
            }

    franchises: dict[str, dict] = {}
    for pid in order:
        member = next((m for m in members if str(m.get("id")) == pid), {})
        franchises[pid] = {
            "id": pid,
            "name": member.get("name", "Manager"),
            "avatar": member.get("avatar", "🏏"),
            "color": member.get("color", "#c8a24b"),
            "is_bot": bool(member.get("is_bot")),
            "pos": 0,
            "fc": STARTING_FC,
            "runs": 0,
            "wickets": STARTING_WICKETS,
            "max_wickets": STARTING_WICKETS,
            "laps": 0,
            "squad": [],
            "skipped": 0,
            "injured": 0,
            "owned": [],
            "out": False,
            "unlocked": False,
            "home_ground": None,
        }

    state: dict[str, Any] = {
        "ruleset": RULES_VERSION,
        "started": True,
        "finished": False,
        "phase": "play",
        "turn": 1,
        "laps": settings["laps"],
        "order": order,
        "turn_index": 0,
        "current_player_id": order[0] if order else None,
        "dice": None,
        "rolled": False,
        "pending": None,
        "board": board,
        "properties": properties,
        "franchises": franchises,
        "last_event": None,
        "settings": settings,
        "data_overrides": deepcopy(overrides or {}),
        "log": [],
        "events": [],
        "winner_id": None,
        "host_id": host_id,
    }
    add_log(state, f"Cricket Monopoly begins — {state['laps']} laps to the title.", "game")
    return state


def standings(state: dict) -> list[dict]:
    """League table ordered by runs, then FC."""
    rows: list[dict] = []
    for pid, franchise in (state.get("franchises") or {}).items():
        rows.append({
            "id": pid,
            "name": franchise.get("name", "Manager"),
            "avatar": franchise.get("avatar", "🏏"),
            "color": franchise.get("color", "#c8a24b"),
            "runs": int(franchise.get("runs", 0)),
            "fc": int(franchise.get("fc", 0)),
            "wickets": int(franchise.get("wickets", 0)),
            "laps": int(franchise.get("laps", 0)),
            "rank": 0,
        })
    rows.sort(key=lambda row: (-row["runs"], -row["fc"], str(row["name"])))
    for index, row in enumerate(rows, 1):
        row["rank"] = index
    return rows


# ---------------------------------------------------------------------------
# Turn flow and board effects
# ---------------------------------------------------------------------------

def advance_turn(state: dict) -> dict:
    """Clear turn-local data and hand the marker to the next active manager."""
    order = list(state.get("order") or [])
    state["dice"] = None
    state["rolled"] = False
    state["pending"] = None
    if not order:
        state["turn_index"] = 0
        state["current_player_id"] = None
        state["turn"] = int(state.get("turn", 0)) + 1
        return state

    count = len(order)
    start = int(state.get("turn_index", 0)) + 1
    chosen = None
    chosen_index = start % count
    for step in range(count):
        index = (start + step) % count
        candidate = order[index]
        if not _franchise(state, candidate).get("out"):
            chosen = candidate
            chosen_index = index
            break
    state["turn_index"] = chosen_index
    state["current_player_id"] = chosen if chosen is not None else order[start % count]
    state["turn"] = int(state.get("turn", 0)) + 1
    return state


def _batsman_price(state: dict, country: str | None) -> int:
    for tile in state.get("board") or []:
        if (tile.get("kind") == "market" and tile.get("country") == country
                and tile.get("role") == "batsman"):
            prop = (state.get("properties") or {}).get(str(tile["id"])) or {}
            return int(prop.get("price", tile.get("price", 0)) or 0)
    return 0


def _pay(visitor: dict, owner: dict, due_runs: int = 0, due_fc: int = 0) -> tuple[int, int, bool]:
    """Transfer dues, clamped to what the visitor actually holds."""
    due_runs = max(0, int(due_runs))
    due_fc = max(0, int(due_fc))
    paid_runs = min(due_runs, max(0, int(visitor.get("runs", 0))))
    paid_fc = min(due_fc, max(0, int(visitor.get("fc", 0))))
    visitor["runs"] = int(visitor.get("runs", 0)) - paid_runs
    visitor["fc"] = int(visitor.get("fc", 0)) - paid_fc
    owner["runs"] = int(owner.get("runs", 0)) + paid_runs
    owner["fc"] = int(owner.get("fc", 0)) + paid_fc
    short = paid_runs < due_runs or paid_fc < due_fc
    return paid_runs, paid_fc, short


def _resolve_charge(state: dict, owner_pid: str, visitor_pid: str, tile: dict) -> None:
    """Apply the rent/charge for a property owned by another manager."""
    owner = _franchise(state, owner_pid)
    visitor = _franchise(state, visitor_pid)
    prop = (state.get("properties") or {}).get(str(tile["id"])) or {}
    level = int(prop.get("level", 0))
    price = int(prop.get("price", tile.get("price", 0)) or 0)
    role = str(tile.get("role") or "")
    kind = str(tile.get("kind") or "")
    detail = ""
    short = False
    home_note = " (home ground bonus)" if _owns_stadium(state, owner_pid) else ""

    if role == "wicketkeeper":
        due = 40 + price // 5 + level * 10
        paid, _, short = _pay(visitor, owner, due_runs=due)
        visitor["skipped"] = 1
        detail = f"pays {paid} runs and will miss a turn"
    elif role == "batsman":
        due = max(15, 90 - level * 18)
        paid, _, short = _pay(visitor, owner, due_runs=due)
        detail = f"pays {paid} runs"
    elif role == "bowler":
        due_runs = 30 + level * 5
        due_fc = _fc_rent_due(state, owner_pid, 20 + level * 10)
        paid_runs, paid_fc, short = _pay(visitor, owner, due_runs, due_fc)
        detail = f"pays {paid_runs} runs and {paid_fc} FC"
        if home_note:
            detail += home_note
        if level >= MAX_LEVEL:
            bonus = _batsman_price(state, tile.get("country")) // 2
            owner["fc"] = int(owner.get("fc", 0)) + bonus
            visitor["wickets"] = int(visitor.get("wickets", 0)) - 1
            detail += f"; the elite bowler costs a wicket and {bonus} FC"
    elif role == "allrounder":
        total = sum(int(value) for value in (state.get("dice") or [0, 0]))
        paid_fc = _fc_rent_due(state, owner_pid, total * 8)
        paid_runs, paid_fc, short = _pay(visitor, owner, total * 2, paid_fc)
        detail = f"pays {paid_runs} runs and {paid_fc} FC on a dice total of {total}"
        if home_note:
            detail += home_note
    elif kind == "stadium":
        due = _fc_rent_due(state, owner_pid, price // 8 + level * 20)
        _, paid_fc, short = _pay(visitor, owner, due_fc=due)
        detail = f"pays {paid_fc} FC ground rent"
        if home_note:
            detail += home_note
    else:
        due = _fc_rent_due(state, owner_pid, 20)
        _, paid_fc, short = _pay(visitor, owner, due_fc=due)
        detail = f"pays {paid_fc} FC"
        if home_note:
            detail += home_note

    if short:
        visitor["wickets"] = int(visitor.get("wickets", 0)) - 1
        detail += "; short payment costs a wicket"
    _settle_out(state, visitor_pid)

    text = (f"{_name(visitor, visitor_pid)} landed on {tile.get('name', tile.get('id', 'a property'))} "
            f"owned by {_name(owner, owner_pid)} and {detail}.")
    state["last_event"] = {"type": role or kind or "charge", "text": text}
    add_log(state, text, "charge")


def _credit_lap(state: dict, pid: str) -> None:
    franchise = _franchise(state, pid)
    franchise["laps"] = int(franchise.get("laps", 0)) + 1
    franchise["fc"] = int(franchise.get("fc", 0)) + LAP_FC
    franchise["runs"] = int(franchise.get("runs", 0)) + LAP_RUNS
    text = (f"{_name(franchise, pid)} completed lap {franchise['laps']} — "
            f"+{LAP_FC} FC and +{LAP_RUNS} runs.")
    state["last_event"] = {"type": "lap", "text": text}
    add_log(state, text, "lap")


def _land_buyable(state: dict, pid: str, tile: dict) -> bool:
    """Resolve a market/stadium landing. Returns True if the turn is on hold."""
    franchise = _franchise(state, pid)
    prop = (state.get("properties") or {}).get(str(tile["id"])) or {}
    price = int(prop.get("price", 0))
    owner = prop.get("owner")
    label = str(tile.get("name", tile.get("id", "property")))

    if owner is None:
        if int(franchise.get("fc", 0)) < price:
            text = (f"{_name(franchise, pid)} cannot afford {label} "
                    f"({price} FC) and moves on.")
            state["last_event"] = {"type": "pass", "text": text}
            add_log(state, text, "pass")
            return False
        state["pending"] = {
            "type": "buy", "pid": pid, "tile_id": str(tile["id"]), "price": price,
        }
        text = f"{label} is available for {price} FC."
        state["last_event"] = {"type": "buy", "text": text}
        add_log(state, text, "offer")
        return True

    if owner == pid:
        if tile.get("kind") == "stadium":
            # Landing on your own ground is a bank bonus, never a rent charge.
            franchise["fc"] = int(franchise.get("fc", 0)) + HOME_GROUND_FC
            franchise["runs"] = int(franchise.get("runs", 0)) + HOME_GROUND_RUNS
            text = (f"{_name(franchise, pid)} landed on their own ground {label} — "
                    f"+{HOME_GROUND_FC} FC and +{HOME_GROUND_RUNS} runs from the bank.")
            state["last_event"] = {"type": "home_ground", "text": text}
            add_log(state, text, "bonus")
        else:
            text = f"{_name(franchise, pid)} owns {label} already."
            state["last_event"] = {"type": "own", "text": text}
            add_log(state, text, "info")
        return False

    _resolve_charge(state, owner, pid, tile)
    return False


def _event(state: dict, pid: str, tile: dict) -> bool:
    """Apply a deterministic special-tile effect. Returns True for an auction."""
    franchise = _franchise(state, pid)
    tile_id = str(tile.get("id") or "")
    label = str(tile.get("name", tile_id))

    if "auction" in tile_id.lower():
        state["pending"] = {"type": "auction", "pid": pid, "price": AUCTION_PRICE}
        text = f"{_name(franchise, pid)} reached {label} — a player auction for {AUCTION_PRICE} FC."
        state["last_event"] = {"type": "auction", "text": text}
        add_log(state, text, "auction")
        return True

    if "injury_reserve" in tile_id.lower():
        franchise["injured"] = 2
        text = f"{_name(franchise, pid)} is sent to the injury reserve for two turns."
        state["last_event"] = {"type": "injury", "text": text}
        add_log(state, text, "injury")
        return False

    if "sponsorship" in tile_id.lower():
        franchise["fc"] = int(franchise.get("fc", 0)) + 100
        detail = "+100 FC"
    elif "championship" in tile_id.lower():
        franchise["runs"] = int(franchise.get("runs", 0)) + 50
        detail = "+50 runs"
    elif "training" in tile_id.lower():
        franchise["fc"] = int(franchise.get("fc", 0)) - 50
        detail = "-50 FC"
    elif "matchday" in tile_id.lower():
        franchise["runs"] = int(franchise.get("runs", 0)) + 40
        detail = "+40 runs"
    elif "strategy" in tile_id.lower() or "recovery" in tile_id.lower():
        franchise["runs"] = int(franchise.get("runs", 0)) + 30
        detail = "+30 runs"
    else:
        franchise["fc"] = int(franchise.get("fc", 0)) + 20
        detail = "+20 FC"

    text = f"{_name(franchise, pid)} visited {label}: {detail}."
    state["last_event"] = {"type": "event", "text": text}
    add_log(state, text, "event")
    return False


# ---------------------------------------------------------------------------
# Public actions
# ---------------------------------------------------------------------------

def roll(state: dict, pid: str) -> str:
    """Roll the dice, move, and resolve the landing square."""
    _require_active(state)
    _require_member(state, pid)
    _require_turn(state, pid)
    if state.get("pending"):
        raise ValueError("Resolve the pending decision first.")
    if _start_status(state, pid):
        return "ok"

    dice = _dice(state)
    total = sum(dice)
    state["dice"] = dice
    state["rolled"] = True
    franchise = _franchise(state, pid)
    old_pos = int(franchise.get("pos", 0))
    new_pos = (old_pos + total) % len(state.get("board") or data52.BOARD)

    roll_text = (f"{_name(franchise, pid)} rolled {dice[0]} + {dice[1]} = {total} "
                 f"and moved to square {new_pos}.")
    state["last_event"] = {"type": "roll", "text": roll_text}
    add_log(state, roll_text, "roll")

    holds_turn = False
    if old_pos > 0 and old_pos + total >= len(state.get("board") or data52.BOARD):
        franchise["pos"] = new_pos
        _credit_lap(state, pid)
        if _maybe_finish(state):
            return "ok"
    else:
        franchise["pos"] = new_pos
        tile = _tile_at(state, new_pos)
        if tile.get("kind") in ("market", "stadium"):
            holds_turn = _land_buyable(state, pid, tile)
        else:
            holds_turn = _event(state, pid, tile)

    if not holds_turn:
        if _maybe_finish(state):
            return "ok"
        advance_turn(state)
    return "ok"


def buy(state: dict, pid: str) -> str:
    """Buy the property currently on offer."""
    _require_active(state)
    _require_member(state, pid)
    _require_turn(state, pid)
    pending = state.get("pending") or {}
    if pending.get("type") != "buy" or pending.get("pid") != pid:
        raise ValueError("No property purchase is pending.")
    tile_id = str(pending["tile_id"])
    prop = (state.get("properties") or {}).get(tile_id)
    if not prop or prop.get("owner") is not None:
        raise ValueError("That property is no longer available.")
    price = int(pending.get("price", prop.get("price", 0)))
    franchise = _franchise(state, pid)
    if int(franchise.get("fc", 0)) < price:
        raise ValueError("Not enough FC to buy that property.")

    franchise["fc"] = int(franchise["fc"]) - price
    prop["owner"] = pid
    franchise.setdefault("owned", []).append(tile_id)
    recompute_franchise(state, pid)
    tile = next((t for t in state.get("board") or [] if str(t.get("id")) == tile_id), {})
    text = f"{_name(franchise, pid)} bought {tile.get('name', tile_id)} for {price} FC."
    state["pending"] = None
    state["last_event"] = {"type": "buy", "text": text}
    add_log(state, text, "buy")
    advance_turn(state)
    return "ok"


def decline(state: dict, pid: str) -> str:
    """Pass on the pending offer and pass the turn on."""
    _require_active(state)
    _require_member(state, pid)
    _require_turn(state, pid)
    pending = state.get("pending") or {}
    if not pending or pending.get("pid") != pid:
        raise ValueError("No decision is pending.")
    franchise = _franchise(state, pid)
    label = "player auction" if pending.get("type") == "auction" else "property"
    text = f"{_name(franchise, pid)} declined the {label}."
    state["pending"] = None
    state["last_event"] = {"type": "decline", "text": text}
    add_log(state, text, "pass")
    advance_turn(state)
    return "ok"


def propose_trade(
    state: dict, pid: str, target: str, give_tile: str, take_tile: str
) -> str:
    """Offer a one-for-one property swap; the turn marker stays with the proposer."""
    _require_active(state)
    _require_member(state, pid)
    _require_turn(state, pid)
    if state.get("pending"):
        raise ValueError("Resolve the pending decision first.")

    target = str(target or "")
    _require_member(state, target)
    if target == pid:
        raise ValueError("Choose another manager to trade with.")
    other = _franchise(state, target)
    if other.get("out") or int(other.get("wickets", 0)) <= 0:
        raise ValueError("That manager is all out and cannot trade.")

    give_tile = str(give_tile or "")
    take_tile = str(take_tile or "")
    if not give_tile or not take_tile or give_tile == take_tile:
        raise ValueError("Choose two different properties.")
    properties = state.get("properties") or {}
    give_prop = properties.get(give_tile)
    take_prop = properties.get(take_tile)
    if not give_prop or not take_prop:
        raise ValueError("Unknown property.")
    if give_prop.get("owner") != pid:
        raise ValueError("You do not own the property you are offering.")
    if take_prop.get("owner") != target:
        raise ValueError("The other manager does not own that property.")

    state["pending"] = {
        "type": "trade", "pid": pid, "target": target,
        "give_tile": give_tile, "take_tile": take_tile, "price": 0,
    }
    text = (f"{_name(_franchise(state, pid), pid)} offered {_tile_label(state, give_tile)} to "
            f"{_name(other, target)} for {_tile_label(state, take_tile)}.")
    state["last_event"] = {"type": "trade", "text": text}
    add_log(state, text, "offer")
    return "ok"


def accept_trade(state: dict, pid: str) -> str:
    """Accept a pending swap. The proposer keeps the turn and may still roll."""
    _require_active(state)
    _require_member(state, pid)
    pending = state.get("pending") or {}
    if pending.get("type") != "trade" or pending.get("target") != pid:
        raise ValueError("No trade offer is pending for you.")

    proposer = str(pending.get("pid") or "")
    give_tile = str(pending.get("give_tile") or "")
    take_tile = str(pending.get("take_tile") or "")
    properties = state.get("properties") or {}
    give_prop = properties.get(give_tile)
    take_prop = properties.get(take_tile)
    if (not give_prop or not take_prop or give_prop.get("owner") != proposer
            or take_prop.get("owner") != pid):
        raise ValueError("The trade is no longer available.")

    give_prop["owner"] = pid
    take_prop["owner"] = proposer
    proposer_franchise = _franchise(state, proposer)
    target_franchise = _franchise(state, pid)
    for tile_id, old_owner, new_owner in (
        (give_tile, proposer, pid), (take_tile, pid, proposer)
    ):
        old_list = (state.get("franchises") or {}).get(old_owner, {}).setdefault("owned", [])
        if tile_id in old_list:
            old_list.remove(tile_id)
        (state.get("franchises") or {}).get(new_owner, {}).setdefault("owned", []).append(tile_id)
    recompute_franchise(state, proposer)
    recompute_franchise(state, pid)

    state["pending"] = None
    text = (f"{_name(target_franchise, pid)} accepted the trade with "
            f"{_name(proposer_franchise, proposer)} — {_tile_label(state, give_tile)} and "
            f"{_tile_label(state, take_tile)} swapped owners.")
    state["last_event"] = {"type": "trade", "text": text}
    add_log(state, text, "trade")
    return "ok"


def decline_trade(state: dict, pid: str) -> str:
    """Decline a pending swap. The proposer keeps the turn."""
    _require_active(state)
    _require_member(state, pid)
    pending = state.get("pending") or {}
    if pending.get("type") != "trade" or pending.get("target") != pid:
        raise ValueError("No trade offer is pending for you.")
    proposer = str(pending.get("pid") or "")
    text = (f"{_name(_franchise(state, pid), pid)} declined the trade offer from "
            f"{_name(_franchise(state, proposer), proposer)}.")
    state["pending"] = None
    state["last_event"] = {"type": "trade_declined", "text": text}
    add_log(state, text, "pass")
    return "ok"


def auction_buy(state: dict, pid: str) -> str:
    """Sign one free real cricketer and gain an extra wicket."""
    _require_active(state)
    _require_member(state, pid)
    _require_turn(state, pid)
    pending = state.get("pending") or {}
    if pending.get("type") != "auction" or pending.get("pid") != pid:
        raise ValueError("No player auction is pending.")
    franchise = _franchise(state, pid)
    if int(franchise.get("fc", 0)) < AUCTION_PRICE:
        raise ValueError(f"Not enough FC for the player auction ({AUCTION_PRICE} FC).")

    claimed: set[str] = set()
    for other in (state.get("franchises") or {}).values():
        claimed.update(str(item) for item in (other.get("squad") or []))
    choice = next(
        (p for p in data52.merged_players(state.get("data_overrides"))
         if p.get("id") and str(p["id"]) not in claimed),
        None,
    )
    if choice is None:
        text = "No free cricketers remain — the auction is skipped."
        state["pending"] = None
        state["last_event"] = {"type": "auction", "text": text}
        add_log(state, text, "auction")
        advance_turn(state)
        return "ok"

    franchise["fc"] = int(franchise["fc"]) - AUCTION_PRICE
    franchise.setdefault("squad", []).append(str(choice["id"]))
    franchise["max_wickets"] = min(MAX_WICKETS, int(franchise.get("max_wickets", STARTING_WICKETS)) + 1)
    franchise["wickets"] = min(
        int(franchise["max_wickets"]), int(franchise.get("wickets", 0)) + 1)
    text = (f"{_name(franchise, pid)} signed {choice.get('name', choice['id'])} "
            f"for {AUCTION_PRICE} FC and gained a wicket "
            f"({franchise['wickets']}/{franchise['max_wickets']}).")
    state["pending"] = None
    state["last_event"] = {"type": "auction", "text": text}
    add_log(state, text, "auction")
    advance_turn(state)
    return "ok"


def auction_skip(state: dict, pid: str) -> str:
    """Decline the player auction and pass the turn on."""
    _require_active(state)
    _require_member(state, pid)
    _require_turn(state, pid)
    pending = state.get("pending") or {}
    if pending.get("type") != "auction" or pending.get("pid") != pid:
        raise ValueError("No player auction is pending.")
    franchise = _franchise(state, pid)
    text = f"{_name(franchise, pid)} skipped the player auction."
    state["pending"] = None
    state["last_event"] = {"type": "auction", "text": text}
    add_log(state, text, "pass")
    advance_turn(state)
    return "ok"


def upgrade(state: dict, pid: str, tile_id: str) -> str:
    """Upgrade one owned property. Does not end the turn or consume the roll."""
    _require_active(state)
    _require_member(state, pid)
    _require_turn(state, pid)
    recompute_franchise(state, pid)
    franchise = _franchise(state, pid)
    if not franchise.get("unlocked"):
        missing = _upgrade_missing(state, pid)
        text = (f"{_name(franchise, pid)} cannot upgrade yet — still needs "
                f"{', '.join(missing)}.")
        state["last_event"] = {"type": "locked", "text": text}
        add_log(state, text, "lock")
        raise ValueError(
            "Upgrade locked: own a batsman market, a bowler market, "
            f"a wicketkeeper market and a ground first (missing: {', '.join(missing)})."
        )
    prop = (state.get("properties") or {}).get(str(tile_id))
    if not prop:
        raise ValueError("Unknown property.")
    if prop.get("owner") != pid:
        raise ValueError("You do not own that property.")
    level = int(prop.get("level", 0))
    if level >= MAX_LEVEL:
        raise ValueError("That property is already fully upgraded.")
    cost = UPGRADE_BASE_COST + level * UPGRADE_STEP_COST
    if int(franchise.get("fc", 0)) < cost:
        raise ValueError(f"Not enough FC to upgrade ({cost} FC).")

    franchise["fc"] = int(franchise["fc"]) - cost
    prop["level"] = level + 1
    tile = next((t for t in state.get("board") or []
                 if str(t.get("id")) == str(tile_id)), {})
    text = (f"{_name(franchise, pid)} upgraded {tile.get('name', tile_id)} "
            f"to level {prop['level']} for {cost} FC.")
    state["last_event"] = {"type": "upgrade", "text": text}
    add_log(state, text, "upgrade")
    return "ok"


def bot_action(state: dict, pid: str) -> None:
    """Take one deterministic decision for an automated manager."""
    if state.get("finished") or pid not in (state.get("franchises") or {}):
        return

    pending = state.get("pending") or {}
    if pending.get("type") == "trade":
        # A trade offer is addressed to its target, not to the current player.
        if pending.get("target") != pid:
            return
        properties = state.get("properties") or {}
        give_price = int((properties.get(str(pending.get("give_tile"))) or {}).get("price", 0))
        take_price = int((properties.get(str(pending.get("take_tile"))) or {}).get("price", 0))
        if take_price >= give_price:
            accept_trade(state, pid)
        else:
            decline_trade(state, pid)
        return
    if pending:
        if pending.get("pid") != pid:
            return
        if pending.get("type") == "buy":
            prop = (state.get("properties") or {}).get(str(pending.get("tile_id"))) or {}
            price = int(pending.get("price", prop.get("price", 0)))
            if int(_franchise(state, pid).get("fc", 0)) >= price:
                buy(state, pid)
            else:
                decline(state, pid)
        elif pending.get("type") == "auction":
            if int(_franchise(state, pid).get("fc", 0)) >= AUCTION_PRICE:
                auction_buy(state, pid)
            else:
                auction_skip(state, pid)
        else:
            decline(state, pid)
        return

    if state.get("current_player_id") != pid:
        return
    if _start_status(state, pid):
        return
    if state.get("rolled") or state.get("finished"):
        return

    franchise = _franchise(state, pid)
    if franchise.get("unlocked") and _rng(state, "bot").random() < 0.25:
        candidates: list[str] = []
        for tile_id in franchise.get("owned") or []:
            prop = (state.get("properties") or {}).get(str(tile_id))
            if not prop or prop.get("owner") != pid:
                continue
            cost = UPGRADE_BASE_COST + int(prop.get("level", 0)) * UPGRADE_STEP_COST
            if int(prop.get("level", 0)) < MAX_LEVEL and int(franchise.get("fc", 0)) >= cost:
                candidates.append(str(tile_id))
        if candidates:
            upgrade(state, pid, candidates[0])

    if state.get("current_player_id") != pid or state.get("pending"):
        return
    roll(state, pid)
