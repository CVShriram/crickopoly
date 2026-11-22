"""Centralised franchise economy. Every credit movement goes through here so
there is exactly one place where balances and the transaction ledger change."""

from __future__ import annotations

import time
from typing import Any

from .data52 import RULES, STADIUM_UPGRADES


def balance(state, fid: str) -> int:
    f = state.franchises[fid]
    return int(f["balance"])


def can_afford(state, fid: str, amount: int) -> bool:
    return balance(state, fid) >= amount


def credit(state, fid: str, amount: int, kind: str, desc: str,
           *, event: str | None = None) -> dict:
    """Add credits and append an immutable ledger entry."""
    if amount <= 0:
        raise ValueError("Credit amount must be positive")
    f = state.franchises[fid]
    before = f["balance"]
    f["balance"] = before + amount
    txn = {
        "id": f"tx-{len(state.transactions) + 1:05d}",
        "round": state.round, "season": state.season,
        "franchise_id": fid, "kind": kind, "desc": desc,
        "amount": amount, "balance_after": f["balance"], "ts": time.time(),
    }
    state.transactions.append(txn)
    if event:
        state.events.append({"type": event, "payload": {
            "franchise_id": fid, "amount": amount, "desc": desc,
        }, "round": state.round})
    return txn


def debit(state, fid: str, amount: int, kind: str, desc: str,
          *, allow_debt: bool = False, event: str | None = None) -> dict:
    """Remove credits. Insufficient funds raise unless Classic-mode debt is allowed."""
    if amount <= 0:
        raise ValueError("Debit amount must be positive")
    f = state.franchises[fid]
    before = f["balance"]
    if before < amount and not allow_debt:
        raise ValueError(f"Insufficient credits: need {amount}, have {before}")
    f["balance"] = before - amount
    txn = {
        "id": f"tx-{len(state.transactions) + 1:05d}",
        "round": state.round, "season": state.season,
        "franchise_id": fid, "kind": kind, "desc": desc,
        "amount": -amount, "balance_after": f["balance"], "ts": time.time(),
        "debt": before < amount,
    }
    state.transactions.append(txn)
    if event:
        state.events.append({"type": event, "payload": {
            "franchise_id": fid, "amount": amount, "desc": desc,
        }, "round": state.round})
    return txn


def transfer(state, from_fid: str, to_fid: str, amount: int,
             kind: str, desc: str) -> tuple[dict, dict]:
    """Atomic two-sided transfer (used by trades, gifts and auctions)."""
    if from_fid == to_fid:
        raise ValueError("Cannot transfer to the same franchise")
    out = debit(state, from_fid, amount, kind, f"{desc} (sent)")
    inc = credit(state, to_fid, amount, kind, f"{desc} (received)")
    return out, inc


def franchise_valuation(state, fid: str) -> int:
    f = state.franchises[fid]
    total = int(f["balance"])
    # Contract value (current listed value, not purchase price).
    from .data52 import PLAYERS_BY_ID
    for pid in f["squad"]:
        p = PLAYERS_BY_ID.get(pid)
        if p:
            total += int(p["value"])
    for tile in f["markets"]:
        t = state_tile(tile)
        total += int(t.get("price", 0)) if t else 0
    for tile_key in f["stadiums"]:
        t = state_tile(int(tile_key))
        if t:
            total += int(t.get("price", 0))
            for up in f["stadiums"][tile_key]:
                total += int(STADIUM_UPGRADES.get(up, {}).get("cost", 0)) // 2
    return total


def state_tile(pos: int) -> dict | None:
    from .data52 import BOARD
    return BOARD[pos] if 0 <= pos < len(BOARD) else None


def settlement(state, fid: str, amount: int, reason: str) -> dict:
    """Classic-mode forced sale: raise credits by liquidating the cheapest
    non-core asset first. Returns the resulting ledger entry."""
    f = state.franchises[fid]
    options: list[tuple[int, str, Any]] = []
    for pid in list(f["squad"]):
        from .data52 import PLAYERS_BY_ID
        p = PLAYERS_BY_ID.get(pid)
        if p:
            options.append((int(p["value"]), "player", pid))
    for tile_key in list(f["stadiums"]):
        t = state_tile(int(tile_key))
        if t:
            options.append((int(t.get("price", 0)) // 2, "stadium", tile_key))
    options.sort(key=lambda x: x[0])
    raised = 0
    for value, kind, ref in options:
        if raised >= amount:
            break
        if kind == "player":
            release = f["squad"].pop(ref, None)
            f["conditions"].pop(ref, None)
            if ref in f["xi"]:
                f["xi"].remove(ref)
        else:
            f["stadiums"].pop(ref, None)
            if int(ref) in f["markets"]:
                f["markets"].remove(int(ref))
            state.ownership.pop(str(ref), None)
        raised += max(1, value)
    if raised:
        return credit(state, fid, raised, "liquidation", f"Asset sale: {reason}")
    return {"amount": 0, "desc": "No assets available"}
