"""Two-sided trades with explicit confirmation and transfer windows.

An offer names what each franchise gives and receives (player contracts,
stadiums, sponsors, tactical cards and FC). Nothing moves until the receiving
franchise accepts; the server then validates both sides again and applies the
swap atomically through the central economy/squad APIs.
"""

from __future__ import annotations

import time
import uuid
from copy import deepcopy
from typing import Any

from . import franchise_economy as economy
from . import squad
from .data52 import BOARD, PLAYERS_BY_ID, RULES

ASSET_KEYS = ("players", "stadiums", "sponsors", "cards")


def _bundle(raw: Any) -> dict:
    src = raw if isinstance(raw, dict) else {}
    out: dict[str, Any] = {key: [] for key in ASSET_KEYS}
    out["cash"] = 0
    for key in ASSET_KEYS:
        value = src.get(key, [])
        if isinstance(value, list):
            out[key] = list(dict.fromkeys(value))
    try:
        out["cash"] = int(src.get("cash", 0) or 0)
    except (TypeError, ValueError):
        raise ValueError("Trade cash must be a non-negative number")
    if out["cash"] < 0:
        raise ValueError("Trade cash cannot be negative")
    return out


def transfer_window_every(state) -> int:
    try:
        return max(0, int(state.settings.get("transfer_window_every", 3) or 0))
    except (TypeError, ValueError):
        return 3


def transfer_window_open(state) -> bool:
    if state.finished or state.phase in ("draft", "over", "setup"):
        return False
    every = transfer_window_every(state)
    if every <= 0:
        return True
    return state.round % every == 0


def transfer_window_info(state) -> dict:
    every = transfer_window_every(state)
    if every <= 0:
        return {"open": True, "every": 0, "next_round": state.round, "round": state.round}
    next_round = state.round
    while next_round % every != 0:
        next_round += 1
    return {"open": transfer_window_open(state), "every": every,
            "next_round": next_round, "round": state.round}


def _next_id(state) -> str:
    return f"trade-{len(state.trades) + 1:04d}-{uuid.uuid4().hex[:4]}"


def _validate(state, trade: dict) -> None:
    if not transfer_window_open(state):
        raise ValueError(f"Transfer window is closed (opens in round "
                         f"{transfer_window_info(state)['next_round']})")
    from_fid, to_fid = trade["from"], trade["to"]
    if from_fid == to_fid or from_fid not in state.franchises or to_fid not in state.franchises:
        raise ValueError("Trade needs two different, active franchises")
    give, want = trade["give"], trade["want"]
    if not any(give[key] or want[key] for key in ASSET_KEYS) and not (give["cash"] or want["cash"]):
        raise ValueError("A trade must include at least one asset or FC")
    for key in ASSET_KEYS:
        overlap = set(give[key]) & set(want[key])
        if overlap:
            raise ValueError(f"The same {key} cannot be on both sides of a trade")
    if give["cash"] > economy.balance(state, from_fid):
        raise ValueError("You cannot offer more FC than you hold")
    if want["cash"] > economy.balance(state, to_fid):
        raise ValueError("The other franchise cannot afford your requested FC")
    from_f, to_f = state.franchises[from_fid], state.franchises[to_fid]
    for ref in give["players"]:
        if ref not in from_f["squad"]:
            raise ValueError("You do not contract that player")
    for ref in want["players"]:
        if ref not in to_f["squad"]:
            raise ValueError("The other franchise does not contract that player")
    for ref in give["stadiums"]:
        if str(ref) not in from_f["stadiums"]:
            raise ValueError("You do not own that stadium")
    for ref in want["stadiums"]:
        if str(ref) not in to_f["stadiums"]:
            raise ValueError("The other franchise does not own that stadium")
    for key, owner in (("sponsors", from_f), ("cards", from_f)):
        for ref in give[key]:
            if ref not in owner[key]:
                raise ValueError(f"You do not hold that {key[:-1]}")
    for key, owner in (("sponsors", to_f), ("cards", to_f)):
        for ref in want[key]:
            if ref not in owner[key]:
                raise ValueError(f"The other franchise does not hold that {key[:-1]}")
    if len(from_f["squad"]) - len(give["players"]) + len(want["players"]) > RULES["squad_capacity"]:
        raise ValueError("Trade would overflow your 15-player squad")
    if len(to_f["squad"]) - len(want["players"]) + len(give["players"]) > RULES["squad_capacity"]:
        raise ValueError("Trade would overflow the other franchise's squad")


def create_offer(state, from_fid: str, to_fid: str, give: dict, want: dict,
                 message: str = "") -> dict:
    trade = {
        "id": _next_id(state), "from": from_fid, "to": to_fid,
        "give": _bundle(give), "want": _bundle(want),
        "message": str(message)[:180], "status": "pending",
        "created_at": time.time(), "round": state.round,
    }
    _validate(state, trade)
    state.trades[trade["id"]] = trade
    state.events.append({"type": "trade_offered", "payload": trade, "round": state.round})
    return trade


def accept_offer(state, trade_id: str, fid: str) -> dict:
    trade = state.trades.get(trade_id)
    if not trade or trade["status"] != "pending":
        raise ValueError("Trade offer is no longer pending")
    if fid != trade["to"]:
        raise ValueError("Only the receiving franchise can confirm this trade")
    _validate(state, trade)
    from_f = state.franchises[trade["from"]]
    to_f = state.franchises[trade["to"]]
    give, want = trade["give"], trade["want"]

    # Snapshot contracts/conditions before releasing any player.
    moves: list[tuple[str, str, dict, dict]] = []
    for pid in give["players"]:
        moves.append((to_f["id"], pid, deepcopy(from_f["squad"][pid]),
                      deepcopy(from_f["conditions"].get(pid, {}))))
    for pid in want["players"]:
        moves.append((from_f["id"], pid, deepcopy(to_f["squad"][pid]),
                      deepcopy(to_f["conditions"].get(pid, {}))))
    for fid_from, players in ((from_f["id"], give["players"]), (to_f["id"], want["players"])):
        for pid in players:
            squad.release_player(state, fid_from, pid)
    for new_fid, pid, contract, condition in moves:
        squad.add_to_squad(state, new_fid, pid, contract.get("price", 50))
        state.franchises[new_fid]["conditions"][pid] = condition

    for owner, receiver, positions in (
        (from_f, to_f, give["stadiums"]), (to_f, from_f, want["stadiums"])
    ):
        for pos in positions:
            key = str(pos)
            upgrades = owner["stadiums"].pop(key, [])
            receiver["stadiums"][key] = upgrades
            state.ownership[key] = receiver["id"]
    for owner, receiver, sponsors in (
        (from_f, to_f, give["sponsors"]), (to_f, from_f, want["sponsors"])
    ):
        for sid in sponsors:
            owner["sponsors"].remove(sid)
            receiver["sponsors"].append(sid)
    for owner, receiver, cards in (
        (from_f, to_f, give["cards"]), (to_f, from_f, want["cards"])
    ):
        for cid in cards:
            owner["cards"].remove(cid)
            receiver["cards"].append(cid)
    if give["cash"]:
        economy.transfer(state, from_f["id"], to_f["id"], give["cash"],
                         "trade", "Trade settlement")
    if want["cash"]:
        economy.transfer(state, to_f["id"], from_f["id"], want["cash"],
                         "trade", "Trade settlement")

    squad.auto_xi(state, from_f["id"])
    squad.auto_xi(state, to_f["id"])
    trade["status"] = "executed"
    trade["accepted_at"] = time.time()
    state.events.append({"type": "trade_completed", "payload": trade, "round": state.round})
    return trade


def reject_offer(state, trade_id: str, fid: str) -> dict:
    trade = state.trades.get(trade_id)
    if not trade or trade["status"] != "pending":
        raise ValueError("Trade offer is no longer pending")
    if fid != trade["to"]:
        raise ValueError("Only the receiving franchise can reject this trade")
    trade["status"] = "rejected"
    trade["resolved_at"] = time.time()
    return trade


def cancel_offer(state, trade_id: str, fid: str) -> dict:
    trade = state.trades.get(trade_id)
    if not trade or trade["status"] != "pending":
        raise ValueError("Trade offer is no longer pending")
    if fid != trade["from"]:
        raise ValueError("Only the offering franchise can withdraw this trade")
    trade["status"] = "cancelled"
    trade["resolved_at"] = time.time()
    return trade


def offers_for(state, fid: str | None = None) -> list[dict]:
    rows = list(state.trades.values())
    if fid:
        rows = [t for t in rows if fid in (t["from"], t["to"])]
    return sorted(rows, key=lambda t: t.get("created_at", 0), reverse=True)
