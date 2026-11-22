"""Franchise AI with Easy / Medium / Hard difficulty.

Every decision is derived from game state: remaining budget, squad role needs,
player ratings/value, pitch and venue conditions, fatigue and opponent
strength. Hard AI additionally plans tactically per match phase.
"""

from __future__ import annotations

import random
from typing import Any

from . import auction, match as matchmod, squad
from . import franchise_economy as economy
from .data52 import (BOARD, PITCHES, PLAYERS_BY_ID, PLAYERS, RULES,
                     STADIUM_UPGRADES)

DIFFICULTIES = ("easy", "medium", "hard")


def _rng(state, fid: str, salt: str = "") -> random.Random:
    return random.Random(hash(fid) ^ state.round * 104729 ^ hash(salt))


def role_need(state, fid: str, role: str) -> int:
    f = state.franchises[fid]
    have = sum(1 for pid in f["squad"] if PLAYERS_BY_ID.get(pid, {}).get("role") == role)
    targets = {"batsman": 5, "bowler": 5, "wicketkeeper": 2, "allrounder": 3}
    return max(0, targets.get(role, 3) - have)


def player_desire(state, fid: str, pid: str, *, opponent: str | None = None) -> float:
    """0..100 desirability used by all AI bidding / drafting decisions."""
    p = PLAYERS_BY_ID.get(pid)
    if not p:
        return 0.0
    if any(pid in fr["squad"] for fr in state.franchises.values()):
        return 0.0
    f = state.franchises[fid]
    diff = f.get("difficulty", "medium")
    need = role_need(state, fid, p["role"])
    value_for_money = p["overall"] / max(20, p["value"])
    score = p["overall"] * 0.4 + need * 8 + value_for_money * 25
    score += (p.get("form", 50) - 50) * 0.15
    if p.get("country"):
        owned = [t for t in f["markets"] if BOARD[t].get("country") == p["country"]]
        if owned:
            score += len(owned) * 3  # scouting synergy from country markets
    cond_budget = economy.balance(state, fid)
    if p["value"] > cond_budget * 0.5:
        score -= 25
    if diff == "easy":
        score += _rng(state, fid, pid).uniform(-22, 12)
    elif diff == "medium":
        score += _rng(state, fid, pid).uniform(-10, 8)
    else:  # hard
        score += _rng(state, fid, pid).uniform(-3, 4)
        if opponent:
            opp = state.franchises.get(opponent)
            if opp and p["id"] in opp["squad"]:
                score -= 12
    return max(0.0, min(100.0, score))


def ai_bid_limit(state, fid: str, pid: str) -> int:
    p = PLAYERS_BY_ID[pid]
    diff = state.franchises[fid].get("difficulty", "medium")
    budget = economy.balance(state, fid)
    # Deterministic difficulty separation: easy undervalues targets, hard
    # pays close to full value. desire is used only as a smaller tilt so the
    # difficulty ordering is stable at any budget.
    desire = player_desire(state, fid, pid)
    cap = budget * {"easy": 0.22, "medium": 0.38, "hard": 0.60}[diff]
    return max(0, min(cap, p["value"] * {"easy": 0.70, "medium": 0.90, "hard": 1.15}[diff]
                      * (0.85 + desire / 400)))


def ai_auction_action(state, fid: str, aid: str | None = None) -> dict:
    """Return a bid/pass decision for one AI participant in an open auction."""
    auc = state.auctions.get(aid or (state.auction or {}).get("id", ""))
    if not auc or auc["status"] != "open":
        return {"action": "none"}
    if auc["highest_bidder"] == fid or fid in auc["passed"]:
        return {"action": "none"}
    pid = auction.current_player(auc)
    if not pid:
        return {"action": "none"}
    f = state.franchises.get(fid)
    if not f or len(f["squad"]) >= RULES["squad_capacity"] or pid in f["squad"]:
        return {"action": "pass"}
    minimum = auction.min_bid(auc)
    limit = ai_bid_limit(state, fid, pid)
    if minimum > limit:
        return {"action": "pass"}
    desire = player_desire(state, fid, pid)
    diff = state.franchises[fid].get("difficulty", "medium")
    aggression = {"easy": 0.85, "medium": 0.95, "hard": 1.0}[diff]
    if desire < (28 if diff == "hard" else 20):
        return {"action": "pass"}
    amount = min(limit, max(minimum, int(minimum * (1 + desire / 200 * aggression))))
    return {"action": "bid", "amount": amount}


def ai_draft_pick(state, fid: str) -> str | None:
    available = [p["id"] for p in PLAYERS
                 if not any(p["id"] in fr["squad"] for fr in state.franchises.values())]
    if not available:
        return None
    f = state.franchises[fid]
    picked = len(f["squad"])
    # Early picks cover every role before stacking star players.
    if picked < 6:
        missing = [r for r in ("wicketkeeper", "bowler", "batsman", "allrounder")
                   if not any(PLAYERS_BY_ID.get(pid, {}).get("role") == r for pid in f["squad"])]
        if missing:
            role = missing[0]
            candidates = [pid for pid in available if PLAYERS_BY_ID[pid]["role"] == role]
            if candidates:
                return max(candidates, key=lambda pid: player_desire(state, fid, pid))
    return max(available, key=lambda pid: player_desire(state, fid, pid))


def ai_tile_action(state, fid: str, result: dict) -> dict:
    """AI decision after landing on a tile."""
    action = result.get("action")
    pos = result.get("to")
    if action == "buy_market":
        price = BOARD[pos]["price"]
        if economy.can_afford(state, fid, price):
            from .turn import buy_market
            return buy_market(state, fid, pos)
    if action == "buy_stadium":
        price = BOARD[pos]["price"]
        if economy.can_afford(state, fid, price):
            from .turn import buy_stadium
            return buy_stadium(state, fid, pos)
    return {"skipped": True}


def ai_upgrade(state, fid: str) -> dict | None:
    f = state.franchises[fid]
    if not f["stadiums"]:
        return None
    diff = f.get("difficulty", "medium")
    affordable = []
    for pos, installed in f["stadiums"].items():
        for up, spec in STADIUM_UPGRADES.items():
            if up not in installed and economy.can_afford(state, fid, spec["cost"]):
                affordable.append((spec["cost"], int(pos), up))
    if not affordable:
        return None
    if diff == "easy":
        choice = _rng(state, fid, "upgrade").choice(affordable)
    else:
        # Hard/medium prefer revenue and home-advancing upgrades first.
        priority = {"elite_stadium": 5, "pavilion": 4, "training_facilities": 3,
                    "pitch_development": 3, "sports_science": 2}
        affordable.sort(key=lambda x: (-priority.get(x[2], 1), x[0]))
        choice = affordable[0]
    if diff == "hard" and economy.balance(state, fid) - choice[0] < 250:
        return None  # hard AI keeps a financial reserve
    from .turn import upgrade_stadium
    return upgrade_stadium(state, fid, choice[1], choice[2])


def ai_tactics(state, fid: str, opponent: str, pitch: str) -> dict:
    """Choose phase-by-phase tactics using pitch, opponent strength and difficulty."""
    diff = state.franchises[fid].get("difficulty", "medium")
    pinfo = PITCHES.get(pitch, PITCHES["flat"])
    opp_strength = squad.squad_strength(state, opponent, pitch)
    my_strength = squad.squad_strength(state, fid, pitch)
    batting = "balanced"
    if my_strength > opp_strength + 8:
        batting = "aggressive" if diff == "hard" else "balanced"
    elif my_strength < opp_strength - 8:
        batting = "defensive" if diff != "easy" else "balanced"
    bowling = "defensive"
    if pinfo["pace"] > 1.08:
        bowling = "pace"
    elif pinfo["spin"] > 1.08:
        bowling = "spin"
    if diff == "hard":
        # Adapt to opponent's likely approach in the death overs.
        bowling = "yorkers"
    tactics: dict[str, dict] = {}
    for phase in ("powerplay", "middle", "death"):
        bat = batting
        bowl = bowling
        field = "balanced"
        if phase == "powerplay":
            bat = "aggressive" if batting != "defensive" else "balanced"
            field = "attacking" if diff == "hard" else "balanced"
        elif phase == "death":
            bat = "aggressive" if batting != "defensive" else "balanced"
            bowl = "yorkers" if diff != "easy" else bowling
            field = "defensive" if diff != "easy" else "balanced"
        tactics[phase] = {"bat": bat, "bowl": bowl, "field": field}
    return tactics


def should_play_match(state, fid: str) -> bool:
    """AI only accepts a match if it has a valid XI."""
    ok, _ = squad.validate_xi(state, fid)
    return ok
