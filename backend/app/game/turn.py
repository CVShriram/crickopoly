"""Turn, board movement and tile-action resolution.

The board is authoritative on the server. Clients send intents (roll, buy,
skip); this module validates and mutates state. Movement is always clockwise
via two dice. Passing SEASON START pays the landing/pass income.
"""

from __future__ import annotations

import random
import time

from . import auction, conditions, squad
from . import franchise_economy as economy
from .data52 import (BOARD, COUNTRIES, EVENTS, RULES, SPONSORS, STADIUMS,
                     STADIUM_UPGRADES)

START_POS = 0


def charge_fee(state, pid: str, amount: int, kind: str, desc: str) -> int:
    """Charge a landing fee without ever forcing a negative balance.

    In Standard mode an asset is liquidated (same rules as Classic settlement)
    when needed; if the franchise has nothing left the fee is waived. This
    keeps the economy sane while still making fees matter strategically.
    """
    if amount <= 0:
        return 0
    f = state.franchises[pid]
    if economy.balance(state, pid) < amount:
        economy.settlement(state, pid, amount - economy.balance(state, pid), "Fee settlement")
    if economy.balance(state, pid) < amount:
        return 0
    economy.debit(state, pid, amount, kind, desc)
    return amount


def roll_dice(state, pid: str, seed: int | None = None) -> dict:
    """Roll two dice for the current franchise and move clockwise."""
    if state.pending or state.auction:
        raise ValueError("Resolve the current action first")
    if pid != state.current_player_id:
        raise ValueError("Not your turn")
    rng = random.Random(seed if seed is not None else
                        (int(time.time() * 1000) ^ hash(pid) ^ (state.round * 7919)))
    d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
    f = state.franchises[pid]
    old = f["pos"]
    steps = d1 + d2
    new = (old + steps) % len(BOARD)
    f["dice"] = [d1, d2]
    state.dice = [d1, d2]
    passed_start = new < old or old + steps >= len(BOARD)
    f["pos"] = new
    # Season-start salary for passing or landing.
    if passed_start or new == START_POS:
        economy.credit(state, pid, RULES["season_start_income"], "season_income",
                       "Passed SEASON START — season grant")

    tile = BOARD[new]
    result = {
        "pid": pid, "from": old, "to": new, "dice": [d1, d2],
        "doubles": d1 == d2, "tile": tile, "passed_start": passed_start,
    }
    if d1 == d2:
        state.doubles_count += 1
    else:
        state.doubles_count = 0

    kind = tile["kind"]
    if kind == "market":
        owner = state.ownership.get(str(new))
        if owner and owner != pid:
            fee = max(10, tile.get("price", 100) // 8)
            paid = charge_fee(state, pid, fee, "rent",
                              f"Market fee to {state.franchises[owner]['name']} ({tile['name']})")
            if paid:
                economy.credit(state, owner, paid, "rent",
                               f"Market rent from {f['name']} ({tile['name']})")
            result["fee"] = paid
            result["action"] = "rent"
            result["fee"] = fee
        elif not owner:
            result["action"] = "buy_market"
            state.pending = {"type": "purchase", "kind": "market", "pos": new, "pid": pid}
    elif kind == "stadium":
        owner = state.ownership.get(str(new))
        if owner and owner != pid:
            fee = tile.get("landing_fee", 40)
            paid = charge_fee(state, pid, fee, "venue_fee",
                              f"Venue fee at {tile['name']}")
            if paid:
                economy.credit(state, owner, paid, "venue_fee",
                               f"Venue revenue from {f['name']}")
            result["action"] = "venue_fee"
            result["fee"] = paid
        elif not owner:
            result["action"] = "buy_stadium"
            state.pending = {"type": "purchase", "kind": "stadium", "pos": new, "pid": pid}
    elif kind == "event":
        result["action"] = "event"
        result["event"] = resolve_event(state, pid, tile["id"])
    elif kind == "corner":
        result["action"] = "corner"
        result["event"] = resolve_corner(state, pid, tile["id"])
    return result


def resolve_event(state, pid: str, event_id: str) -> dict:
    """Apply a meaningful state mutation for every special event tile."""
    result = _resolve_event(state, pid, event_id)
    state.events.append({
        "type": "tile_event", "round": state.round,
        "payload": {"franchise_id": pid, "event": event_id, "result": result},
    })
    return result


def _resolve_event(state, pid: str, event_id: str) -> dict:
    """Internal event resolution; always returns a structured result."""
    f = state.franchises[pid]
    if event_id == "mega_auction":
        pool = [p["id"] for p in __import__("app.game.data52", fromlist=["PLAYERS"]).PLAYERS
                if p["tier"] == "gold" and not any(p["id"] in fr["squad"] for fr in state.franchises.values())][:4]
        if pool:
            auction.create_auction(state, "mega", pool, pid)
            return {"type": "mega_auction", "players": pool, "opened": True}
        return {"type": "mega_auction", "opened": False, "reason": "No free stars"}
    if event_id == "matchday_arena":
        state.pending = {"type": "matchday", "initiator": pid}
        return {"type": "matchday_arena", "opened": True}
    if event_id == "injury_reserve":
        injured = [p for p in f["squad"] if f["conditions"].get(p, {}).get("injury")]
        if injured:
            c = conditions.rehabilitate(state, pid, injured[0])
            return {"type": "injury_reserve", "player": injured[0], "healed": True}
        fatigued = max(f["squad"], key=lambda p: f["conditions"].get(p, {}).get("fatigue", 0), default=None)
        if fatigued:
            conditions.rest_player(state, pid, fatigued)
            return {"type": "injury_reserve", "player": fatigued, "rested": True}
        return {"type": "injury_reserve", "nothing": True}
    if event_id == "training_camp":
        free = [p for p in f["squad"] if p not in f["xi"]][:1] or list(f["squad"])[:1]
        if free:
            out = conditions.train(state, pid, free[0], "specialist")
            return {"type": "training_camp", **out}
        return {"type": "training_camp", "nothing": True}
    if event_id == "sponsorship_deal":
        available = [s for s in SPONSORS if s["id"] not in f["sponsors"]]
        if available:
            sponsor = available[0]
            f["sponsors"].append(sponsor["id"])
            economy.credit(state, pid, sponsor["per_round"] * 2, "sponsorship",
                           f"Signed {sponsor['name']} (2-round advance)")
            return {"type": "sponsorship_deal", "sponsor": sponsor["id"], "per_round": sponsor["per_round"]}
        # All signed: payout instead.
        income = sum(s["per_round"] for s in SPONSORS if s["id"] in f["sponsors"])
        economy.credit(state, pid, income, "sponsorship", "Sponsorship renewal")
        return {"type": "sponsorship_deal", "renewal": True, "amount": income}
    if event_id == "championship_qualifier":
        f["record"]["bonus"] += 2
        f["reputation"] += 2
        economy.credit(state, pid, 40, "bonus", "Championship Qualifier bonus")
        return {"type": "championship_qualifier", "points": 2}
    if event_id == "strategy_room":
        card = f"tactical_{len(f['cards']) % 6 + 1}"
        f["cards"].append(card)
        return {"type": "strategy_room", "card": card}
    if event_id == "recovery_camp":
        conditions.recover(state, pid, 22)
        return {"type": "recovery_camp", "fatigue_reduced": 22}
    return {"type": event_id, "unknown": True}


def resolve_corner(state, pid: str, corner_id: str) -> dict:
    f = state.franchises[pid]
    if corner_id == "season_start":
        return {"type": "season_start", "paid": RULES["season_start_income"]}
    if corner_id == "headquarters":
        ok, errors = squad.auto_xi(state, pid)
        return {"type": "headquarters", "auto_xi": ok, "errors": errors}
    if corner_id == "matchday":
        state.pending = {"type": "matchday", "initiator": pid}
        return {"type": "matchday_arena", "opened": True}
    if corner_id == "injury_reserve":
        conditions.recover(state, pid, 15)
        return {"type": "injury_reserve", "recovered": 15}
    return {"type": corner_id}


def buy_market(state, pid: str, pos: int) -> dict:
    tile = BOARD[pos]
    if tile.get("kind") != "market" or pos != state.franchises[pid]["pos"]:
        raise ValueError("Not on a purchasable market tile")
    if str(pos) in state.ownership:
        raise ValueError("Market already owned")
    price = tile["price"]
    economy.debit(state, pid, price, "market_purchase", f"Purchased {tile['name']}")
    state.ownership[str(pos)] = pid
    state.franchises[pid]["markets"].append(pos)
    state.pending = None
    # Country collection reward is granted when all four roles are owned.
    country = tile["country"]
    owned = [t for t in state.franchises[pid]["markets"]
             if BOARD[t].get("country") == country]
    reward = None
    if len(owned) == 4:
        reward = {"country": country, "name": COUNTRIES[country]["name"]}
        economy.credit(state, pid, 120, "collection", f"Completed {reward['name']} collection")
        state.franchises[pid]["reputation"] += 3
        reward["bonus"] = 120
    return {"pos": pos, "price": price, "collection": reward}


def buy_stadium(state, pid: str, pos: int) -> dict:
    tile = BOARD[pos]
    if tile.get("kind") != "stadium" or pos != state.franchises[pid]["pos"]:
        raise ValueError("Not on a purchasable stadium tile")
    if str(pos) in state.ownership:
        raise ValueError("Stadium already owned")
    price = tile["price"]
    economy.debit(state, pid, price, "stadium_purchase", f"Purchased {tile['name']}")
    state.ownership[str(pos)] = pid
    state.franchises[pid]["stadiums"][str(pos)] = []
    state.pending = None
    return {"pos": pos, "price": price, "stadium": tile["id"]}


def skip_purchase(state, pid: str) -> dict:
    if state.pending:
        state.pending = None
    return {"skipped": True}


def upgrade_stadium(state, pid: str, pos: int, upgrade: str) -> dict:
    if upgrade not in STADIUM_UPGRADES:
        raise ValueError("Unknown stadium upgrade")
    f = state.franchises[pid]
    if str(pos) not in f["stadiums"]:
        raise ValueError("You do not own this stadium")
    if upgrade in f["stadiums"][str(pos)]:
        raise ValueError("Upgrade already installed")
    spec = STADIUM_UPGRADES[upgrade]
    economy.debit(state, pid, spec["cost"], "stadium_upgrade",
                  f"{spec['name']} at {BOARD[pos]['name']}")
    f["stadiums"][str(pos)].append(upgrade)
    return {"pos": pos, "upgrade": upgrade, "cost": spec["cost"]}


def next_turn(state) -> None:
    """Advance the turn; every full circle increments the round."""
    state.turn_index += 1
    if state.turn_index % max(1, len(state.order)) == 0:
        state.round += 1
        pay_round_income(state)
        from .tournament import check_classic_survival
        if state.mode == "classic":
            survivor = check_classic_survival(state)
            if survivor:
                from .tournament import champion
                champion(state, survivor)


def pay_round_income(state) -> None:
    for fid, f in state.franchises.items():
        income = 0
        for sid in f["sponsors"]:
            sponsor = next((s for s in SPONSORS if s["id"] == sid), None)
            if sponsor:
                income += sponsor["per_round"]
        if income:
            economy.credit(state, fid, income, "sponsorship", "Round sponsorship income")
        # Stadium match revenue from owned venues.
        for pos in f["stadiums"]:
            tile = BOARD[int(pos)]
            rev = tile.get("match_revenue", 0)
            if "pavilion" in f["stadiums"][pos]:
                rev = int(rev * 1.3)
            economy.credit(state, fid, rev, "venue_revenue",
                           f"Match revenue from {tile['name']}")
