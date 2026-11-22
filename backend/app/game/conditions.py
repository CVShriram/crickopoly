"""Player condition engine: fatigue, form, confidence, fitness, injuries and
training. All progression is bounded so no attribute can grow without limit."""

from __future__ import annotations

import random

from .data52 import INJURIES, PLAYERS_BY_ID, TRAINING
from .franchise_economy import debit
from ..state import fresh_condition

MAX_ATTR = 98


def cond(state, fid: str, pid: str) -> dict:
    f = state.franchises[fid]
    if pid not in f["conditions"]:
        f["conditions"][pid] = fresh_condition(PLAYERS_BY_ID[pid])
    return f["conditions"][pid]


def apply_match_conditions(state, fid: str, runs: int, wickets: int,
                           won: bool, seed: int = 0) -> list[str]:
    """Update every selected player's condition after a match."""
    f = state.franchises[fid]
    rng = random.Random(seed)
    notes: list[str] = []
    for pid in f["xi"]:
        c = cond(state, fid, pid)
        c["matches_played"] += 1
        c["fatigue"] = min(100, c["fatigue"] + rng.randint(12, 20))
        contribution = runs / max(1, len(f["xi"]))
        if pid in f.get("pcm_id", []):
            contribution += 25
        delta = max(-8, min(10, int(contribution / 12) + (3 if won else -1)))
        c["form"] = max(10, min(98, c["form"] + delta))
        c["confidence"] = max(10, min(98, c["confidence"] + (4 if won else -2) + delta // 3))
        c["fitness"] = max(35, min(99, c["fitness"] - (2 if c["fatigue"] > 60 else 0)))
        if c["injury"]:
            c["injury"]["matches_left"] -= 1
            if c["injury"]["matches_left"] <= 0:
                c["injury"] = None
                notes.append(f"{PLAYERS_BY_ID[pid]['name']} recovered from injury")
    f["fatigue"] = min(100, sum(cond(state, fid, p)["fatigue"] for p in f["xi"]) // max(1, len(f["xi"])))
    return notes


def recover(state, fid: str, amount: int = 18) -> None:
    f = state.franchises[fid]
    for pid in f["squad"]:
        c = cond(state, fid, pid)
        c["fatigue"] = max(0, c["fatigue"] - amount)
        c["fitness"] = min(99, c["fitness"] + max(0, amount // 6))


def rest_player(state, fid: str, pid: str) -> None:
    c = cond(state, fid, pid)
    c["fatigue"] = max(0, c["fatigue"] - 30)
    c["fitness"] = min(99, c["fitness"] + 3)


def injure(state, fid: str, pid: str, severity: str = "minor",
           rng: random.Random | None = None) -> dict:
    if severity not in INJURIES:
        raise ValueError("Unknown injury severity")
    rng = rng or random.Random()
    kind = rng.choice(["Hamstring strain", "Ankle sprain", "Shoulder issue", "Back spasm", "Groin strain"])
    spec = INJURIES[severity]
    c = cond(state, fid, pid)
    c["injury"] = {
        "type": kind, "severity": severity,
        "matches_left": spec["matches"], "cost": spec["cost"],
        "icon": spec["icon"],
    }
    return c["injury"]


def rehabilitate(state, fid: str, pid: str) -> dict:
    c = cond(state, fid, pid)
    if not c["injury"]:
        raise ValueError("Player is not injured")
    cost = c["injury"]["cost"]
    debit(state, fid, cost, "rehabilitation",
          f"Rehabilitation for {PLAYERS_BY_ID[pid]['name']}")
    c["injury"] = None
    c["fitness"] = min(99, c["fitness"] + 6)
    c["fatigue"] = max(0, c["fatigue"] - 20)
    return c


def training_cost(state, fid: str, training_type: str) -> int:
    if training_type not in TRAINING:
        raise ValueError("Unknown training type")
    base = TRAINING[training_type]["cost"]
    stadiums = state.franchises[fid].get("stadiums", {})
    if any("training_facilities" in ups for ups in stadiums.values()):
        base = int(base * 0.75)
    return base


def train(state, fid: str, pid: str, training_type: str) -> dict:
    if training_type not in TRAINING:
        raise ValueError("Unknown training type")
    p = PLAYERS_BY_ID[pid]
    c = cond(state, fid, pid)
    if c["injury"]:
        raise ValueError("Injured player cannot train")
    cost = training_cost(state, fid, training_type)
    debit(state, fid, cost, "training", f"{TRAINING[training_type]['name']}: {p['name']}")
    spec = TRAINING[training_type]
    before = p.get(spec["attr"], p["overall"])
    gain = spec["gain"]
    if c["fatigue"] > 60:
        gain = max(1, gain - 2)
    cap = MAX_ATTR - p["overall"]
    gain = min(gain, max(1, cap // 2))
    current = p.get(spec["attr"], before) + gain
    # Static player data is shared, so store the trained value on the condition.
    c.setdefault("trained_attrs", {})[spec["attr"]] = min(MAX_ATTR, current)
    c["training"].append(training_type)
    c["fatigue"] = min(100, c["fatigue"] + 8)
    c["confidence"] = min(98, c["confidence"] + 2)
    return {"player_id": pid, "attr": spec["attr"], "before": before,
            "after": min(MAX_ATTR, current), "cost": cost}


def effective_attr(cond_data: dict | None, player: dict, attr: str) -> int:
    trained = (cond_data or {}).get("trained_attrs", {}).get(attr)
    return trained if trained is not None else player.get(attr, 50)
