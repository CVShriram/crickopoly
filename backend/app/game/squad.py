"""Squad construction, Playing XI validation and chemistry calculation.

Chemistry never overrides player quality: all bonuses are deliberately small
(usually 1–6%) and are additive caps applied by the match engine.
"""

from __future__ import annotations

from collections import Counter

from .data52 import PLAYERS_BY_ID, ROLE_LABELS, RULES


def _player(pid: str) -> dict | None:
    return PLAYERS_BY_ID.get(pid)


def squad_players(state, fid: str) -> list[dict]:
    f = state.franchises[fid]
    return [p for pid in f["squad"] if (p := _player(pid))]


def xi_players(state, fid: str) -> list[dict]:
    f = state.franchises[fid]
    return [p for pid in f["xi"] if (p := _player(pid))]


def is_available(state, fid: str, pid: str) -> bool:
    f = state.franchises[fid]
    cond = f.get("conditions", {}).get(pid, {})
    return pid in f["squad"] and cond.get("injury") is None


def add_to_squad(state, fid: str, player_id: str, price: int) -> None:
    f = state.franchises[fid]
    if player_id not in PLAYERS_BY_ID:
        raise ValueError("Unknown player")
    if player_id in f["squad"]:
        raise ValueError("Player already contracted to this franchise")
    if any(player_id in fr["squad"] for oid, fr in state.franchises.items() if oid != fid):
        raise ValueError("Player already contracted to another franchise")
    if len(f["squad"]) >= RULES["squad_capacity"]:
        raise ValueError(f"Squad is full ({RULES['squad_capacity']} players)")
    f["squad"][player_id] = {"price": price, "tier": PLAYERS_BY_ID[player_id]["tier"]}
    from ..state import fresh_condition
    f["conditions"][player_id] = fresh_condition(PLAYERS_BY_ID[player_id])


def release_player(state, fid: str, player_id: str) -> None:
    f = state.franchises[fid]
    if player_id not in f["squad"]:
        raise ValueError("Player not in squad")
    del f["squad"][player_id]
    f["conditions"].pop(player_id, None)
    if player_id in f["xi"]:
        f["xi"].remove(player_id)
    if f.get("captain") == player_id:
        f["captain"] = None
    if f.get("vice") == player_id:
        f["vice"] = None


def validate_xi(state, fid: str, xi: list[str] | None = None,
                captain: str | None = None, vice: str | None = None) -> tuple[bool, list[str]]:
    """Return (valid, list of human-readable violations)."""
    f = state.franchises[fid]
    xi = list(xi if xi is not None else f["xi"])
    captain = captain or f.get("captain")
    vice = vice or f.get("vice")
    errors: list[str] = []
    if len(xi) != RULES["xi_size"]:
        errors.append(f"Playing XI must contain exactly {RULES['xi_size']} players (has {len(xi)})")
    if len(set(xi)) != len(xi):
        errors.append("Duplicate players in Playing XI")
    for pid in xi:
        if pid not in f["squad"]:
            errors.append("Selected player is not in your squad")
        elif not is_available(state, fid, pid):
            errors.append("Injured player cannot be selected")
    counts = Counter(_player(pid)["role"] for pid in xi if _player(pid))
    for role, limits in RULES["xi_roles"].items():
        n = counts.get(role, 0)
        if n < limits["min"]:
            errors.append(f"Need at least {limits['min']} {ROLE_LABELS[role].lower()}(s) (has {n})")
        if n > limits["max"]:
            errors.append(f"At most {limits['max']} {ROLE_LABELS[role].lower()}(s) allowed (has {n})")
    if captain and captain not in xi:
        errors.append("Captain must be in the Playing XI")
    if vice and vice not in xi:
        errors.append("Vice-captain must be in the Playing XI")
    if captain and vice and captain == vice:
        errors.append("Captain and vice-captain must be different players")
    return (not errors), errors


def set_xi(state, fid: str, xi: list[str], captain: str | None = None,
           vice: str | None = None) -> tuple[bool, list[str]]:
    ok, errors = validate_xi(state, fid, xi, captain, vice)
    if ok:
        f = state.franchises[fid]
        f["xi"] = list(xi)
        f["captain"] = captain
        f["vice"] = vice
    return ok, errors


def auto_xi(state, fid: str) -> tuple[bool, list[str]]:
    """Build a valid XI automatically (used by AI and as a convenience)."""
    f = state.franchises[fid]
    players = [p for p in squad_players(state, fid) if is_available(state, fid, p["id"])]
    players.sort(key=lambda p: p["overall"], reverse=True)
    chosen: dict[str, list[dict]] = {r: [] for r in RULES["xi_roles"]}
    for p in players:
        chosen[p["role"]].append(p)
    xi: list[str] = []
    for role, limits in RULES["xi_roles"].items():
        xi.extend(p["id"] for p in chosen[role][: limits["max"]])
    # If short (fewer than 11), fill with best remaining regardless of role.
    if len(xi) < RULES["xi_size"]:
        for p in players:
            if p["id"] not in xi and len(xi) < RULES["xi_size"]:
                xi.append(p["id"])
    if len(xi) > RULES["xi_size"]:
        # Prefer keeping role coverage when trimming: drop the lowest-rated
        # players from roles that are above their minimum first.
        ranked = {p["id"]: p["overall"] for p in players}
        role_by_id = {p["id"]: p["role"] for p in players}
        while len(xi) > RULES["xi_size"]:
            removable = [
                pid for pid in xi
                if sum(1 for x in xi if role_by_id.get(x) == role_by_id.get(pid))
                > RULES["xi_roles"].get(role_by_id.get(pid), {}).get("min", 0)
            ]
            if not removable:
                removable = list(xi)
            drop = min(removable, key=lambda pid: ranked.get(pid, 0))
            xi.remove(drop)
    # Final safety net: never leave the XI empty — always field the best 11
    # available even if role coverage is imperfect (warnings are surfaced).
    if len(xi) < RULES["xi_size"]:
        ranked = {p["id"]: p["overall"] for p in players}
        for p in sorted(players, key=lambda x: ranked.get(x["id"], 0), reverse=True):
            if len(xi) >= RULES["xi_size"]:
                break
            if p["id"] not in xi:
                xi.append(p["id"])
    captain = next((p["id"] for p in players if p["id"] in xi and p["role"] == "batsman"), xi[0] if xi else None)
    vice = next((p["id"] for p in players if p["id"] in xi and p["role"] == "allrounder"),
                next((p["id"] for p in players if p["id"] in xi and p["id"] != captain), None))
    f["xi"] = list(xi)
    f["captain"] = captain
    f["vice"] = vice
    return validate_xi(state, fid, xi, captain, vice)


def squad_warnings(state, fid: str) -> list[str]:
    f = state.franchises[fid]
    players = squad_players(state, fid)
    counts = Counter(p["role"] for p in players)
    warnings: list[str] = []
    if counts.get("batsman", 0) < 4:
        warnings.append("Thin batting reserves")
    if counts.get("bowler", 0) < 4:
        warnings.append("Not enough bowlers")
    if counts.get("wicketkeeper", 0) < 1:
        warnings.append("No wicketkeeper in the squad")
    if counts.get("allrounder", 0) < 2:
        warnings.append("Limited all-rounder flexibility")
    if len(players) < 11:
        warnings.append(f"Only {len(players)} players contracted")
    fatigued = sum(1 for p in players if f["conditions"].get(p["id"], {}).get("fatigue", 0) >= 55)
    if fatigued >= 3:
        warnings.append(f"{fatigued} fatigued players — consider rotation")
    injured = sum(1 for p in players if f["conditions"].get(p["id"], {}).get("injury"))
    if injured:
        warnings.append(f"{injured} player(s) injured")
    return warnings


def chemistry_bonus(state, fid: str, pitch: str) -> dict[str, float]:
    """Small, configurable squad-combination bonuses."""
    f = state.franchises[fid]
    lineup = xi_players(state, fid)
    by_role: dict[str, list[dict]] = {}
    for p in lineup:
        by_role.setdefault(p["role"], []).append(p)
    bat = 0.0
    bowl = 0.0
    # Opener + anchor: stable top order.
    if len(by_role.get("batsman", [])) >= 2:
        bat += 0.02
    # Anchor + finisher.
    if by_role.get("batsman") and any(p.get("abilities", {}).get("finishing", 0) >= 75 for p in lineup):
        bat += 0.02
    # Multiple all-rounders add bowling depth.
    if len(by_role.get("allrounder", [])) >= 2:
        bowl += 0.025
        bat += 0.01
    # Fast bowlers on green pitches.
    if pitch == "green" and any(p.get("abilities", {}).get("pace", 0) >= 75
                                 for p in by_role.get("bowler", [])):
        bowl += 0.03
    # Spinners on dry pitches.
    if pitch == "dry" and any(p.get("abilities", {}).get("spin", 0) >= 75
                               for p in by_role.get("bowler", [])):
        bowl += 0.035
    # Experienced captain + keeper coordination.
    captain = f.get("captain")
    if captain and by_role.get("wicketkeeper") and PLAYERS_BY_ID.get(captain, {}).get("overall", 0) >= 78:
        bowl += 0.02
    # Complete country collection → national chemistry, modest and capped.
    from .data52 import COUNTRIES
    for country in COUNTRIES:
        markets = {tile for tile in f["markets"] if state_tile_country(state, tile) == country}
        if len(markets) >= 4:
            bat += 0.015
            bowl += 0.015
    return {"batting": round(min(0.08, bat), 4), "bowling": round(min(0.08, bowl), 4)}


def state_tile_country(state, tile_pos: int) -> str | None:
    from .data52 import BOARD
    if 0 <= tile_pos < len(BOARD):
        return BOARD[tile_pos].get("country")
    return None


def squad_strength(state, fid: str, pitch: str) -> int:
    players = xi_players(state, fid) or squad_players(state, fid)
    if not players:
        return 0
    chem = chemistry_bonus(state, fid, pitch)
    total = sum(p["overall"] for p in players[:11]) / min(11, len(players))
    return int(total * (1 + (chem["batting"] + chem["bowling"]) / 2))
