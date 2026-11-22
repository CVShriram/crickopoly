"""High-level game orchestration on top of the modular engines.

This module is the single entry point used by REST/WebSocket handlers. It
owns game creation, the inaugural draft, match setup/resolution, AI turns and
save/load state snapshots.
"""

from __future__ import annotations

import time
from collections import Counter
from copy import deepcopy
from typing import Any

from ..state import GameState, new_franchise  # noqa: F401
from . import ai, auction, conditions, match as matchmod, squad, tournament, turn
from . import franchise_economy as economy
from .data52 import (BOARD, DRAFT_PRICE, PITCHES, PLAYERS, PLAYERS_BY_ID,
                     RULES, STADIUMS, TACTICAL_CARDS)


AVATARS = ("🦁", "🦅", "🐯", "🐋", "🦘", "🦓", "🦉", "🐊")
COLORS = ("#c8a24b", "#4fd1c5", "#f56565", "#68d391", "#b794f4", "#f6ad55", "#63b3ed", "#fc8181")


def create_game(room_id: str, code: str, members: list[dict], settings: dict) -> GameState:
    """Build a fresh GameState from lobby members (humans + bots)."""
    cfg = {
        "starting_credits": int(settings.get("starting_credits", RULES["starting_credits"])),
        "max_players": int(settings.get("max_players", 6)),
        "mode": settings.get("mode", "standard"),
        "season_rounds": int(settings.get("season_rounds", 8)),
        "ai_difficulty": settings.get("ai_difficulty", "medium"),
        "transfer_window_every": int(settings.get("transfer_window_every", 3)),
        "tactical_reveal": bool(settings.get("tactical_reveal", True)),
        "victory_mode": settings.get("victory_mode", "standard_season"),
    }
    state = GameState(room_id=room_id, code=code, mode=cfg["mode"], settings=cfg)
    state.data_overrides = deepcopy(settings.get("data_overrides") or {})
    state.pitch = settings.get("pitch", "flat")
    order: list[str] = []
    for idx, member in enumerate(members):
        fid = member.get("id") or member.get("player_id") or str(idx)
        name = member.get("name", f"Franchise {idx + 1}")
        avatar = member.get("avatar") or AVATARS[idx % len(AVATARS)]
        color = member.get("color") or COLORS[idx % len(COLORS)]
        is_bot = bool(member.get("is_bot"))
        difficulty = member.get("difficulty", cfg["ai_difficulty"])
        state.franchises[fid] = new_franchise(
            fid, name, avatar, color,
            is_host=bool(member.get("is_host")), is_bot=is_bot,
            difficulty=difficulty, starting_credits=cfg["starting_credits"],
        )
        order.append(fid)
    state.order = order
    state.phase = "draft"
    state.started = True
    state.victory_mode = cfg["victory_mode"]
    state.log_event = None  # convenience, never serialised
    add_log(state, "system", f"Season 1 draft begins — {len(order)} franchises")
    return state


def add_log(state, kind: str, text: str, payload: dict | None = None) -> None:
    state.log.append({
        "kind": kind, "text": text, "ts": time.time(),
        "round": state.round, "payload": payload or {},
    })
    state.log = state.log[-200:]


def draft_pick(state, fid: str, player_id: str) -> dict:
    if state.phase != "draft":
        raise ValueError("Draft is not active")
    if fid != state.current_player_id:
        raise ValueError("Not your draft turn")
    if player_id not in PLAYERS_BY_ID:
        raise ValueError("Unknown player")
    if any(player_id in f["squad"] for f in state.franchises.values()):
        raise ValueError("Player already drafted")
    f = state.franchises[fid]
    if len(f["squad"]) >= 15:
        raise ValueError("Squad already full")
    price = DRAFT_PRICE[PLAYERS_BY_ID[player_id]["tier"]]
    if not economy.can_afford(state, fid, price):
        raise ValueError("Insufficient credits to draft this player")
    squad.add_to_squad(state, fid, player_id, price)
    economy.debit(state, fid, price, "draft", f"Drafted {PLAYERS_BY_ID[player_id]['name']}")
    add_log(state, "draft", f"{f['name']} signed {PLAYERS_BY_ID[player_id]['name']}")
    advance(state)
    return {"player_id": player_id, "price": price}


def draft_status(state) -> dict:
    counts = {fid: len(f["squad"]) for fid, f in state.franchises.items()}
    drafted = {pid for f in state.franchises.values() for pid in f["squad"]}
    pool_empty = len(drafted) >= len(PLAYERS)
    done = pool_empty or all(n >= 15 for n in counts.values())
    return {"counts": counts, "complete": done, "target": 15}


def advance(state) -> None:
    """Advance turn in draft or season; detect phase transitions."""
    if state.phase == "draft":
        state.turn_index += 1
        if state.turn_index >= len(state.order) * 15:
            state.phase = "season"
            state.turn_index = 0
            state.round = 1
            for fid, f in state.franchises.items():
                squad.auto_xi(state, fid)
            add_log(state, "system", "Draft complete. Standard Season begins!")
        return
    turn.next_turn(state)


def ai_draft_step(state) -> bool:
    """One AI pick if it is an AI's turn. Returns True if a pick was made."""
    if state.phase != "draft":
        return False
    fid = state.current_player_id
    f = state.franchises.get(fid)
    if not f or not f.get("is_bot"):
        return False
    pid = ai.ai_draft_pick(state, fid)
    if not pid:
        return False
    try:
        draft_pick(state, fid, pid)
        return True
    except ValueError:
        # Fallback: pick any affordable player.
        for p in PLAYERS:
            if p["id"] not in [x for fr in state.franchises.values() for x in fr["squad"]] \
                    and p["value"] <= economy.balance(state, fid):
                try:
                    draft_pick(state, fid, p["id"])
                    return True
                except ValueError:
                    continue
    return False


def _lineup(state, fid: str) -> list[dict]:
    f = state.franchises[fid]
    ids = f["xi"] or list(f["squad"])[:11]
    return [PLAYERS_BY_ID[pid] for pid in ids if pid in PLAYERS_BY_ID]


def ensure_match_ready(state, fid: str) -> tuple[bool, list[str]]:
    """Guarantee a legal XI, using emergency reserve signings if injuries
    have left a franchise short. Reserve players cost the normal draft fee."""
    ok, errors = squad.validate_xi(state, fid)
    if ok:
        return ok, errors
    ok, errors = squad.auto_xi(state, fid)
    if ok:
        return ok, errors
    f = state.franchises[fid]
    contracted = {pid for fr in state.franchises.values() for pid in fr["squad"]}
    # Prioritise the roles named in the validation errors.
    for attempt in range(6):
        ok, errors = squad.validate_xi(state, fid)
        if ok:
            break
        need = "batsman"
        for e in errors:
            for role in RULES["xi_roles"]:
                if role in e and "at least" in e:
                    need = role
                    break
        candidate = next((p for p in PLAYERS
                          if p["id"] not in contracted and p["role"] == need), None)
        candidate = candidate or next((p for p in PLAYERS if p["id"] not in contracted), None)
        if not candidate:
            break
        # A full squad with injured reserves must release one to sign a
        # replacement (the injured player leaves the club, no refund).
        if len(f["squad"]) >= RULES["squad_capacity"]:
            injured = next((pid for pid in f["squad"]
                            if f["conditions"].get(pid, {}).get("injury")), None)
            if injured:
                squad.release_player(state, fid, injured)
                contracted.discard(injured)
            else:
                # Release the lowest-rated surplus player (a role may be
                # over-stocked while another role is missing).
                counts = Counter(PLAYERS_BY_ID[p]["role"] for p in f["squad"])
                surplus = [
                    pid for pid in f["squad"]
                    if counts[PLAYERS_BY_ID[pid]["role"]]
                    > RULES["xi_roles"].get(PLAYERS_BY_ID[pid]["role"], {}).get("max", 3)
                ]
                pool = surplus or list(f["squad"])
                drop = min(pool, key=lambda p: PLAYERS_BY_ID[p]["overall"])
                squad.release_player(state, fid, drop)
                contracted.discard(drop)
        try:
            price = DRAFT_PRICE[candidate["tier"]]
            if not economy.can_afford(state, fid, price):
                credit = economy.settlement(state, fid, price - economy.balance(state, fid),
                                            "Emergency reserve signing")
                if credit["amount"] <= 0:
                    break
            squad.add_to_squad(state, fid, candidate["id"], price)
            if economy.can_afford(state, fid, price):
                economy.debit(state, fid, price, "reserve",
                              f"Emergency reserve: {candidate['name']}")
            contracted.add(candidate["id"])
            add_log(state, "reserve", f"{f['name']} signed reserve {candidate['name']}")
        except ValueError:
            break
    ok, errors = squad.auto_xi(state, fid)
    return ok, errors


PHASES = ("powerplay", "middle", "death")


def default_tactics() -> dict:
    return {
        phase: {"bat": "balanced", "bowl": "defensive", "field": "balanced"}
        for phase in PHASES
    }


def normalise_tactics(tactics: dict | None) -> dict:
    """Coerce client tactics into valid, complete phase plans."""
    src = tactics if isinstance(tactics, dict) else {}
    out = default_tactics()
    for phase in PHASES:
        part = src.get(phase) if isinstance(src.get(phase), dict) else {}
        bat = part.get("bat", "balanced")
        bowl = part.get("bowl", "defensive")
        field = part.get("field", "balanced")
        out[phase] = {
            "bat": bat if bat in matchmod.BATTING_STRATEGIES else "balanced",
            "bowl": bowl if bowl in matchmod.BOWLING_TACTICS else "defensive",
            "field": field if field in matchmod.FIELD_PLACEMENTS else "balanced",
        }
    return out


def apply_tactical_card(tactics: dict, card_id: str) -> dict:
    """Apply one earned card's phase bias to a tactics plan."""
    spec = TACTICAL_CARDS.get(card_id)
    if not spec:
        raise ValueError("Unknown tactical card")
    out = normalise_tactics(tactics)
    out.setdefault(spec["phase"], {}).update(spec["changes"])
    return out


def match_participants(state) -> list[str]:
    pending = state.pending or {}
    if pending.get("type") != "match_setup":
        return []
    return [pid for pid in (pending.get("a"), pending.get("b")) if pid in state.franchises]


def open_match(state, fid: str, opponent: str, seed: int | None = None) -> dict:
    """Open a concealed match lobby. Plans are submitted before any reveal."""
    if state.finished or state.phase == "over":
        raise ValueError("The season is already complete")
    if state.auction:
        raise ValueError("Resolve the auction first")
    if state.pending and state.pending.get("type") != "matchday":
        raise ValueError("Resolve the current action first")
    if fid not in state.franchises or opponent not in state.franchises:
        raise ValueError("Unknown franchise")
    if fid == opponent:
        raise ValueError("Choose a different opponent")
    for pid in (fid, opponent):
        ok, errors = ensure_match_ready(state, pid)
        if not ok:
            raise ValueError(f"{state.franchises[pid]['name']} XI invalid: {'; '.join(errors)}")
    state.pending = None
    state.tactics_submissions = {}
    try:
        match_seed = int(seed) if seed is not None else int(time.time() * 1000) & 0x7FFFFFFF
    except (TypeError, ValueError):
        match_seed = int(time.time() * 1000) & 0x7FFFFFFF
    state.pending = {
        "type": "match_setup", "a": fid, "b": opponent,
        "initiator": fid, "seed": match_seed, "created_at": time.time(),
    }
    add_log(state, "match", f"{state.franchises[fid]['name']} challenged "
            f"{state.franchises[opponent]['name']}")
    auto_submit_bots(state)
    record = maybe_resolve_match(state)
    return record or state.pending or {}


def submit_tactics(state, fid: str, tactics: dict | None,
                   card_id: str | None = None, *, auto: bool = False) -> dict:
    """Record one franchise's plan. Opponents cannot see it until reveal."""
    participants = match_participants(state)
    if not participants:
        raise ValueError("No match is being prepared")
    if fid not in participants:
        raise ValueError("You are not in this match")
    f = state.franchises[fid]
    card = card_id or None
    if card:
        previous = (state.tactics_submissions.get(fid) or {}).get("card")
        if card not in f["cards"] and card != previous:
            raise ValueError("You do not hold that tactical card")
    plan = normalise_tactics(tactics)
    if card:
        plan = apply_tactical_card(plan, card)
    state.tactics_submissions[fid] = {
        "tactics": plan, "card": card, "submitted_at": time.time(), "auto": bool(auto),
    }
    record = maybe_resolve_match(state)
    return record or state.tactics_submissions.get(fid, {})


def auto_submit_bots(state) -> list[str]:
    """AI managers submit their concealed plans immediately."""
    submitted: list[str] = []
    for fid in match_participants(state):
        f = state.franchises[fid]
        pending = state.pending or {}
        other = pending.get("b") if fid == pending.get("a") else pending.get("a")
        if not f.get("is_bot") or fid in state.tactics_submissions or not other:
            continue
        tactics = ai.ai_tactics(state, fid, other, state.pitch)
        card = f["cards"][0] if f.get("cards") else None
        submit_tactics(state, fid, tactics, card, auto=True)
        submitted.append(fid)
    return submitted


def maybe_resolve_match(state) -> dict | None:
    """Resolve a concealed match as soon as both plans are available."""
    pending = state.pending or {}
    if pending.get("type") != "match_setup":
        return None
    a, b = pending.get("a"), pending.get("b")
    if a not in state.tactics_submissions or b not in state.tactics_submissions:
        return None
    sub_a, sub_b = state.tactics_submissions[a], state.tactics_submissions[b]
    # Consume any tactical cards only once, at the moment of reveal.
    for fid, sub in ((a, sub_a), (b, sub_b)):
        card = sub.get("card")
        cards = state.franchises[fid]["cards"]
        if card and card in cards:
            cards.remove(card)
    fixture = prepare_match(
        state, a, b, seed=pending.get("seed"),
        tactics_a=sub_a["tactics"], tactics_b=sub_b["tactics"],
    )
    record = resolve_match(state, fixture)
    state.pending = None
    state.tactics_submissions = {}
    if state.phase == "season":
        advance(state)
    maybe_end_season(state)
    return record


def reveal_match(state, fid: str | None = None) -> dict | None:
    """Reveal plans, filling any missing participant with its default plan."""
    participants = match_participants(state)
    if not participants:
        raise ValueError("No match is being prepared")
    if fid and fid not in participants:
        raise ValueError("You are not in this match")
    for pid in participants:
        if pid not in state.tactics_submissions:
            other = next((x for x in participants if x != pid), pid)
            tactics = ai.ai_tactics(state, pid, other, state.pitch)
            state.tactics_submissions[pid] = {
                "tactics": normalise_tactics(tactics), "card": None,
                "submitted_at": time.time(), "auto": True,
            }
    return maybe_resolve_match(state)


def cancel_match(state, fid: str | None = None) -> None:
    pending = state.pending or {}
    if pending.get("type") != "match_setup":
        raise ValueError("No match is being prepared")
    f = state.franchises.get(fid or pending.get("initiator"), {})
    if fid and fid not in (pending.get("a"), pending.get("b"), pending.get("initiator")) \
            and not f.get("is_host"):
        raise ValueError("Only match participants can cancel")
    state.pending = None
    state.tactics_submissions = {}


def prepare_match(state, fid_a: str, fid_b: str, seed: int | None = None,
                  tactics_a: dict | None = None, tactics_b: dict | None = None) -> dict:
    """Validate XIs and return a match descriptor (no state mutation yet)."""
    ok_a, err_a = ensure_match_ready(state, fid_a)
    ok_b, err_b = ensure_match_ready(state, fid_b)
    if not ok_a:
        raise ValueError(f"{state.franchises[fid_a]['name']} XI invalid: {'; '.join(err_a)}")
    if not ok_b:
        raise ValueError(f"{state.franchises[fid_b]['name']} XI invalid: {'; '.join(err_b)}")
    pitch = state.pitch
    tactics_a = tactics_a or ai.ai_tactics(state, fid_a, fid_b, pitch)
    tactics_b = tactics_b or ai.ai_tactics(state, fid_b, fid_a, pitch)
    seed = seed if seed is not None else int(time.time() * 1000) & 0x7FFFFFFF
    return {
        "a": fid_a, "b": fid_b, "pitch": pitch, "seed": seed,
        "tactics": {"first": tactics_a, "second": tactics_b},
        "venue": None,
    }


def resolve_match(state, fixture: dict) -> dict:
    """Simulate and fully apply a match to state (records, conditions, economy)."""
    fid_a, fid_b = fixture["a"], fixture["b"]
    a, b = state.franchises[fid_a], state.franchises[fid_b]
    conditions_a = {
        pid: {**PLAYERS_BY_ID[pid], **a["conditions"].get(pid, {}),
              "trained_attrs": a["conditions"].get(pid, {}).get("trained_attrs", {})}
        for pid in a["xi"]
    }
    conditions_b = {
        pid: {**PLAYERS_BY_ID[pid], **b["conditions"].get(pid, {}),
              "trained_attrs": b["conditions"].get(pid, {}).get("trained_attrs", {})}
        for pid in b["xi"]
    }
    team_a = {
        "name": a["name"], "lineup": _lineup(state, fid_a),
        "conditions": conditions_a,
        "chemistry": squad.chemistry_bonus(state, fid_a, fixture["pitch"]),
    }
    team_b = {
        "name": b["name"], "lineup": _lineup(state, fid_b),
        "conditions": conditions_b,
        "chemistry": squad.chemistry_bonus(state, fid_b, fixture["pitch"]),
    }
    # apply trained attributes to lineup copies so the engine sees them
    for team, conds in ((team_a, conditions_a), (team_b, conditions_b)):
        for p in team["lineup"]:
            trained = conds.get(p["id"], {}).get("trained_attrs", {})
            for attr, val in trained.items():
                p[attr] = val
    result = matchmod.simulate_match(
        team_a, team_b, fixture["pitch"], fixture["tactics"],
        seed=fixture["seed"], venue=fixture.get("venue"),
    )

    a_innings, b_innings = result["first_innings"], result["second_innings"]
    if result["winner"] == "first":
        outcome_a, outcome_b = "win", "loss"
    elif result["winner"] == "second":
        outcome_a, outcome_b = "loss", "win"
    else:
        outcome_a = outcome_b = "tie"
    tournament.award_result(state, fid_a, a_innings["runs"], b_innings["runs"],
                            a_innings["overs"], b_innings["overs"], outcome_a)
    tournament.award_result(state, fid_b, b_innings["runs"], a_innings["runs"],
                            b_innings["overs"], a_innings["overs"], outcome_b)

    winner_fid = fid_a if result["winner"] == "first" else fid_b if result["winner"] == "second" else None
    for fid, runs, wickets in ((fid_a, a_innings["runs"], a_innings["wickets"]),
                               (fid_b, b_innings["runs"], b_innings["wickets"])):
        notes = conditions.apply_match_conditions(
            state, fid, runs, wickets, winner_fid == fid, seed=fixture["seed"] + len(fid)
        )
        for n in notes:
            add_log(state, "injury", n)
    if winner_fid:
        economy.credit(state, winner_fid, 60, "prize", "Match victory prize")

    record = {
        "id": f"match-{len(state.matches) + 1:04d}",
        "round": state.round, "season": state.season,
        "a": fid_a, "b": fid_b, "a_name": a["name"], "b_name": b["name"],
        "a_runs": a_innings["runs"], "a_wickets": a_innings["wickets"],
        "b_runs": b_innings["runs"], "b_wickets": b_innings["wickets"],
        "winner": winner_fid, "winner_name": result["winner_name"],
        "margin_runs": result.get("margin_runs", 0),
        "margin_wickets": result.get("margin_wickets", 0),
        "pitch": fixture["pitch"], "seed": fixture["seed"],
        "tactics": fixture["tactics"], "analysis": result["analysis"],
        "player_of_match": result.get("player_of_match"),
        "phases_a": a_innings["phases"], "phases_b": b_innings["phases"],
        "ts": time.time(),
    }
    state.matches.append(record)
    state.events.append({"type": "match", "payload": record, "round": state.round})
    add_log(state, "match",
            f"{a['name']} {a_innings['runs']}/{a_innings['wickets']} vs "
            f"{b['name']} {b_innings['runs']}/{b_innings['wickets']} — {result['winner_name']}")
    return record


def maybe_end_season(state) -> bool:
    """At the configured round count, move to playoffs or declare a champion."""
    rounds = state.settings.get("season_rounds", 8)
    if state.phase != "season" or state.round <= rounds:
        return False
    bracket = tournament.build_playoff_bracket(state)
    state.playoff_bracket = bracket
    state.phase = "playoffs"
    add_log(state, "system", f"League complete — playoffs: {bracket['type']}")
    # Automatically resolve playoffs unless an interactive client takes over.
    while state.phase == "playoffs":
        step_playoff(state)
    return True


def step_playoff(state) -> dict | None:
    bracket = getattr(state, "playoff_bracket", None) or tournament.build_playoff_bracket(state)
    if bracket["type"] in ("none", "final"):
        finalists = bracket.get("final", [])
        if len(finalists) == 2 and all(finalists):
            fixture = prepare_match(state, finalists[0], finalists[1])
            record = resolve_match(state, fixture)
            winner = record["winner"] or finalists[0]
            tournament.champion(state, winner)
            add_log(state, "final", f"{state.franchises[winner]['name']} are champions!")
            return record
        if bracket.get("semis") and all(bracket["semis"][0]):
            pair = bracket["semis"][0]
            fixture = prepare_match(state, pair[0], pair[1])
            record = resolve_match(state, fixture)
            winner = record["winner"] or pair[0]
            tournament.champion(state, winner)
            return record
        # Single team left.
        if bracket.get("seeds"):
            tournament.champion(state, bracket["seeds"][0])
        state.phase = "over"
        return None
    for key in ("semis", "third_place"):
        for pair in bracket.get(key, []):
            if pair and all(pair) and not any(m.get("playoff_pair") == pair for m in state.matches):
                fixture = prepare_match(state, pair[0], pair[1])
                record = resolve_match(state, fixture)
                record["playoff_pair"] = list(pair)
                record["playoff_stage"] = key
                return record
    # All semis done -> final between winners.
    winners: list[str] = []
    for pair in bracket.get("semis", []):
        for m in reversed(state.matches):
            if m.get("playoff_pair") == pair:
                winners.append(m["winner"] or pair[0])
                break
    if len(winners) >= 2:
        fixture = prepare_match(state, winners[0], winners[1])
        record = resolve_match(state, fixture)
        record["playoff_stage"] = "final"
        tournament.champion(state, record["winner"] or winners[0])
        return record
    if bracket.get("final") and len(bracket["final"]) == 2 and all(bracket["final"]):
        fixture = prepare_match(state, bracket["final"][0], bracket["final"][1])
        record = resolve_match(state, fixture)
        tournament.champion(state, record["winner"] or bracket["final"][0])
        return record
    state.phase = "over"
    return None


def run_ai_step(state) -> list[dict]:
    """Let the current AI franchise take its whole turn (used by hosts)."""
    actions: list[dict] = []
    fid = state.current_player_id
    f = state.franchises.get(fid)
    if not f or not f.get("is_bot") or state.finished:
        return actions
    if state.phase == "draft":
        if ai_draft_step(state):
            actions.append({"type": "draft", "fid": fid})
        return actions
    if state.phase != "season":
        return actions
    if state.auction:
        dec = ai.ai_auction_action(state, fid)
        if dec["action"] == "bid":
            try:
                auction.place_bid(state, fid, dec["amount"])
                actions.append({"type": "bid", "fid": fid, "amount": dec["amount"]})
            except ValueError:
                pass
        elif dec["action"] == "pass":
            auction.pass_auction(state, fid)
            actions.append({"type": "pass", "fid": fid})
        # Resolve expired lots asynchronously via tick (caller can invoke).
        return actions
    if state.pending:
        if state.pending.get("type") == "match_setup":
            auto_submit_bots(state)
            record = maybe_resolve_match(state)
            if record:
                actions.append({"type": "match", "fid": fid, "record": record})
        return actions
    roll = turn.roll_dice(state, fid)
    actions.append({"type": "roll", "fid": fid, "dice": roll["dice"], "to": roll["to"]})
    ai_action = ai.ai_tile_action(state, fid, roll)
    actions.append({"type": "tile", "fid": fid, "result": ai_action})
    if state.pending and state.pending.get("type") == "purchase":
        turn.skip_purchase(state, fid)
    if state.pending and state.pending.get("type") == "matchday":
        opponent = None
        for candidate in state.order:
            if candidate == fid:
                continue
            ok, _ = ensure_match_ready(state, candidate)
            if ok:
                opponent = candidate
                break
        if opponent:
            state.pending = None
            open_match(state, fid, opponent)
            auto_submit_bots(state)
            record = maybe_resolve_match(state)
            actions.append({"type": "match", "fid": fid, "opponent": opponent,
                            "record": record})
            if state.pending:
                return actions
            maybe_end_season(state)
            return actions
        state.pending = None
    upgrade = ai.ai_upgrade(state, fid)
    if upgrade:
        actions.append({"type": "upgrade", "fid": fid, "result": upgrade})
    advance(state)
    maybe_end_season(state)
    return actions


def series_ai_steps(state, max_steps: int = 40) -> list[dict]:
    """Advance AI turns until a human's turn or game end (bounded)."""
    all_actions: list[dict] = []
    for _ in range(max_steps):
        if state.finished:
            break
        fid = state.current_player_id
        f = state.franchises.get(fid)
        if not f or not f.get("is_bot"):
            break
        step = run_ai_step(state)
        all_actions.extend(step)
        if not step:
            break
        auction.tick_auctions(state)
    return all_actions
