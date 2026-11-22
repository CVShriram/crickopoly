"""League standings, playoffs, finals and Championship scoring.

The Standard Season awards exactly 100 final points split across five
categories (see data52.RULES['final_weights']). Classic mode is pure survival:
the lastfranchise with a positive balance / valid squad remains.
"""

from __future__ import annotations

from .data52 import RULES


def nrr(record: dict) -> float:
    """Net run rate. Defensive defaults handle zero overs played."""
    of = float(record.get("overs_for", 0) or 0)
    oa = float(record.get("overs_against", 0) or 0)
    if of <= 0 or oa <= 0:
        return 0.0
    return (record.get("runs_for", 0) / of) - (record.get("runs_against", 0) / oa)


def standings(state) -> list[dict]:
    """Return franchises ranked by points, then NRR, then runs scored."""
    rows: list[dict] = []
    for fid, f in state.franchises.items():
        rec = f["record"]
        rows.append({
            "id": fid,
            "name": f["name"],
            "color": f["color"],
            "played": rec["played"],
            "wins": rec["wins"],
            "losses": rec["losses"],
            "ties": rec["ties"],
            "points": rec["points"] + rec.get("bonus", 0),
            "nrr": round(nrr(rec), 3),
            "runs_for": rec["runs_for"],
            "record": f"{rec['wins']}-{rec['losses']}" + (f"-{rec['ties']}" if rec["ties"] else ""),
        })
    rows.sort(key=lambda r: (r["points"], r["nrr"], r["runs_for"]), reverse=True)
    for idx, row in enumerate(rows, 1):
        row["rank"] = idx
    return rows


def award_result(state, fid: str, runs_for: int, runs_against: int,
                 overs_for: float, overs_against: float, outcome: str) -> None:
    """Apply a match result to a franchise's record (win/loss/tie)."""
    f = state.franchises[fid]
    rec = f["record"]
    rec["played"] += 1
    rec["runs_for"] += runs_for
    rec["runs_against"] += runs_against
    rec["overs_for"] += overs_for
    rec["overs_against"] += overs_against
    if outcome == "win":
        rec["wins"] += 1
        rec["points"] += RULES["win_points"]
    elif outcome == "loss":
        rec["losses"] += 1
        rec["points"] += RULES["loss_points"]
    else:
        rec["ties"] += 1
        rec["points"] += RULES["tie_points"]


def playoff_seeds(state) -> list[str]:
    """Top half qualify. Four or more teams -> semis; 2-3 -> direct final."""
    order = standings(state)
    n = len(order)
    if n < 2:
        return []
    if n <= 3:
        return [row["id"] for row in order[:n]]
    return [row["id"] for row in order[:4]]


def build_playoff_bracket(state) -> dict:
    seeds = playoff_seeds(state)
    if len(seeds) >= 4:
        return {
            "type": "semis_final",
            "semis": [[seeds[0], seeds[3]], [seeds[1], seeds[2]]],
            "final": [],
            "third_place": [[seeds[2], seeds[3]]],
            "seeds": seeds,
        }
    if len(seeds) == 3:
        return {"type": "final", "semis": [[seeds[1], seeds[2]]],
                "final": [seeds[0], None], "seeds": seeds}
    if len(seeds) == 2:
        return {"type": "final", "final": list(seeds), "seeds": seeds}
    return {"type": "none", "final": [], "seeds": seeds}


def champion(state, winner_id: str) -> dict:
    """Mark the tournament winner and compute the 100-point final table."""
    state.finished = True
    state.winner_id = winner_id
    state.phase = "over"
    table = final_points(state)
    state.events.append({"type": "champion", "payload": {
        "winner_id": winner_id,
        "winner_name": state.franchises[winner_id]["name"],
        "table": table,
    }, "round": state.round})
    return table


def final_points(state) -> list[dict]:
    """Standard Season 100-point final scorecard for every franchise."""
    from .franchise_economy import franchise_valuation

    weights = RULES["final_weights"]
    rows = standings(state)
    max_pts = max((r["points"] for r in rows), default=0) or 1
    vals = {fid: franchise_valuation(state, fid) for fid in state.franchises}
    max_val = max(vals.values(), default=1) or 1
    max_squad = 0
    for fid in state.franchises:
        from .squad import squad_strength
        max_squad = max(max_squad, squad_strength(state, fid, state.pitch))
    max_squad = max_squad or 1

    table: list[dict] = []
    for row in rows:
        fid = row["id"]
        f = state.franchises[fid]
        champ = (weights["championship"] if fid == state.winner_id
                 else int(weights["championship"] * row["points"] / max_pts * 0.6))
        finance = int(weights["finance"] * vals[fid] / max_val)
        from .squad import squad_strength
        squad = int(weights["squad"] * squad_strength(state, fid, state.pitch) / max_squad)
        infra = min(weights["infrastructure"],
                    len(f["stadiums"]) * 3 + sum(len(v) for v in f["stadiums"].values()))
        collections = min(weights["collections"], len(f["markets"]))
        total = champ + finance + squad + infra + collections
        table.append({
            "id": fid, "name": f["name"], "color": f["color"],
            "championship": champ, "finance": finance, "squad": squad,
            "infrastructure": infra, "collections": collections,
            "total": min(100, total), "league_points": row["points"],
            "rank": row["rank"],
        })
    table.sort(key=lambda r: r["total"], reverse=True)
    for idx, r in enumerate(table, 1):
        r["final_rank"] = idx
    return table


def classic_survivors(state) -> list[str]:
    """Classic survival: alive if balance >= 0 and at least 11 contracted."""
    return [
        fid for fid, f in state.franchises.items()
        if f["balance"] >= 0 and len(f["squad"]) >= RULES["xi_size"]
    ]


def check_classic_survival(state) -> str | None:
    alive = classic_survivors(state)
    if len(alive) <= 1:
        return alive[0] if alive else None
    return None
