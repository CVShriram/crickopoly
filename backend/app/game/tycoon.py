"""Pure rules engine for Crickopoly: Stadium Tycoon.

This is a complete rule replacement. It deliberately keeps the existing 52-tile
board, 96 real cricketers and 8 stadiums from data52, but adds its own scoring,
tactics and turn resolution so the old draft/XI/T20 rules are not involved.

No network, database or socket code lives here.
"""

from __future__ import annotations

import random
from copy import deepcopy
from typing import Any

from . import data52

RULES_VERSION = 2

DEFAULT_SETTINGS: dict[str, Any] = {
    "starting_credits": 1500,
    "max_players": 6,
    "season_rounds": 8,
    "mode": "standard",
    "pitch": "flat",
    "ai_difficulty": "medium",
}

PITCH_KEYS = ("flat", "green", "dry", "slow")

PITCH_EFFECTS: dict[str, dict[str, Any]] = {
    "flat": {"runs": 10, "wickets": 0, "note": "True bounce — batters add 10 runs."},
    "green": {"runs": 0, "wickets": 2, "note": "Seam movement — bowlers add 2 wickets."},
    "dry": {"runs": -10, "wickets": 1, "note": "Turn — spinners save 10 runs and add 1 wicket."},
    "slow": {"runs": 0, "wickets": 0, "note": "Slow carry — placement cards are rewarded."},
}

# One-card cricket tactics. run_mod moves your own score; bowl_mod suppresses
# the opponent's score and adds wickets; risk adds wickets to your own innings.
TACTICS: dict[str, dict[str, Any]] = {
    "powerplay": {"id": "powerplay", "name": "Powerplay Charge", "icon": "⚡",
                  "kind": "bat", "run_mod": 24, "bowl_mod": 0, "risk": 2,
                  "pitch": "flat", "slow_penalty": -8,
                  "desc": "Attack the first six overs. Big runs, extra wicket risk."},
    "anchor": {"id": "anchor", "name": "Anchor Chase", "icon": "⚓",
               "kind": "bat", "run_mod": 10, "bowl_mod": 0, "risk": -2,
               "pitch": "slow", "pitch_run": 12, "desc": "Protect wickets and pace the chase. Strong on slow pitches."},
    "death_slog": {"id": "death_slog", "name": "Death Over Slog", "icon": "🚀",
                   "kind": "bat", "run_mod": 34, "bowl_mod": 0, "risk": 3,
                   "desc": "Swing late and hard. Huge runs if it comes off."},
    "swing": {"id": "swing", "name": "Swing Assault", "icon": "🌬️",
              "kind": "bowl", "run_mod": -8, "bowl_mod": 3, "risk": 1,
              "pitch": "green", "pitch_wicket": 2, "desc": "Attack the new ball. Deadly on green pitches."},
    "spin_web": {"id": "spin_web", "name": "Spin Web", "icon": "🕸️",
                 "kind": "bowl", "run_mod": -18, "bowl_mod": 1, "risk": 0,
                 "pitch": "dry", "pitch_run": -10, "desc": "Dry the runs up through the middle overs."},
    "yorker": {"id": "yorker", "name": "Yorker Rampage", "icon": "🎯",
               "kind": "bowl", "run_mod": 12, "bowl_mod": 2, "risk": 2,
               "desc": "Save the yorkers for the last five overs."},
    "pressure": {"id": "pressure", "name": "All-Round Pressure", "icon": "🛡️",
                 "kind": "balanced", "run_mod": 8, "bowl_mod": 1, "risk": 0,
                 "desc": "No weaknesses. Works on every surface."},
}

TACTIC_IDS = tuple(TACTICS)

EVENT_RESULTS: dict[str, dict[str, Any]] = {
    "mega_auction": {"kind": "auction", "text": "Mega auction opened. Submit a sealed bid for the featured star."},
    "matchday_arena": {"kind": "duel", "text": "Matchday! Pick a tactic to challenge the next manager for an 80 FC pot."},
    "injury_reserve": {"kind": "cash", "amount": 60, "text": "Recovery costs covered — +60 FC from the league."},
    "training_camp": {"kind": "cash", "amount": 80, "text": "Subsidised camp — +80 FC talent grant."},
    "sponsorship_deal": {"kind": "cash", "amount": 120, "text": "New sponsor signed — +120 FC."},
    "championship_qualifier": {"kind": "cash", "amount": 100, "text": "Qualifier bonus — +100 FC."},
    "strategy_room": {"kind": "card", "text": "Strategy room — a fresh tactic card was added to your hand."},
    "recovery_camp": {"kind": "cash", "amount": 60, "text": "Sports science support — +60 FC."},
}


def rng_for(state: dict, label: str = "") -> random.Random:
    """Deterministic per-action randomness, so replays/tests are stable."""
    seed = f"{state.get('code', 'GAME')}:{state.get('round', 1)}:{state.get('turn_index', 0)}:{label}"
    return random.Random(seed)


def player_map(overrides: dict | None = None) -> dict[str, dict]:
    return {p["id"]: p for p in data52.merged_players(overrides)}


def starter_squad(overrides: dict | None = None, index: int = 0) -> list[str]:
    """Six unique real cricketers: two batters, two bowlers, a keeper, an all-rounder.

    The country rotates by manager index so every table starts with different
    bronze players instead of six cloned squads.
    """
    pmap = player_map(overrides)
    countries = list(data52.COUNTRIES)
    roles = ("batsman", "batsman", "bowler", "bowler", "wicketkeeper", "allrounder")
    squad: list[str] = []
    for offset, role in enumerate(roles):
        country = countries[(index * len(roles) + offset) % len(countries)]
        pid = f"{country}_{role}_bronze"
        if pid in pmap and pid not in squad:
            squad.append(pid)
    if len(squad) < 6:
        for player in pmap.values():
            if player.get("tier") == "bronze" and player["id"] not in squad and player["role"] in roles:
                squad.append(player["id"])
                if len(squad) == 6:
                    break
    return squad[:6]


def draw_hand(rng: random.Random) -> list[str]:
    hand = rng.sample(list(TACTIC_IDS), 5)
    if "pressure" not in hand:
        hand[-1] = "pressure"
    return hand


def draw_replacement(hand: list[str], rng: random.Random) -> str:
    options = [card for card in TACTIC_IDS if card not in hand]
    return rng.choice(options or list(TACTIC_IDS))


def new_state(lobby: dict, overrides: dict | None = None) -> dict:
    settings = dict(DEFAULT_SETTINGS)
    settings.update(lobby.get("settings") or {})
    settings["max_players"] = max(2, min(6, int(settings.get("max_players", 6))))
    settings["season_rounds"] = max(2, min(16, int(settings.get("season_rounds", 8))))
    settings["starting_credits"] = max(500, min(5000, int(settings.get("starting_credits", 1500))))

    members = list((lobby.get("members") or {}).values())
    order = [m["id"] for m in members]
    franchises: dict[str, dict] = {}
    for index, member in enumerate(members):
        pid = member["id"]
        franchises[pid] = {
            "id": pid,
            "name": member.get("name", "Manager"),
            "avatar": member.get("avatar", "🏏"),
            "color": member.get("color", "#c8a24b"),
            "is_host": bool(member.get("is_host")),
            "is_bot": bool(member.get("is_bot")),
            "difficulty": member.get("difficulty", "medium"),
            "pos": 0,
            "balance": int(settings["starting_credits"]),
            "squad": starter_squad(overrides, index),
            "tactics": draw_hand(rng_for({"code": lobby.get("code", "GAME")}, pid)),
            "stadiums": [],
            "duels_won": 0,
            "last_action": "Joined the league",
        }

    return {
        "ruleset": RULES_VERSION,
        "room_id": lobby.get("room_id", ""),
        "code": lobby.get("code", ""),
        "host_id": lobby.get("host_id", ""),
        "started": True,
        "finished": False,
        "phase": "season",
        "season": 1,
        "round": 1,
        "mode": settings.get("mode", "standard"),
        "settings": settings,
        "pitch": settings.get("pitch", "flat"),
        "current_player_id": order[0] if order else None,
        "order": order,
        "turn_index": 0,
        "franchises": franchises,
        "ownership": {},
        "pending": None,
        "auction": None,
        "dice": [],
        "log": [],
        "events": [],
        "data_overrides": deepcopy(overrides or {}),
        "winner_id": None,
    }


def squad_ratings(squad_ids: list[str], pmap: dict[str, dict]) -> dict[str, int]:
    players = [pmap[pid] for pid in squad_ids if pid in pmap]
    batters = [p for p in players if p["role"] in ("batsman", "allrounder")]
    bowlers = [p for p in players if p["role"] in ("bowler", "allrounder")]
    keepers = [p for p in players if p["role"] == "wicketkeeper"]

    def total(items: list[dict], key: str, count: int) -> int:
        values = sorted((int(p.get(key, 50)) for p in items), reverse=True)[:count]
        if not values:
            return 0
        # Scale a short squad up to a full four-player contribution so early
        # seasons are not crippled before managers can sign more cricketers.
        return round(sum(values) * count / len(values))

    return {
        "bat": total(batters, "batting", 4),
        "bowl": total(bowlers, "bowling", 4),
        "field": total(players, "fielding", 4) + total(keepers, "fielding", 1) // 5,
    }


def brand_value(franchise: dict, state: dict) -> int:
    pmap = player_map(state.get("data_overrides"))
    stadium_value = sum(
        int((data52.STADIUMS.get(pos) or {}).get("price", 0))
        for pos in franchise.get("stadiums", [])
    )
    player_value = len(franchise.get("squad", [])) * 20
    return int(
        franchise.get("balance", 0)
        + stadium_value * 1.5
        + player_value
        + franchise.get("duels_won", 0) * 200
    )


def standings(state: dict) -> list[dict]:
    rows = []
    for fid, f in state.get("franchises", {}).items():
        rows.append({
            "id": fid,
            "name": f.get("name", "Manager"),
            "avatar": f.get("avatar", "🏏"),
            "color": f.get("color", "#c8a24b"),
            "brand_value": brand_value(f, state),
            "cash": f.get("balance", 0),
            "stadiums": len(f.get("stadiums", [])),
            "players": len(f.get("squad", [])),
            "duels_won": f.get("duels_won", 0),
        })
    rows.sort(key=lambda r: (-r["brand_value"], r["name"]))
    for index, row in enumerate(rows, 1):
        row["rank"] = index
    return rows


def add_log(state: dict, text: str, kind: str = "info") -> None:
    entry = {"text": text, "kind": kind, "round": state.get("round", 1)}
    state.setdefault("log", []).append(entry)
    state.setdefault("events", []).append(entry)
    state["log"] = state["log"][-100:]
    state["events"] = state["events"][-50:]


def signed_players(state: dict) -> set[str]:
    result: set[str] = set()
    for f in state.get("franchises", {}).values():
        result.update(f.get("squad", []))
    return result


def charge(state: dict, pid: str, amount: int, creditor: str | None = None) -> tuple[str, int]:
    """Pay from a franchise, selling its cheapest player if short."""
    f = state["franchises"][pid]
    amount = max(0, int(amount))
    note = ""
    if f["balance"] < amount:
        pmap = player_map(state.get("data_overrides"))
        owned = sorted(f.get("squad", []), key=lambda x: pmap.get(x, {}).get("value", 50))
        for sale_id in owned:
            if f["balance"] >= amount or len(f["squad"]) <= 6:
                break
            if sale_id not in f["squad"]:
                continue
            f["squad"].remove(sale_id)
            value = int(pmap.get(sale_id, {}).get("value", 50))
            f["balance"] += value
            note = f" Sold {pmap.get(sale_id, {}).get('name', 'a player')} for {value} FC to cover costs."
    paid = min(f["balance"], amount)
    shortfall = amount - paid
    f["balance"] -= paid
    if creditor and paid:
        state["franchises"][creditor]["balance"] += paid
    return note, shortfall


def market_offer(state: dict, pos: int) -> dict | None:
    tile = data52.BOARD[pos]
    if tile.get("kind") != "market":
        return None
    taken = signed_players(state)
    pool = [
        p for p in data52.merged_players(state.get("data_overrides"))
        if p["country"] == tile["country"] and p["role"] == tile["role"] and p["id"] not in taken
    ]
    if not pool:
        return None
    rng = rng_for(state, f"offer-{pos}")
    by_tier: dict[str, list[dict]] = {}
    for p in pool:
        by_tier.setdefault(p["tier"], []).append(p)
    candidates: list[str] = []
    for tier in ("bronze", "silver", "gold"):
        group = by_tier.get(tier) or []
        if group:
            candidates.append(rng.choice(group)["id"])
    if len(candidates) < 3:
        for p in rng.sample(pool, min(3 - len(candidates), len(pool))):
            if p["id"] not in candidates:
                candidates.append(p["id"])
    return {
        "pos": pos,
        "country": tile["country"],
        "role": tile["role"],
        "price": int(tile.get("price", 150)),
        "candidates": candidates[:3],
    }


def apply_event(state: dict, pid: str, tile: dict) -> dict:
    """Apply a non-contest tile. Returns a pending descriptor."""
    event = EVENT_RESULTS.get(tile.get("id"), {
        "kind": "cash", "amount": 50, "text": "League bonus — +50 FC."
    })
    fid = tile.get("id", "event")
    f = state["franchises"][pid]
    if event["kind"] == "cash":
        amount = int(event.get("amount", 50))
        f["balance"] += amount
        add_log(state, f"{f['name']}: {event['text']}", "event")
        return {"type": "result", "pid": pid, "title": tile.get("name", "Event"), "text": event["text"]}
    if event["kind"] == "card":
        rng = rng_for(state, f"card-{pid}")
        card = rng.choice(list(TACTIC_IDS))
        if card not in f["tactics"]:
            f["tactics"].append(card)
        add_log(state, f"{f['name']} gained {TACTICS[card]['name']}.", "card")
        return {"type": "result", "pid": pid, "title": "Tactic gained",
                "text": f"{TACTICS[card]['icon']} {TACTICS[card]['name']} added to your hand."}
    if event["kind"] == "auction":
        return open_auction(state, pid)
    if event["kind"] == "duel":
        defender = next_manager(state, pid)
        return {"type": "duel", "pid": pid, "defender": defender, "pos": None,
                "rent": 80, "pot": True, "cards": {}, "result": None,
                "label": "Matchday challenge"}
    return {"type": "result", "pid": pid, "title": tile.get("name", "Event"), "text": event["text"]}


def next_manager(state: dict, pid: str) -> str:
    order = state.get("order") or []
    if pid not in order or len(order) < 2:
        return pid
    return order[(order.index(pid) + 1) % len(order)]


def open_auction(state: dict, pid: str) -> dict:
    taken = signed_players(state)
    pool = [p for p in data52.merged_players(state.get("data_overrides")) if p["id"] not in taken]
    if not pool:
        return {"type": "result", "pid": pid, "title": "Auction", "text": "Every cricketer is already signed."}
    rng = rng_for(state, f"auction-{pid}")
    star = rng.choice([p for p in pool if p["tier"] == "gold"] or pool)
    auction = {
        "id": f"{state['code']}-{state['round']}-{state['turn_index']}",
        "player_id": star["id"],
        "base_price": int(star.get("value", 80)),
        "bids": {},
        "passed": [],
        "opened_by": pid,
        "revealed": False,
    }
    state["auction"] = auction
    add_log(state, f"{state['franchises'][pid]['name']} opened the auction for {star['name']}.", "auction")
    result = {"type": "result", "pid": pid, "title": "Sealed auction",
              "text": f"{star['name']} is up for grabs. Everyone submits one sealed bid."}
    state["pending"] = result
    return result


def roll(state: dict, pid: str) -> dict | None:
    if state.get("current_player_id") != pid or state.get("pending") or state.get("auction"):
        return state.get("pending")

    def finish(pending: dict) -> dict:
        state["pending"] = pending
        return pending

    rng = rng_for(state, f"roll-{pid}")
    steps = rng.randint(1, 6)
    start = state["franchises"][pid]["pos"]
    end = (start + steps) % 52
    state["dice"] = [steps]
    state["franchises"][pid]["pos"] = end
    state["franchises"][pid]["last_action"] = f"Rolled {steps} to tile {end}"

    if end < start:
        state["franchises"][pid]["balance"] += 200
        add_log(state, f"{state['franchises'][pid]['name']} passed Season Start — +200 FC.", "corner")

    tile = data52.BOARD[end]
    add_log(state, f"{state['franchises'][pid]['name']} rolled {steps} → {tile['name']}.", "roll")

    if tile["kind"] == "stadium":
        owner = state.get("ownership", {}).get(str(end))
        if not owner:
            return finish({"type": "buy_stadium", "pid": pid, "pos": end,
                           "price": int(tile.get("price", 250)), "title": tile["name"]})
        if owner == pid:
            income = int(tile.get("match_revenue", 60)) // 2
            state["franchises"][pid]["balance"] += income
            return finish({"type": "result", "pid": pid, "title": "Home ground",
                           "text": f"You own {tile['name']}. Home crowd pays +{income} FC."})
        return finish({"type": "duel", "pid": pid, "defender": owner, "pos": end,
                       "rent": int(tile.get("landing_fee", 50)), "pot": False,
                       "cards": {}, "result": None, "label": f"Rent duel at {tile['name']}"})

    if tile["kind"] == "market":
        offer = market_offer(state, end)
        if not offer:
            return finish({"type": "result", "pid": pid, "title": tile["name"],
                           "text": "No players left in this market."})
        return finish({"type": "sign_player", "pid": pid, **offer, "title": tile["name"]})

    if tile["kind"] == "corner":
        tid = tile.get("id")
        if tid == "season_start":
            state["franchises"][pid]["balance"] += 200
            return finish({"type": "result", "pid": pid, "title": "Season Start",
                           "text": "Season bonus — +200 FC."})
        if tid == "headquarters":
            state["franchises"][pid]["balance"] += 100
            return finish({"type": "result", "pid": pid, "title": "Headquarters",
                           "text": "Sponsorship office — +100 FC."})
        if tid == "matchday":
            defender = next_manager(state, pid)
            return finish({"type": "duel", "pid": pid, "defender": defender, "pos": None,
                           "rent": 100, "pot": True, "cards": {}, "result": None,
                           "label": "Arena showdown"})

    return finish(apply_event(state, pid, tile))


def buy_stadium(state: dict, pid: str, pos: int) -> str:
    pending = state.get("pending") or {}
    if pending.get("type") != "buy_stadium" or pending.get("pid") != pid or pending.get("pos") != pos:
        return "That purchase is no longer available."
    price = int(pending.get("price", 0))
    if state["franchises"][pid]["balance"] < price:
        return "Not enough FC to buy this ground."
    charge(state, pid, price)
    stadium_id = str(data52.BOARD[pos].get("id", pos))
    state["ownership"][str(pos)] = pid
    grounds = state["franchises"][pid].setdefault("stadiums", [])
    if stadium_id not in grounds:
        grounds.append(stadium_id)
    state["pending"] = None
    add_log(state, f"{state['franchises'][pid]['name']} bought {data52.BOARD[pos]['name']} for {price} FC.", "purchase")
    return f"{data52.BOARD[pos]['name']} is yours for {price} FC."


def sign_player(state: dict, pid: str, player_id: str) -> str:
    pending = state.get("pending") or {}
    if pending.get("type") != "sign_player" or pending.get("pid") != pid:
        return "No signing is waiting."
    if player_id not in pending.get("candidates", []):
        return "That player is not on the market tile."
    if player_id in signed_players(state):
        return "That cricketer is already signed."
    if len(state["franchises"][pid].get("squad", [])) >= 15:
        return "Your squad is full (15 players)."
    price = int(pending.get("price", 150))
    if state["franchises"][pid]["balance"] < price:
        return "Not enough FC to sign this cricketer."
    charge(state, pid, price)
    state["franchises"][pid].setdefault("squad", []).append(player_id)
    state["pending"] = None
    name = player_map(state.get("data_overrides")).get(player_id, {}).get("name", player_id)
    add_log(state, f"{state['franchises'][pid]['name']} signed {name} for {price} FC.", "sign")
    return f"{name} joins your squad for {price} FC."


def submit_card(state: dict, pid: str, card: str) -> dict | None:
    pending = state.get("pending") or {}
    if pending.get("type") != "duel" or card not in TACTICS:
        return None
    challenger = pending["pid"]
    defender = pending["defender"]
    if pid not in (challenger, defender):
        return None
    if pid in pending.get("cards", {}):
        return None
    hand = state["franchises"][pid].setdefault("tactics", [])
    if card not in hand:
        return None
    replacement = draw_replacement(hand, rng_for(state, f"hand-{pid}-{len(state.get('log', []))}"))
    hand.remove(card)
    hand.append(replacement)
    pending.setdefault("cards", {})[pid] = card
    add_log(state, f"{state['franchises'][pid]['name']} chose {TACTICS[card]['name']}.", "tactic")
    if len(pending["cards"]) < 2:
        return None
    return resolve_duel(state)


def resolve_duel(state: dict) -> dict:
    pending = state["pending"]
    challenger = pending["pid"]
    defender = pending["defender"]
    cards = pending["cards"]
    pmap = player_map(state.get("data_overrides"))
    pitch = state.get("pitch", "flat")
    home = data52.BOARD[pending["pos"]] if pending.get("pos") is not None else None

    sides: dict[str, dict] = {}
    for pid in (challenger, defender):
        ratings = squad_ratings(state["franchises"][pid].get("squad", []), pmap)
        card = TACTICS[cards[pid]]
        run_mod = int(card.get("run_mod", 0))
        wicket_mod = int(card.get("bowl_mod", 0))
        suppress = 0
        if card.get("pitch") == pitch:
            run_mod += int(card.get("pitch_run", 0))
            wicket_mod += int(card.get("pitch_wicket", 0))
        if pitch == "flat" and card.get("kind") == "bat":
            run_mod += 10
        if pitch == "slow" and card.get("id") == "powerplay":
            run_mod += int(card.get("slow_penalty", -8))
        if pitch == "dry" and card.get("id") == "spin_web":
            suppress = 10
        if pid == defender and home:
            wicket_mod += 2
        sides[pid] = {"ratings": ratings, "card": card, "run_mod": run_mod,
                      "bowl_mod": wicket_mod, "suppress": suppress,
                      "runs": 0, "wickets": 0, "score": 0}

    rng = rng_for(state, f"duel-{challenger}-{defender}")
    for pid in (challenger, defender):
        me = sides[pid]
        foe = sides[defender if pid == challenger else challenger]
        bat_strength = me["ratings"]["bat"] / 4 + me["run_mod"]
        bowl_pressure = foe["ratings"]["bowl"] / 6 + foe["bowl_mod"]
        me["runs"] = max(70, min(250, round(
            112 + bat_strength - bowl_pressure / 2 + rng.randint(-8, 8) - foe["suppress"]
        )))
        me["wickets"] = max(0, min(10, round(
            4 + bowl_pressure / 8 - bat_strength / 12 + me["card"].get("risk", 0) + rng.randint(0, 2)
        )))
        me["score"] = me["runs"] - me["wickets"] * 4

    c, d = sides[challenger], sides[defender]
    winner = challenger if c["score"] > d["score"] else defender
    margin = abs(c["score"] - d["score"])
    rent = int(pending.get("rent", 50))
    if pending.get("pot"):
        multiplier = 1
        paid = rent
    elif winner == challenger:
        multiplier = 0.5
        paid = round(rent * multiplier)
    else:
        multiplier = 1.5 if margin >= 40 else 1
        paid = round(rent * multiplier)

    payer = defender if winner == challenger else challenger
    note, shortfall = charge(state, payer, paid, winner)

    transfer_note = ""
    if shortfall and not pending.get("pot"):
        owned = list(state["franchises"][payer].get("stadiums", []))
        contest = data52.BOARD[pending["pos"]] if pending.get("pos") is not None else None
        stadium_id = contest.get("id") if contest and contest.get("id") in owned else (owned[0] if owned else None)
        if stadium_id:
            tile = next((t for t in data52.BOARD
                         if t.get("kind") == "stadium" and t.get("id") == stadium_id), None)
            if tile:
                state["ownership"][str(tile["position"])] = winner
                state["franchises"][payer]["stadiums"].remove(stadium_id)
                state["franchises"][winner].setdefault("stadiums", []).append(stadium_id)
                transfer_note = (
                    f" {state['franchises'][payer]['name']} had no FC left; "
                    f"{tile['name']} transferred to {state['franchises'][winner]['name']} at 70%."
                )
                add_log(state, transfer_note.strip(), "transfer")
    state["franchises"][winner]["duels_won"] += 1

    scorecard = {
        "challenger": {"id": challenger, "name": state["franchises"][challenger]["name"],
                       "runs": c["runs"], "wickets": c["wickets"], "score": c["score"],
                       "card": TACTICS[cards[challenger]]["name"], "icon": TACTICS[cards[challenger]]["icon"],
                       "run_mod": c["run_mod"], "bowl_mod": c["bowl_mod"]},
        "defender": {"id": defender, "name": state["franchises"][defender]["name"],
                     "runs": d["runs"], "wickets": d["wickets"], "score": d["score"],
                     "card": TACTICS[cards[defender]]["name"], "icon": TACTICS[cards[defender]]["icon"],
                     "run_mod": d["run_mod"], "bowl_mod": d["bowl_mod"]},
    }
    verb = "won" if winner == challenger else "held"
    text = (f"{state['franchises'][winner]['name']} {verb} by {margin} runs. "
            f"{paid} FC settled at {multiplier}× rent.{note}{transfer_note}")
    add_log(state, text, "match")
    state["pending"] = {
        "type": "result", "pid": challenger, "title": pending.get("label", "Match duel"),
        "text": text, "scorecard": scorecard, "pitch": pitch,
        "winner_id": winner, "paid": paid, "multiplier": multiplier,
        "viewers": [challenger, defender],
    }
    return state["pending"]


def place_bid(state: dict, pid: str, amount: int) -> str:
    auction = state.get("auction")
    if not auction or pid in auction.get("passed", []):
        return "No active auction for you."
    base = int(auction.get("base_price", 80))
    if int(amount) < base:
        return f"Bid must be at least {base} FC."
    if state["franchises"][pid]["balance"] < int(amount):
        return "Not enough FC for that bid."
    if len(state["franchises"][pid].get("squad", [])) >= 15:
        return "Your squad is full (15 players)."
    auction.setdefault("bids", {})[pid] = int(amount)
    add_log(state, f"{state['franchises'][pid]['name']} submitted a sealed bid.", "bid")
    return f"Sealed bid of {amount} FC recorded."


def pass_auction(state: dict, pid: str) -> str:
    auction = state.get("auction")
    if not auction:
        return "No active auction."
    if pid not in auction.setdefault("passed", []):
        auction["passed"].append(pid)
    auction.get("bids", {}).pop(pid, None)
    add_log(state, f"{state['franchises'][pid]['name']} passed the auction.", "bid")
    return "You passed."


def resolve_auction(state: dict) -> dict | None:
    auction = state.get("auction")
    if not auction:
        return None
    active = set(state.get("order", []))
    settled = set(auction.get("bids", {})) | set(auction.get("passed", []))
    if active - settled:
        return None
    bids = auction.get("bids") or {}
    auction["revealed"] = True
    state["auction"] = None
    if not bids:
        text = "No bids — the cricketer went unsold."
        add_log(state, text, "auction")
        result = {"type": "result", "pid": auction.get("opened_by"), "title": "Auction", "text": text,
                  "viewers": [auction.get("opened_by")]}
        state["pending"] = result
        return result
    winner = sorted(bids.items(), key=lambda item: (-item[1], state["order"].index(item[0])))[0][0]
    price = int(bids[winner])
    charge(state, winner, price)
    name = player_map(state.get("data_overrides")).get(auction["player_id"], {}).get("name", "the star")
    state["franchises"][winner].setdefault("squad", []).append(auction["player_id"])
    text = f"{state['franchises'][winner]['name']} won {name} for {price} FC."
    add_log(state, text, "auction")
    result = {"type": "result", "pid": auction.get("opened_by", winner), "title": "Auction won", "text": text,
              "viewers": [auction.get("opened_by"), winner]}
    state["pending"] = result
    return result


def advance_turn(state: dict) -> dict:
    if state.get("auction"):
        return state
    state["pending"] = None
    order = state.get("order") or []
    if not order:
        return state
    index = (state.get("turn_index", 0) + 1) % len(order)
    if index == 0:
        end_round(state)
        if state.get("finished"):
            return state
    state["turn_index"] = index
    state["current_player_id"] = order[index]
    return state


def end_round(state: dict) -> None:
    for f in state["franchises"].values():
        f["balance"] += len(f.get("stadiums", [])) * 15
    if state["round"] >= int(state["settings"].get("season_rounds", 8)):
        state["finished"] = True
        state["phase"] = "over"
        table = standings(state)
        state["winner_id"] = table[0]["id"] if table else None
        add_log(state, f"Season complete — {table[0]['name']} wins on Brand Value.", "final")
        return
    state["round"] += 1
    state["pitch"] = PITCH_KEYS[(state["round"] - 1) % len(PITCH_KEYS)]
    add_log(state, f"Round {state['round']} begins. Pitch: {state['pitch'].title()}.", "round")


def _can_acknowledge_result(pending: dict, pid: str) -> bool:
    """Either side of a finished duel or auction may close the scorecard."""
    return pending.get("pid") == pid or pid in (pending.get("viewers") or [])


def skip(state: dict, pid: str) -> str:
    pending = state.get("pending") or {}
    is_result = pending.get("type") == "result"
    if pending.get("pid") != pid and not (is_result and _can_acknowledge_result(pending, pid)):
        return "Wait for the current action to finish."
    if is_result:
        advance_turn(state)
        return "Turn passed."
    add_log(state, f"{state['franchises'][pid]['name']} passed on the offer.", "skip")
    advance_turn(state)
    return "Offer passed."


def next_turn(state: dict, pid: str) -> str:
    if state.get("auction"):
        return "Finish the auction first."
    pending = state.get("pending") or {}
    if not pending:
        return "Wait for the current action to finish."
    if pending.get("pid") != pid and not (
        pending.get("type") == "result" and _can_acknowledge_result(pending, pid)
    ):
        return "Wait for the current action to finish."
    advance_turn(state)
    return "Turn passed."


def bot_action(state: dict, pid: str) -> None:
    """One decision for an automated manager. Safe to call repeatedly in a tick."""
    f = state["franchises"][pid]
    auction = state.get("auction")
    pending = state.get("pending")
    if auction:
        if pid in auction.get("bids", {}) or pid in auction.get("passed", []):
            if set(state["order"]) <= set(auction.get("bids", {})) | set(auction.get("passed", [])):
                resolve_auction(state)
            return
        rng = rng_for(state, f"botbid-{pid}")
        if rng.random() < 0.65 and f["balance"] >= auction["base_price"]:
            place_bid(state, pid, auction["base_price"] + rng.choice([0, 20, 50]))
        else:
            pass_auction(state, pid)
        resolve_auction(state)
        return

    if not pending:
        if state.get("current_player_id") == pid:
            roll(state, pid)
        return

    ptype = pending.get("type")
    if ptype == "result":
        advance_turn(state)
        return
    if ptype == "buy_stadium" and pending.get("pid") == pid:
        if f["balance"] >= pending.get("price", 0):
            buy_stadium(state, pid, pending["pos"])
        else:
            skip(state, pid)
        return
    if ptype == "sign_player" and pending.get("pid") == pid:
        affordable = [p for p in pending.get("candidates", []) if f["balance"] >= pending.get("price", 150)]
        if affordable:
            sign_player(state, pid, affordable[-1])
        else:
            skip(state, pid)
        return
    if ptype == "duel":
        card = None
        if pid == pending.get("pid") and pid not in pending.get("cards", {}):
            card = f["tactics"][0]
        elif pid == pending.get("defender") and pid not in pending.get("cards", {}):
            card = f["tactics"][1 % len(f["tactics"])]
        if card:
            submit_card(state, pid, card)
        elif len(pending.get("cards", {})) < 2:
            for side in (pending.get("pid"), pending.get("defender")):
                if side not in pending["cards"]:
                    submit_card(state, side, state["franchises"][side]["tactics"][0])
                    break
        return
