"""Competitive auction engine: market, mega and transfer auctions.

Bidding is turn/timeout based and never freezes: passing, insufficient funds,
or an expiry always resolves the lot. AI bidders use the same public interface.
"""

from __future__ import annotations

import time
from typing import Any

from .data52 import PLAYERS_BY_ID, RULES
from .franchise_economy import balance, credit, debit
from .squad import add_to_squad, release_player

MIN_INCREMENT = 10
DEFAULT_DURATION = 28.0  # seconds per lot in real time; AI also bids on tick


def _next_id(state) -> str:
    return f"auc-{len(state.auctions) + 1:04d}"


def create_auction(state, kind: str, player_ids: list[str], initiator: str,
                   *, owner_fid: str | None = None,
                   base_price: int | None = None,
                   duration: float = DEFAULT_DURATION) -> dict:
    if kind not in ("market", "mega", "transfer"):
        raise ValueError("Unknown auction type")
    if not player_ids:
        raise ValueError("Auction needs at least one player")
    for pid in player_ids:
        if pid not in PLAYERS_BY_ID:
            raise ValueError("Unknown player in auction")
    if kind == "transfer":
        # Confirm no one else owns the player; release from seller first.
        for pid in player_ids:
            for fid, f in state.franchises.items():
                if pid in f["squad"] and fid != initiator:
                    release_player(state, fid, pid)
    on = base_price if base_price is not None else max(20, PLAYERS_BY_ID[player_ids[0]]["value"] // 2)
    auction = {
        "id": _next_id(state), "kind": kind, "initiator": initiator,
        "owner_fid": owner_fid,
        "players": list(player_ids), "index": 0,
        "base_price": on, "current_bid": 0, "highest_bidder": None,
        "bids": [], "passed": [],
        "participants": [fid for fid, f in state.franchises.items()
                         if len(f["squad"]) < RULES["squad_capacity"]],
        "status": "open", "created_at": time.time(),
        "expires_at": time.time() + duration,
        "history": [],
    }
    state.auctions[auction["id"]] = auction
    state.auction = auction
    state.pending = {"type": "auction", "auction_id": auction["id"],
                     "expires_at": auction["expires_at"]}
    return auction


def current_player(auction: dict) -> str | None:
    idx = auction["index"]
    return auction["players"][idx] if idx < len(auction["players"]) else None


def min_bid(auction: dict) -> int:
    return (auction["current_bid"] + MIN_INCREMENT) if auction["highest_bidder"] else auction["base_price"]


def place_bid(state, fid: str, amount: int, auction_id: str | None = None) -> dict:
    auction = state.auctions.get(auction_id or (state.auction or {}).get("id", ""))
    if not auction or auction["status"] != "open":
        raise ValueError("No open auction")
    if fid in auction["passed"]:
        raise ValueError("You have passed this auction")
    if auction["highest_bidder"] == fid:
        raise ValueError("You already hold the highest bid")
    minimum = min_bid(auction)
    if amount < minimum:
        raise ValueError(f"Bid must be at least {minimum} FC")
    if balance(state, fid) < amount:
        raise ValueError("Insufficient credits")
    if fid not in auction["participants"]:
        raise ValueError("Not a participant")
    current = current_player(auction)
    f = state.franchises.get(fid)
    if not f or len(f["squad"]) >= RULES["squad_capacity"]:
        raise ValueError("Squad is full")
    if current and current in f["squad"]:
        raise ValueError("Player already in your squad")
    auction["current_bid"] = amount
    auction["highest_bidder"] = fid
    auction["expires_at"] = max(auction["expires_at"], time.time() + 6)
    auction["bids"].append({"fid": fid, "amount": amount, "ts": time.time()})
    state.events.append({"type": "auction_bid", "payload": {
        "auction_id": auction["id"], "franchise_id": fid, "amount": amount,
        "player_id": current_player(auction),
    }, "round": state.round})
    return auction


def pass_auction(state, fid: str, auction_id: str | None = None) -> dict:
    auction = state.auctions.get(auction_id or (state.auction or {}).get("id", ""))
    if not auction or auction["status"] != "open":
        raise ValueError("No open auction")
    if fid not in auction["passed"]:
        auction["passed"].append(fid)
    remaining = [p for p in auction["participants"] if p not in auction["passed"]]
    if len(remaining) <= 1 and auction["highest_bidder"]:
        close_auction(state, auction["id"])
    return auction


def close_auction(state, auction_id: str) -> dict:
    auction = state.auctions.get(auction_id)
    if not auction or auction["status"] != "open":
        raise ValueError("Auction is not open")
    pid = current_player(auction)
    winner = auction["highest_bidder"]
    price = auction["current_bid"]
    if winner and pid:
        f = state.franchises.get(winner)
        if (not f or len(f["squad"]) >= RULES["squad_capacity"]
                or pid in f["squad"] or balance(state, winner) < price):
            # Never let a stale or ineligible bid freeze the auction loop.
            winner = None
    record = {
        "player_id": pid, "price": price, "winner": winner,
        "bids": list(auction["bids"]), "kind": auction["kind"],
    }
    if winner and pid:
        add_to_squad(state, winner, pid, price)
        debit(state, winner, price, "auction", f"Won {auction['kind']} auction for {PLAYERS_BY_ID[pid]['name']}")
        if auction.get("owner_fid") and auction["owner_fid"] != winner:
            scouting = max(5, price // 10)
            credit(state, auction["owner_fid"], scouting, "scouting",
                   f"Scouting fee from {auction['kind']} auction")
        auction["history"].append({**record, "result": "sold"})
        state.events.append({"type": "auction_won", "payload": {
            "player_id": pid, "franchise_id": winner, "price": price,
            "player_name": PLAYERS_BY_ID[pid]["name"], "kind": auction["kind"],
        }, "round": state.round})
    else:
        auction["history"].append({**record, "result": "unsold"})
        state.events.append({"type": "auction_unsold", "payload": {
            "player_id": pid, "kind": auction["kind"],
        }, "round": state.round})
    auction["index"] += 1
    if auction["index"] < len(auction["players"]):
        # Reset for the next lot, keeping history.
        auction["current_bid"] = 0
        auction["highest_bidder"] = None
        auction["bids"] = []
        auction["passed"] = []
        auction["base_price"] = max(20, PLAYERS_BY_ID[current_player(auction)]["value"] // 2)
        auction["expires_at"] = time.time() + DEFAULT_DURATION
        state.auction = auction
    else:
        auction["status"] = "closed"
        state.auction = None
        state.pending = None
    return auction


def tick_auctions(state) -> list[str]:
    """Close any expired lots. Returns closed auction ids."""
    closed: list[str] = []
    now = time.time()
    for aid, auction in list(state.auctions.items()):
        if auction["status"] == "open" and now >= auction["expires_at"]:
            close_auction(state, aid)
            closed.append(aid)
    return closed


def active_participants(state, auction: dict) -> list[str]:
    return [p for p in auction["participants"] if p not in auction["passed"]]
