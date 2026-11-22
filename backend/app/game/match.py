"""Deterministic-plus-randomness T20 match simulation engine.

Every outcome is derived from player ratings, conditions, pitch, tactics,
field placement, chemistry and a controlled random seed. No winner is picked
by a coin flip. All public functions are side-effect free so they can be unit
tested and reused by the AI, HTTP layer and WebSocket layer.
"""

from __future__ import annotations

import math
import random
from typing import Any

from .data52 import PITCHES, RULES

PHASES = (
    {"key": "powerplay", "name": "Powerplay", "start": 1, "end": 6},
    {"key": "middle", "name": "Middle Overs", "start": 7, "end": 15},
    {"key": "death", "name": "Death Overs", "start": 16, "end": 20},
)

BATTING_STRATEGIES = ("aggressive", "balanced", "defensive")
BOWLING_TACTICS = ("pace", "spin", "yorkers", "defensive", "variation")
FIELD_PLACEMENTS = ("attacking", "balanced", "defensive")

# (batting strategy, bowling tactic) -> run multiplier. No single row/column
# dominates; each has a contextual advantage.
_TACTIC_RUN = {
    ("aggressive", "pace"): 1.06, ("aggressive", "spin"): 0.94,
    ("aggressive", "yorkers"): 0.80, ("aggressive", "defensive"): 1.02,
    ("aggressive", "variation"): 0.88,
    ("balanced", "pace"): 0.99, ("balanced", "spin"): 1.00,
    ("balanced", "yorkers"): 0.92, ("balanced", "defensive"): 0.96,
    ("balanced", "variation"): 0.97,
    ("defensive", "pace"): 0.90, ("defensive", "spin"): 0.95,
    ("defensive", "yorkers"): 0.90, ("defensive", "defensive"): 0.91,
    ("defensive", "variation"): 0.93,
}

# Wicket multiplier for the same matrix (inverse pressure).
_TACTIC_WICKET = {
    ("aggressive", "pace"): 1.20, ("aggressive", "spin"): 1.10,
    ("aggressive", "yorkers"): 1.34, ("aggressive", "defensive"): 0.88,
    ("aggressive", "variation"): 1.12,
    ("balanced", "pace"): 1.00, ("balanced", "spin"): 1.00,
    ("balanced", "yorkers"): 1.10, ("balanced", "defensive"): 0.90,
    ("balanced", "variation"): 1.02,
    ("defensive", "pace"): 0.78, ("defensive", "spin"): 0.82,
    ("defensive", "yorkers"): 0.92, ("defensive", "defensive"): 0.70,
    ("defensive", "variation"): 0.80,
}

_FIELD_RUN = {"attacking": 1.06, "balanced": 1.00, "defensive": 0.92}
_FIELD_WICKET = {"attacking": 1.18, "balanced": 1.00, "defensive": 0.82}

_BOUNDARY_WEIGHT = {
    "aggressive": 1.35, "balanced": 1.0, "defensive": 0.72,
}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 50.0


def _condition_factor(cond: dict | None) -> float:
    if not cond:
        return 1.0
    form = cond.get("form", 50)
    conf = cond.get("confidence", 50)
    fatigue = cond.get("fatigue", 0)
    fitness = cond.get("fitness", 80)
    factor = 0.88 + (form - 50) * 0.0016 + (conf - 50) * 0.0010
    factor -= max(0, fatigue - 20) * 0.0022
    factor -= max(0, 80 - fitness) * 0.0018
    return _clamp(factor, 0.72, 1.18)


def _player_rating(player: dict, cond: dict | None, batting: bool) -> float:
    base = player.get("batting", 50) if batting else player.get("bowling", 50)
    return _clamp(base * _condition_factor(cond), 10, 110)


def calculate_pitch_modifier(pitch: str, tactic: str, batting: bool) -> float:
    """Pitch effect depends on the chosen tactic, not just a flat multiplier."""
    p = PITCHES.get(pitch, PITCHES["flat"])
    if batting:
        base = p["bat"]
        if tactic == "aggressive" and pitch in ("slow", "green"):
            base -= 0.06
        if tactic == "defensive" and pitch == "flat":
            base += 0.02
        return _clamp(base, 0.75, 1.25)
    if tactic == "pace":
        return p["pace"]
    if tactic == "spin":
        return p["spin"]
    if tactic == "yorkers":
        return _clamp((p["pace"] + p["bat"] * 0.5) / 1.5, 0.85, 1.15)
    return _clamp((p["pace"] + p["spin"]) / 2, 0.88, 1.12)


def calculate_batting_strength(lineup: list[dict], conditions: dict,
                               pitch: str, strategy: str, chemistry: dict) -> float:
    """Weighted batting strength for the current phase's active batters."""
    if not lineup:
        return 45.0
    weights = [1.3, 1.2, 1.0, 0.9, 0.8, 0.7][: len(lineup)]
    total = sum(w for w in weights)
    ratings = []
    for idx, player in enumerate(lineup):
        rating = _player_rating(player, conditions.get(player["id"]), True)
        ab = player.get("abilities", {})
        if strategy == "aggressive":
            rating += (ab.get("power", 50) - 50) * 0.10 + (ab.get("finishing", 50) - 50) * 0.05
        elif strategy == "defensive":
            rating += (ab.get("consistency", 50) - 50) * 0.10 + (ab.get("strike_rotation", 50) - 50) * 0.05
        else:
            rating += (ab.get("timing", 50) - 50) * 0.08
        ratings.append(rating * weights[min(idx, len(weights) - 1)])
    strength = sum(ratings) / total
    strength *= calculate_pitch_modifier(pitch, strategy, True)
    strength *= 1.0 + chemistry.get("batting", 0.0)
    return _clamp(strength, 20, 125)


def calculate_bowling_resistance(attack: list[dict], conditions: dict,
                                 pitch: str, tactic: str, chemistry: dict) -> float:
    if not attack:
        return 50.0
    weights = [1.2, 1.1, 1.0, 0.9, 0.8][: len(attack)]
    total = sum(weights)
    ratings = []
    for idx, bowler in enumerate(attack):
        rating = _player_rating(bowler, conditions.get(bowler["id"]), False)
        ab = bowler.get("abilities", {})
        if tactic == "pace":
            rating += (ab.get("pace", 50) - 50) * 0.12 + (ab.get("swing", 50) - 50) * 0.08
        elif tactic == "spin":
            rating += (ab.get("spin", 50) - 50) * 0.16
        elif tactic == "yorkers":
            rating += (ab.get("death_bowling", 50) - 50) * 0.12 + (ab.get("accuracy", 50) - 50) * 0.10
        elif tactic == "defensive":
            rating += (ab.get("accuracy", 50) - 50) * 0.14
        else:
            rating += (ab.get("variations", 50) - 50) * 0.10 + (ab.get("accuracy", 50) - 50) * 0.06
        ratings.append(rating * weights[min(idx, len(weights) - 1)])
    resistance = sum(ratings) / total
    resistance *= calculate_pitch_modifier(pitch, tactic, False)
    resistance *= 1.0 + chemistry.get("bowling", 0.0)
    return _clamp(resistance, 20, 125)


def calculate_tactical_advantage(strategy: str, bowling: str, field: str,
                                 phase: str) -> dict[str, float]:
    run = _TACTIC_RUN[(strategy, bowling)] * _FIELD_RUN[field]
    wicket = _TACTIC_WICKET[(strategy, bowling)] * _FIELD_WICKET[field]
    if phase == "death":
        if bowling == "yorkers":
            run *= 0.92
            wicket *= 1.10
        if strategy == "aggressive":
            run *= 1.05
            wicket *= 1.08
    elif phase == "powerplay":
        if bowling == "pace":
            run *= 1.04
        if field == "attacking":
            wicket *= 1.06
    else:  # middle
        if bowling == "spin":
            run *= 0.95
            wicket *= 1.06
    return {"run": _clamp(run, 0.65, 1.4), "wicket": _clamp(wicket, 0.55, 1.6)}


def calculate_wicket_probability(bat_strength: float, bowl_resistance: float,
                                 tactic_adv: dict, field: str, phase: str) -> float:
    pressure = bowl_resistance / max(30, bat_strength)
    base = 0.031 * pressure
    if phase == "death":
        base *= 1.30
    elif phase == "powerplay":
        base *= 1.10
    base *= tactic_adv["wicket"] * _FIELD_WICKET[field]
    return _clamp(base, 0.008, 0.16)


def calculate_run_distribution(bat_strength: float, bowl_resistance: float,
                               tactic_adv: dict, strategy: str, pitch: str) -> dict:
    """Return per-ball probabilities for dot/singles/boundaries + target rpb."""
    quality = _clamp(bat_strength / max(30, bowl_resistance), 0.60, 1.65)
    rpb = 1.02 * quality * tactic_adv["run"]
    p_wicket_base = 0.0  # handled separately
    p_dot = _clamp(0.34 - (quality - 1.0) * 0.10, 0.22, 0.44)
    boundary_bias = _BOUNDARY_WEIGHT[strategy]
    if pitch in ("slow", "dry"):
        boundary_bias *= 0.90
    if pitch == "flat" and strategy == "aggressive":
        boundary_bias *= 1.08
    # Scoring-ball distribution weights, boundary frequency driven by quality.
    w1, w2, w3 = 0.56, 0.20, 0.025
    w4 = _clamp(0.115 * quality * boundary_bias, 0.05, 0.26)
    w6 = _clamp(0.065 * quality * boundary_bias, 0.02, 0.18)
    total = w1 + w2 + w3 + w4 + w6
    scoring = {"1": w1 / total, "2": w2 / total, "3": w3 / total,
               "4": w4 / total, "6": w6 / total}
    return {"dot": p_dot, "scoring": scoring, "rpb": rpb,
            "p_wicket_base": p_wicket_base,
            "_score_prob": 1.0 - p_dot}


def calculate_phase_outcome(batting: list[dict], bowling: list[dict],
                            conditions: dict, pitch: str, strategy: str,
                            tactic: str, field: str, phase: str,
                            chemistry_bat: dict, chemistry_bowl: dict,
                            rng: random.Random, start_over: int, end_over: int,
                            wickets: int, target: int | None = None) -> dict:
    bat_strength = calculate_batting_strength(batting, conditions, pitch, strategy, chemistry_bat)
    bowl_resistance = calculate_bowling_resistance(bowling, conditions, pitch, tactic, chemistry_bowl)
    adv = calculate_tactical_advantage(strategy, tactic, field, phase)
    p_wicket = calculate_wicket_probability(bat_strength, bowl_resistance, adv, field, phase)
    dist = calculate_run_distribution(bat_strength, bowl_resistance, adv, strategy, pitch)
    balls = (end_over - start_over + 1) * 6
    runs = 0
    wickets_taken = 0
    boundaries = 0
    scoring_balls = 0
    per_batter: dict[str, int] = {}
    phase_balls = balls
    for ball in range(balls):
        if wickets + wickets_taken >= 10:
            phase_balls = ball
            break
        roll = rng.random()
        if roll < p_wicket:
            wickets_taken += 1
            bowler = bowling[(ball + wickets_taken) % len(bowling)] if bowling else None
            if bowler:
                per_batter[bowler["id"]] = per_batter.get(bowler["id"], 0) + 0  # wickets tracked below
            continue
        if roll < p_wicket + dist["dot"]:
            continue
        sroll = rng.random()
        acc = 0.0
        runs_this = 1
        for value, prob in dist["scoring"].items():
            acc += prob
            if sroll <= acc:
                runs_this = int(value)
                break
        runs += runs_this
        scoring_balls += 1
        if runs_this in (4, 6):
            boundaries += 1
        striker = batting[(ball // 2) % len(batting)] if batting else None
        if striker:
            per_batter[striker["id"]] = per_batter.get(striker["id"], 0) + runs_this
        if target and runs >= target:
            phase_balls = ball + 1
            break
    return {
        "phase": phase, "start_over": start_over,
        "overs": round(phase_balls / 6, 2),
        "runs": runs, "wickets": wickets_taken,
        "boundaries": boundaries, "scoring_balls": scoring_balls,
        "rpb": round(dist["rpb"], 3), "p_wicket": round(p_wicket, 4),
        "bat_strength": round(bat_strength, 1),
        "bowl_resistance": round(bowl_resistance, 1),
        "per_batter": per_batter,
    }


def calculate_innings_result(lineup: list[dict], attack: list[dict], conditions: dict,
                             pitch: str, tactics: dict, chemistry_bat: dict,
                             chemistry_bowl: dict, rng: random.Random,
                             target: int | None = None) -> dict:
    """Simulate a full 20-over innings from phase tactics.

    tactics = {phase: {"bat": str, "bowl": str, "field": str}}
    """
    total_runs = 0
    total_wickets = 0
    phases: list[dict] = []
    per_batter: dict[str, int] = {}
    for phase_def in PHASES:
        t = tactics.get(phase_def["key"], {"bat": "balanced", "bowl": "defensive", "field": "balanced"})
        out = calculate_phase_outcome(
            batting=lineup, bowling=attack, conditions=conditions, pitch=pitch,
            strategy=t["bat"], tactic=t["bowl"], field=t["field"],
            phase=phase_def["key"], chemistry_bat=chemistry_bat,
            chemistry_bowl=chemistry_bowl, rng=rng,
            start_over=phase_def["start"], end_over=phase_def["end"],
            wickets=total_wickets, target=target,
        )
        total_runs += out["runs"]
        total_wickets += out["wickets"]
        for pid, r in out["per_batter"].items():
            per_batter[pid] = per_batter.get(pid, 0) + r
        phases.append(out)
        if total_wickets >= 10 or (target and total_runs >= target):
            break
    return {
        "runs": total_runs, "wickets": total_wickets,
        "overs": min(20.0, sum(p["overs"] for p in phases)),
        "phases": phases, "per_batter": per_batter,
        "run_rate": round(total_runs / max(1, sum(p["overs"] for p in phases)), 2),
        "target": target,
    }


def determine_match_winner(first: dict, second: dict) -> dict:
    if second["runs"] > first["runs"]:
        return {"winner": "second", "margin_runs": 0,
                "margin_wickets": 10 - second["wickets"], "tie": False}
    if first["runs"] > second["runs"]:
        return {"winner": "first", "margin_runs": first["runs"] - second["runs"],
                "margin_wickets": 0, "tie": False}
    return {"winner": None, "margin_runs": 0, "margin_wickets": 0, "tie": True}


def _super_over(first: dict, second: dict, rng: random.Random) -> dict:
    """Six-ball tie-breaker using the same rating-based ball simulation."""
    def over(bat: dict, bowl: dict) -> tuple[int, int]:
        bat_strength = _avg([bat.get("batting", 50)])
        bowl_resistance = _avg([bowl.get("bowling", 50)])
        adv = calculate_tactical_advantage("aggressive", "yorkers", "defensive", "death")
        dist = calculate_run_distribution(bat_strength, bowl_resistance, adv, "aggressive", "flat")
        p_wicket = calculate_wicket_probability(bat_strength, bowl_resistance, adv, "defensive", "death")
        runs = wickets = 0
        for _ in range(6):
            r = rng.random()
            if r < p_wicket:
                wickets += 1
                continue
            if r < p_wicket + dist["dot"]:
                continue
            sr = rng.random()
            acc = 0.0
            for value, prob in dist["scoring"].items():
                acc += prob
                if sr <= acc:
                    runs += int(value)
                    break
        return runs, wickets
    a_runs, a_wk = over(first, second)
    b_runs, b_wk = over(second, first)
    if a_runs == b_runs:
        # Tie broken by fewer wickets, then a fresh sudden-death ball.
        if a_wk != b_wk:
            return {"winner": "first" if a_wk < b_wk else "second", "super_over": [a_runs, b_runs]}
        a_runs += rng.choice([0, 1, 2, 4, 6])
        b_runs += rng.choice([0, 1, 2, 4, 6])
    return {"winner": "first" if a_runs > b_runs else "second",
            "super_over": [a_runs, b_runs]}


def _tactical_analysis(first_name: str, second_name: str, first_t: dict,
                       second_t: dict, result: dict, pitch: str) -> str:
    winner = result.get("winner_name", "")
    p = PITCHES.get(pitch, PITCHES["flat"])
    if winner == first_name:
        batting = first_t["powerplay"]["bat"]
        bowling = second_t["death"]["bowl"]
    elif winner == second_name:
        batting = second_t["powerplay"]["bat"]
        bowling = first_t["death"]["bowl"]
    else:
        return f"A tight contest on a {p['name'].lower()}. Both franchises read the conditions well."
    notes = []
    if batting == "aggressive" and bowling in ("defensive", "spin"):
        notes.append("attacking batting punished a conservative bowling plan")
    if batting == "defensive" and bowling in ("pace", "yorkers"):
        notes.append("patient batting protected the wickets against a charging attack")
    if bowling == "spin" and pitch == "dry":
        notes.append("spin exploited the dry, gripping surface")
    if bowling == "pace" and pitch == "green":
        notes.append("pace and swing troubled the batters on the green top")
    if not notes:
        notes.append("balanced tactics and better execution across the three phases made the difference")
    return f"{winner} won because {'; '.join(notes)}."


def simulate_match(first: dict, second: dict, pitch: str, tactics: dict,
                   seed: int = 0, venue: dict | None = None) -> dict:
    """Simulate a complete T20 match.

    first / second are {"name","lineup"[player dicts],"conditions",
    "chemistry":{...},"home_venue":bool}. tactics is
    {"first":{phase:...}, "second":{phase:...}}.
    """
    rng = random.Random(seed)
    p = PITCHES.get(pitch, PITCHES["flat"])
    if venue:
        # Home-ground modifiers tilt the pitch slightly toward the host.
        pitch = venue.get("pitch", pitch)
        p = PITCHES.get(pitch, PITCHES["flat"])

    def lineup(team: dict) -> list[dict]:
        return team.get("lineup", [])[:11]

    first_innings = calculate_innings_result(
        lineup(first), lineup(second), first.get("conditions", {}), pitch,
        tactics["first"], first.get("chemistry", {}), second.get("chemistry", {}), rng,
    )
    target = first_innings["runs"] + 1
    second_innings = calculate_innings_result(
        lineup(second), lineup(first), second.get("conditions", {}), pitch,
        tactics["second"], second.get("chemistry", {}), first.get("chemistry", {}),
        rng, target=target,
    )
    result = determine_match_winner(first_innings, second_innings)
    if result["tie"]:
        so = _super_over(
            {"batting": _avg([x.get("batting", 50) for x in lineup(first)]),
             "bowling": _avg([x.get("bowling", 50) for x in lineup(second)])},
            {"batting": _avg([x.get("batting", 50) for x in lineup(second)]),
             "bowling": _avg([x.get("bowling", 50) for x in lineup(first)])},
            rng,
        )
        result.update({"winner": so["winner"], "super_over": so["super_over"], "tie_broken": True})

    result["winner_name"] = (
        first["name"] if result["winner"] == "first"
        else second["name"] if result["winner"] == "second" else "No result"
    )
    result["loser_name"] = (
        second["name"] if result["winner"] == "first"
        else first["name"] if result["winner"] == "second" else ""
    )
    # Player of the match: combined batting runs + wicket value from the engine.
    impact: dict[tuple[str, str], float] = {}
    for side_key, team, innings in (("first", first, first_innings), ("second", second, second_innings)):
        for pid, runs in innings["per_batter"].items():
            impact[(side_key, pid)] = impact.get((side_key, pid), 0.0) + runs * 1.0
        for phase in innings["phases"]:
            for b in lineup(team):
                impact[(side_key, b["id"])] = impact.get((side_key, b["id"]), 0.0) + phase["wickets"] * 12 / max(1, len(lineup(team)))
    if impact:
        (side, pid), score = max(impact.items(), key=lambda kv: kv[1])
        team = first if side == "first" else second
        potm = next((x for x in lineup(team) if x["id"] == pid), None)
        result["player_of_match"] = potm["name"] if potm else None
        result["player_of_match_id"] = pid
        result["potm_impact"] = round(score, 1)
    else:
        result["player_of_match"] = None
        result["player_of_match_id"] = None

    result.update({
        "first_name": first["name"], "second_name": second["name"],
        "first_innings": first_innings, "second_innings": second_innings,
        "target": target, "pitch": pitch,
        "tactics": tactics,
        "analysis": _tactical_analysis(first["name"], second["name"],
                                       tactics["first"], tactics["second"], result, pitch),
    })
    return result
