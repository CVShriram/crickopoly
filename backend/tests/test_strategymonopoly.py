"""Focused tests for Cricket Strategy League (ruleset 8)."""

from __future__ import annotations

import asyncio
import json
import random
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import persistence as db
from app.game import data52, strategymonopoly as tycoon
from app.main import app
from app.tycoon_api import (TycoonRoom, _rows, clean_settings, hub, manager,
                            saved_summaries)


STATE_KEYS = {
    "ruleset", "started", "finished", "phase", "turn", "laps", "order",
    "turn_index", "current_player_id", "dice", "rolled", "pending", "board",
    "properties", "franchises", "contest", "last_contest", "last_event",
    "settings", "data_overrides", "log", "events", "winner_id", "host_id",
}


def lobby(code: str, players: int = 2, settings: dict | None = None,
          bots: bool = False) -> dict:
    members = {}
    for index in range(players):
        pid = f"p{index}"
        members[pid] = {
            "id": pid, "name": f"Manager {index}", "avatar": "🏏",
            "color": "#c8a24b", "is_host": index == 0, "is_bot": bots,
            "difficulty": "medium", "ready": True,
        }
    return {
        "room_id": f"r-{code}", "code": code, "host_id": "p0",
        "created_at": 1.0, "settings": settings or {}, "members": members,
        "data_overrides": {},
    }


def client_without_ticks() -> TestClient:
    """A client whose bot loop is not running; bots are driven explicitly."""
    return TestClient(app)


def tile_position(kind: str, role: str | None = None, min_pos: int = 14) -> int:
    """Find a buyable tile past the first corner so rolls never cross START."""
    for pos, tile in enumerate(data52.BOARD):
        if pos >= min_pos and tile.get("kind") == kind and (
                role is None or tile.get("role") == role):
            return pos
    raise AssertionError("No matching tile")


def place_before(state: dict, target: int) -> None:
    """Set the current player's position so the next deterministic roll lands."""
    for _ in range(24):
        steps = sum(tycoon._dice(state))
        start = (target - steps) % 52
        if start > 0 and start + steps < 52:
            state["franchises"][state["current_player_id"]]["pos"] = start
            return
        state["turn"] = int(state["turn"]) + 1
    raise AssertionError("Could not line up a landing square")


def give_property(state: dict, pid: str, tile_id: str, level: int = 0) -> None:
    prop = state["properties"][tile_id]
    prop["owner"] = pid
    prop["level"] = level
    owned = state["franchises"][pid]["owned"]
    if tile_id not in owned:
        owned.append(tile_id)
    tycoon.recompute_franchise(state, pid)


def open_contest(state: dict, pos: int, visitor: str | None = None,
                 owner: str | None = None, level: int | None = None,
                 allow_resolved: bool = False) -> dict:
    """Land the first manager on the second one's market and open a contest."""
    order = state["order"]
    visitor = visitor or order[0]
    owner = owner or order[1]
    tile = data52.BOARD[pos]
    tile_id = str(tile["id"])
    if state["properties"][tile_id]["owner"] != owner:
        give_property(state, owner, tile_id, level or 0)
    elif level is not None:
        state["properties"][tile_id]["level"] = level
    state["current_player_id"] = visitor
    state["turn_index"] = state["order"].index(visitor)
    state["phase"] = "roll"
    state["pending"] = None
    state["contest"] = None
    state["rolled"] = False
    state["dice"] = None
    place_before(state, pos)
    tycoon.roll(state, visitor)
    if not allow_resolved:
        assert state["contest"] is not None
    return state["contest"] or state["last_contest"]


def expected_ball(state: dict, contest: dict, shot: str, plan: str) -> tuple[int, bool]:
    """Independently compute the published ball formula for assertions."""
    rng = tycoon._contest_rng(state, contest)
    jitter_runs = rng.randint(-3, 3)
    jitter_wk = rng.randint(-3, 3)
    bat = int(contest["visitor_bat"])
    bowl = int(contest["owner_bowl"])
    base = max(0, min(30, 10 + (bat - bowl) // 3))
    match_runs, match_wk = tycoon.MATCHUPS[shot][plan]
    runs = max(0, min(40, base + tycoon.SHOTS[shot]["runs"] + tycoon.PLANS[plan]["runs"]
                      + match_runs + jitter_runs))
    chance = max(1, min(45, 8 + tycoon.SHOTS[shot]["wk"] + tycoon.PLANS[plan]["wk"]
                        + match_wk + jitter_wk))
    return runs, rng.randrange(100) < chance


# ---------------------------------------------------------------------------
# Engine: contract and table
# ---------------------------------------------------------------------------

def test_ruleset_constants_and_exact_state_contract():
    assert tycoon.RULES_VERSION == 8
    assert tycoon.DEFAULT_SETTINGS == {"max_players": 6, "laps": 3, "difficulty": "medium"}
    assert set(tycoon.STATE_KEYS) == STATE_KEYS

    state = tycoon.new_state(lobby("SETUP", 4, {
        "max_players": 99, "laps": 99, "difficulty": "hard", "note": "keep",
    }))
    assert set(state) == STATE_KEYS
    assert state["ruleset"] == 8
    assert state["started"] is True
    assert state["finished"] is False
    assert state["phase"] == "roll"
    assert state["turn"] == 1
    assert state["laps"] == 5
    assert state["order"] == ["p0", "p1", "p2", "p3"]
    assert state["turn_index"] == 0
    assert state["current_player_id"] == "p0"
    assert state["dice"] is None
    assert state["rolled"] is False
    assert state["pending"] is None
    assert state["contest"] is None
    assert state["last_contest"] is None
    assert state["last_event"] is None
    assert state["settings"] == {
        "max_players": 6, "laps": 5, "difficulty": "hard", "note": "keep",
    }
    assert state["host_id"] == "p0"
    assert state["data_overrides"] == {}
    assert state["winner_id"] is None
    assert state["log"] and state["events"]

    assert len(state["board"]) == 52
    expected_props = {
        str(tile["id"]) for tile in data52.BOARD
        if tile["kind"] in ("market", "stadium")
    }
    assert set(state["properties"]) == expected_props
    assert len(state["properties"]) == 40
    for prop in state["properties"].values():
        assert prop == {"owner": None, "level": 0, "price": prop["price"]}
        assert 0 <= prop["level"] <= 4

    for pid, franchise in state["franchises"].items():
        assert set(franchise) == set(tycoon.FRANCHISE_KEYS)
        assert franchise == {
            "id": pid, "name": f"Manager {pid[1:]}", "avatar": "🏏",
            "color": "#c8a24b", "is_bot": False, "pos": 0, "fc": 1500,
            "runs": 0, "wickets": 3, "max_wickets": 3, "laps": 0,
            "squad": [], "skipped": 0, "injured": 0, "owned": [],
            "out": False, "unlocked": False, "home_ground": None,
        }

    original = state["board"][3]["name"]
    state["board"][3]["name"] = "Mutated"
    assert data52.BOARD[3]["name"] == original


def test_standings_sort_runs_then_fc():
    state = tycoon.new_state(lobby("TABLE", 3))
    state["franchises"]["p0"].update(runs=100, fc=250, wickets=1, laps=1)
    state["franchises"]["p1"].update(runs=100, fc=500, wickets=2)
    state["franchises"]["p2"].update(runs=140, fc=10, wickets=3)

    table = tycoon.standings(state)
    assert [row["id"] for row in table] == ["p2", "p1", "p0"]
    assert [row["rank"] for row in table] == [1, 2, 3]
    assert all(set(row) == set(tycoon.STANDING_KEYS) for row in table)
    assert table[0]["runs"] == 140 and table[0]["fc"] == 10


# ---------------------------------------------------------------------------
# Engine: Monopoly board rules
# ---------------------------------------------------------------------------

def test_buy_decline_and_auction_actions():
    state = tycoon.new_state(lobby("BUY", 2))
    pos = tile_position("market", "batsman")
    place_before(state, pos)
    tycoon.roll(state, "p0")

    pending = state["pending"]
    assert pending["type"] == "buy"
    assert pending["pid"] == "p0"
    assert pending["tile_id"] == str(data52.BOARD[pos]["id"])
    assert pending["price"] == data52.BOARD[pos]["price"]
    assert tycoon.buy(state, "p0") == "ok"
    assert state["properties"][pending["tile_id"]]["owner"] == "p0"
    assert state["franchises"]["p0"]["fc"] == 1500 - pending["price"]
    assert state["current_player_id"] == "p1"
    assert state["pending"] is None

    with pytest.raises(ValueError, match="purchase is pending"):
        tycoon.buy(state, "p1")

    state["current_player_id"] = "p0"
    state["turn_index"] = 0
    state["pending"] = {"type": "buy", "pid": "p0", "tile_id": "india_batsman", "price": 150}
    tycoon.decline(state, "p0")
    assert state["pending"] is None
    assert state["current_player_id"] == "p1"

    state["current_player_id"] = "p0"
    state["pending"] = {"type": "auction", "pid": "p0", "price": 180}
    tycoon.auction_buy(state, "p0")
    franchise = state["franchises"]["p0"]
    assert franchise["fc"] == 1500 - pending["price"] - 180
    assert len(franchise["squad"]) == 1
    assert franchise["max_wickets"] == 4 and franchise["wickets"] == 4

    state["current_player_id"] = "p0"
    state["pending"] = {"type": "auction", "pid": "p0", "price": 180}
    tycoon.auction_skip(state, "p0")
    assert state["pending"] is None
    assert len(state["franchises"]["p0"]["squad"]) == 1


def test_unlock_home_ground_and_upgrade_lock():
    state = tycoon.new_state(lobby("UNLOCK", 2))
    stadium = str(data52.BOARD[tile_position("stadium")]["id"])
    with pytest.raises(ValueError, match="Upgrade locked"):
        tycoon.upgrade(state, "p0", "india_batsman")
    assert state["last_event"]["type"] == "locked"

    give_property(state, "p0", "india_batsman")
    give_property(state, "p0", "india_bowler")
    give_property(state, "p0", "india_wicketkeeper")
    assert not state["franchises"]["p0"]["unlocked"]
    give_property(state, "p0", stadium)
    assert state["franchises"]["p0"]["unlocked"] is True
    assert state["franchises"]["p0"]["home_ground"] == stadium

    fc = state["franchises"]["p0"]["fc"]
    tycoon.upgrade(state, "p0", "india_bowler")
    assert state["properties"]["india_bowler"]["level"] == 1
    assert state["franchises"]["p0"]["fc"] == fc - 60
    assert state["current_player_id"] == "p0"


def test_home_ground_rent_and_own_ground_bonus():
    state = tycoon.new_state(lobby("RENT", 2))
    pos = tile_position("stadium")
    tile = data52.BOARD[pos]
    give_property(state, "p1", str(tile["id"]))
    place_before(state, pos)
    tycoon.roll(state, "p0")

    expected = (tile["price"] // 8) * 3 // 2
    assert state["franchises"]["p1"]["fc"] == 1500 + expected
    assert state["franchises"]["p0"]["fc"] == 1500 - expected
    assert "home ground bonus" in state["last_event"]["text"]

    # Hand the ground to p0 so the second landing triggers the own-ground bonus.
    tile_id = str(tile["id"])
    if tile_id in state["franchises"]["p1"]["owned"]:
        state["franchises"]["p1"]["owned"].remove(tile_id)
    give_property(state, "p0", tile_id)
    tycoon.recompute_franchise(state, "p1")

    state["current_player_id"] = "p0"
    state["turn_index"] = 0
    state["pending"] = None
    state["rolled"] = False
    place_before(state, pos)
    tycoon.roll(state, "p0")
    assert state["franchises"]["p0"]["fc"] == 1500 - expected + 100
    assert state["franchises"]["p0"]["runs"] == 50
    assert state["last_event"]["type"] == "home_ground"


def test_trade_offer_accept_and_decline_keep_proposer_turn():
    state = tycoon.new_state(lobby("TRADE", 2))
    give_property(state, "p0", "india_batsman")
    give_property(state, "p1", "india_bowler")

    tycoon.propose_trade(state, "p0", "p1", "india_batsman", "india_bowler")
    assert state["pending"] == {
        "type": "trade", "pid": "p0", "target": "p1",
        "give_tile": "india_batsman", "take_tile": "india_bowler", "price": 0,
    }
    tycoon.accept_trade(state, "p1")
    assert state["properties"]["india_batsman"]["owner"] == "p1"
    assert state["properties"]["india_bowler"]["owner"] == "p0"
    assert state["current_player_id"] == "p0"
    assert state["pending"] is None

    tycoon.propose_trade(state, "p0", "p1", "india_bowler", "india_batsman")
    tycoon.decline_trade(state, "p1")
    assert state["properties"]["india_bowler"]["owner"] == "p0"
    assert state["pending"] is None
    assert state["current_player_id"] == "p0"


# ---------------------------------------------------------------------------
# Engine: contests
# ---------------------------------------------------------------------------

def test_contest_starts_hidden_resolves_and_advances_once():
    state = tycoon.new_state(lobby("BALL", 2))
    pos = tile_position("market", "batsman")
    start_turn = state["turn"]
    contest = open_contest(state, pos)

    assert set(contest) == set(tycoon.CONTEST_KEYS)
    assert state["phase"] == "contest"
    assert state["turn"] == start_turn
    assert state["current_player_id"] == "p0"
    assert contest["tile_id"] == pos
    assert contest["role"] == "batsman"
    assert contest["visitor_shot"] is None and contest["owner_plan"] is None
    assert contest["visitor_bat"] > 0 and contest["owner_bowl"] > 0

    with pytest.raises(ValueError, match="attack, steady or defend"):
        tycoon.set_shot(state, "p0", "boundary")
    with pytest.raises(ValueError, match="Only the owner"):
        tycoon.set_plan(state, "p0", "yorker")

    tycoon.set_shot(state, "p0", "steady")
    assert state["contest"]["visitor_shot"] == "steady"
    assert state["contest"]["owner_plan"] is None
    assert state["phase"] == "contest"
    assert state["last_contest"] is None
    assert state["turn"] == start_turn

    expected_runs, expected_wicket = expected_ball(state, state["contest"], "steady", "length")
    tycoon.set_plan(state, "p1", "length")

    last = state["last_contest"]
    assert set(last) == set(tycoon.LAST_CONTEST_KEYS)
    assert last["shot"] == "steady" and last["plan"] == "length"
    assert last["runs"] == expected_runs
    assert last["wicket"] is expected_wicket
    assert last["visitor"] == "p0" and last["owner"] == "p1"
    assert state["contest"] is None
    assert state["phase"] == "roll"
    assert state["turn"] == start_turn + 1
    assert state["current_player_id"] == "p1"
    assert state["franchises"]["p1"]["runs"] == expected_runs


def test_shot_and_plan_constants_change_ball_math():
    pos = tile_position("market", "batsman")
    results = {}
    for shot, plan in (("attack", "yorker"), ("attack", "spin"), ("defend", "spin")):
        state = tycoon.new_state(lobby(f"MATH-{shot}-{plan}", 2))
        state["phase"] = "contest"
        state["contest"] = {
            "visitor": "p0", "owner": "p1", "tile_id": pos, "role": "batsman",
            "visitor_shot": shot, "owner_plan": plan,
            "visitor_bat": 80, "owner_bowl": 70,
        }
        expected = expected_ball(state, state["contest"], shot, plan)
        tycoon.resolve_contest(state)
        results[(shot, plan)] = (state["last_contest"]["runs"], state["last_contest"]["wicket"])
        assert results[(shot, plan)] == expected

    assert results[("attack", "spin")][0] > results[("attack", "yorker")][0]
    assert results[("attack", "yorker")][0] > results[("defend", "spin")][0]


def test_wicket_transfers_bonus_runs_and_can_eliminate_visitor(monkeypatch):
    monkeypatch.setattr(random.Random, "randrange", lambda self, *args: 0)
    state = tycoon.new_state(lobby("WICKET", 2))
    pos = tile_position("market", "batsman")
    price = state["properties"][str(data52.BOARD[pos]["id"])]["price"]
    state["phase"] = "contest"
    state["contest"] = {
        "visitor": "p0", "owner": "p1", "tile_id": pos, "role": "batsman",
        "visitor_shot": "attack", "owner_plan": "yorker",
        "visitor_bat": 80, "owner_bowl": 70,
    }
    state["franchises"]["p0"]["wickets"] = 1
    tycoon.resolve_contest(state)

    last = state["last_contest"]
    assert last["wicket"] is True
    assert last["extra_runs"] == price // 4
    assert state["franchises"]["p0"]["wickets"] == 0
    assert state["franchises"]["p0"]["out"] is True
    assert state["franchises"]["p1"]["runs"] == last["runs"] + last["extra_runs"]
    # The out visitor is not advanced past: their own next call consumes it.
    assert state["current_player_id"] == "p0"


def test_no_wicket_keeps_wickets_and_runs(monkeypatch):
    def never_wicket(self, *args):
        return 0 if len(args) == 2 else 99

    monkeypatch.setattr(random.Random, "randrange", never_wicket)
    state = tycoon.new_state(lobby("NOWICKET", 2))
    pos = tile_position("market", "batsman")
    state["phase"] = "contest"
    state["contest"] = {
        "visitor": "p0", "owner": "p1", "tile_id": pos, "role": "batsman",
        "visitor_shot": "attack", "owner_plan": "yorker",
        "visitor_bat": 80, "owner_bowl": 70,
    }
    tycoon.resolve_contest(state)
    assert state["last_contest"]["wicket"] is False
    assert state["last_contest"]["extra_runs"] == 0
    assert state["franchises"]["p0"]["wickets"] == 3
    assert state["current_player_id"] == "p1"


def test_wicketkeeper_contest_skips_visitor_next_turn():
    state = tycoon.new_state(lobby("KEEPER", 2))
    pos = tile_position("market", "wicketkeeper")
    start_turn = state["turn"]
    open_contest(state, pos)
    tycoon.set_shot(state, "p0", "steady")
    tycoon.set_plan(state, "p1", "length")

    assert state["last_contest"]["skip"] is True
    assert state["franchises"]["p0"]["skipped"] >= 1
    assert state["phase"] == "roll"
    assert state["current_player_id"] == "p1"
    assert state["turn"] == start_turn + 1
    assert state["rolled"] is False
    assert state["dice"] is None

    # The keeper's turn marker passes on immediately; the skip is consumed
    # only when p0's next turn comes around.
    state["turn_index"] = 0
    state["current_player_id"] = "p0"
    state["pending"] = None
    state["contest"] = None
    state["phase"] = "roll"
    state["rolled"] = False
    tycoon.roll(state, "p0")
    assert state["franchises"]["p0"]["skipped"] == 0
    assert state["current_player_id"] == "p1"
    assert state["turn"] == start_turn + 2
    assert state["rolled"] is False


def test_market_star_and_upgrade_raise_owner_bowl():
    state = tycoon.new_state(lobby("STAR", 2))
    pos = tile_position("market", "bowler")
    tile = data52.BOARD[pos]
    star = tycoon.market_star(state, str(tile["id"]))
    players = data52.merged_players()
    pool = [p for p in players if p["country"] == tile["country"] and p["role"] == tile["role"]]
    assert star["id"] == max(
        pool, key=lambda p: (p["tier"] == "gold", p["overall"], p["bowling"], p["id"]))["id"]
    assert star["tier"] == "gold"

    open_contest(state, pos)
    base_bowl = state["contest"]["owner_bowl"]
    assert base_bowl == min(99, int(star["bowling"]))

    upgraded = tycoon.new_state(lobby("STAR2", 2))
    open_contest(upgraded, pos, level=2)
    assert upgraded["contest"]["owner_bowl"] == min(99, int(star["bowling"]) + 12)
    assert upgraded["contest"]["owner_bowl"] > base_bowl


def test_bot_contest_choices_and_auto_submission():
    state = tycoon.new_state(lobby("BOTBALL", 2, bots=True))
    pos = tile_position("market", "batsman")
    open_contest(state, pos, allow_resolved=True)
    assert state["contest"] is None
    assert state["last_contest"] is not None
    assert state["phase"] == "roll"
    assert state["current_player_id"] == "p1"

    mixed = tycoon.new_state(lobby("MIXED", 2))
    mixed["franchises"]["p1"]["is_bot"] = True
    open_contest(mixed, pos)
    assert mixed["phase"] == "contest"
    assert mixed["contest"]["owner_plan"] in tycoon.PLANS
    assert mixed["contest"]["visitor_shot"] is None
    bot_plan = mixed["contest"]["owner_plan"]
    tycoon.set_shot(mixed, "p0", "attack")
    assert mixed["last_contest"]["plan"] == bot_plan
    assert mixed["last_contest"]["shot"] == "attack"

    choices = tycoon.new_state(lobby("CHOICES", 2))
    choices["phase"] = "contest"
    choices["contest"] = {
        "visitor": "p0", "owner": "p1", "tile_id": pos, "role": "batsman",
        "visitor_shot": None, "owner_plan": None, "visitor_bat": 70, "owner_bowl": 60,
    }
    assert tycoon.bot_contest_choice(choices, "p0") == "steady"
    choices["franchises"]["p0"]["laps"] = 2
    assert tycoon.bot_contest_choice(choices, "p0") == "attack"
    choices["franchises"]["p0"]["wickets"] = 1
    assert tycoon.bot_contest_choice(choices, "p0") == "defend"
    assert tycoon.bot_contest_choice(choices, "p1") in ("yorker", "length", "spin")
    assert tycoon.bot_contest_choice(choices, "p1") == tycoon.bot_contest_choice(choices, "p1")
    choices["franchises"]["p1"]["wickets"] = 1
    assert tycoon.bot_contest_choice(choices, "p1") == "yorker"
    assert tycoon.bot_contest_choice(choices, "outsider") is None


def test_bot_action_handles_pending_offers():
    state = tycoon.new_state(lobby("BOTACTION", 2))
    give_property(state, "p0", "india_batsman", level=1)
    give_property(state, "p1", "india_bowler")

    tycoon.propose_trade(state, "p0", "p1", "india_batsman", "india_bowler")
    tycoon.bot_action(state, "p1")
    assert state["pending"] is None
    assert state["properties"]["india_bowler"]["owner"] == "p0"

    state["current_player_id"] = "p0"
    state["pending"] = {"type": "buy", "pid": "p0", "tile_id": "india_wicketkeeper", "price": 130}
    tycoon.bot_action(state, "p0")
    assert state["properties"]["india_wicketkeeper"]["owner"] == "p0"

    state["current_player_id"] = "p0"
    state["pending"] = {"type": "auction", "pid": "p0", "price": 180}
    tycoon.bot_action(state, "p0")
    assert state["pending"] is None
    assert len(state["franchises"]["p0"]["squad"]) == 1


# ---------------------------------------------------------------------------
# API integration
# ---------------------------------------------------------------------------

def test_rules_settings_and_snapshot_contract():
    client = client_without_ticks()
    rules = client.get("/api/fg/gamedata").json()["rules"]
    assert rules == {
        "ruleset": 8, "laps": 3, "min_players": 2, "max_players": 6,
        "shots": ["attack", "steady", "defend"],
        "plans": ["yorker", "length", "spin"],
    }

    created = client.post("/api/fg/rooms", json={
        "name": "Host",
        "settings": {"max_players": 99, "laps": 99, "difficulty": "hard", "note": "keep"},
    }).json()
    code, host = created["code"], created["player_id"]
    assert created["state"]["settings"]["max_players"] == 6
    assert created["state"]["settings"]["laps"] == 5

    updated = client.post(f"/api/fg/rooms/{code}/settings", json={
        "player_id": host, "settings": {"max_players": 1, "laps": 0},
    }).json()
    assert updated["settings"]["max_players"] == 2
    assert updated["settings"]["laps"] == 2
    assert updated["gamedata"]["rules"]["laps"] == 2

    guest = client.post("/api/fg/rooms/join", json={"code": code, "name": "Guest"}).json()["player_id"]
    client.post(f"/api/fg/rooms/{code}/start", json={"player_id": host})
    room = manager.by_code(code)
    snap = room.snapshot(host)
    assert set(snap) == STATE_KEYS | {"gamedata", "standings", "you"}
    assert snap["ruleset"] == 8
    assert snap["you"] == host
    assert snap["standings"] == tycoon.standings(room.state)
    assert snap["gamedata"]["rules"]["shots"] == list(tycoon.SHOT_IDS)
    assert len(snap["gamedata"]["players"]) == 96
    assert len(snap["board"]) == 52

    with pytest.raises(HTTPException) as exc:
        manager.by_token(code, "not-a-member")
    assert exc.value.status_code == 403
    with client.websocket_connect(f"/api/fg/ws?code={code}&token=not-a-member") as ws:
        message = ws.receive_json()
        assert message["type"] == "error"
        assert "Invalid room link" in message["message"]


def test_dispatch_actions_and_hidden_choices():
    client = client_without_ticks()
    created = client.post("/api/fg/rooms", json={"name": "Host"}).json()
    code, host = created["code"], created["player_id"]
    guest = client.post("/api/fg/rooms/join", json={"code": code, "name": "Guest"}).json()["player_id"]
    client.post(f"/api/fg/rooms/{code}/start", json={"player_id": host})
    room = manager.by_code(code)
    state = room.state

    pos = tile_position("market", "batsman")
    contest_state = open_contest(state, pos)
    assert contest_state is state["contest"]

    with pytest.raises(ValueError, match="attack, steady or defend"):
        hub.dispatch(room, host, "shot", {"shot": "six"})
    with pytest.raises(ValueError, match="yorker, length or spin"):
        hub.dispatch(room, guest, "plan", {"plan": "fulltoss"})

    assert hub.dispatch(room, host, "shot", {"shot": "attack"}) == "ok"
    assert state["contest"]["visitor_shot"] == "attack"
    # The owner cannot see the visitor's shot until both choices are in.
    assert room.snapshot(guest)["contest"]["visitor_shot"] is None
    assert room.snapshot(host)["contest"]["visitor_shot"] == "attack"
    # Snapshot copies never mutate the authoritative contest.
    assert state["contest"]["visitor_shot"] == "attack"

    before_signature = hub._signature(room)
    assert hub.dispatch(room, guest, "plan", {"plan": "spin"}) == "ok"
    assert state["contest"] is None
    assert state["last_contest"]["shot"] == "attack"
    assert state["last_contest"]["plan"] == "spin"
    assert hub._signature(room) != before_signature
    assert room.snapshot(guest)["last_contest"] == state["last_contest"]

    assert hub.dispatch(room, host, "ping", {}) == "pong"
    with pytest.raises(ValueError, match="Unknown action"):
        hub.dispatch(room, host, "bid", {"amount": 10})

    # Other dispatch actions remain available.
    state["current_player_id"] = host
    state["turn_index"] = 0
    state["pending"] = {"type": "auction", "pid": host, "price": 180}
    assert hub.dispatch(room, host, "auction_skip", {}) == "ok"

    state["current_player_id"] = host
    state["turn_index"] = 0
    state["pending"] = {"type": "buy", "pid": host, "tile_id": "india_batsman", "price": 150}
    assert hub.dispatch(room, host, "buy", {}) == "ok"

    give_property(state, host, "india_bowler")
    give_property(state, host, "india_wicketkeeper")
    stadium_id = str(data52.BOARD[tile_position("stadium")]["id"])
    give_property(state, host, stadium_id)
    state["current_player_id"] = host
    state["turn_index"] = 0
    assert hub.dispatch(room, host, "upgrade", {"tile_id": "india_bowler"}) == "ok"
    assert state["properties"]["india_bowler"]["level"] == 1

    overrides = {"players": {"india_batsman_gold": {"batting": 99, "name": "Edited Name"}}}
    assert hub.dispatch(room, host, "admin_update", {"overrides": overrides}) == "Player data updated."
    edited = next(p for p in room.snapshot(host)["gamedata"]["players"]
                  if p["id"] == "india_batsman_gold")
    assert edited["batting"] == 99 and edited["name"] == "Edited Name"


def test_signature_and_auto_room_bot_behaviour():
    client = client_without_ticks()
    created = client.post("/api/fg/rooms", json={"name": "Bot"}).json()
    code, host = created["code"], created["player_id"]
    guest = client.post("/api/fg/rooms/join", json={"code": code, "name": "Other Bot"}).json()["player_id"]
    client.post(f"/api/fg/rooms/{code}/start", json={"player_id": host})
    room = manager.by_code(code)
    state = room.state

    order = state["order"]
    visitor = order[0]
    pos = tile_position("market", "batsman")
    open_contest(state, pos)
    signature = hub._signature(room)
    state["properties"]["india_batsman"]["level"] = 2
    assert hub._signature(room) != signature
    signature = hub._signature(room)
    state["franchises"][visitor]["runs"] += 5
    assert hub._signature(room) != signature

    # A human-vs-human contest is never answered by the bot tick.
    human = tycoon.new_state(lobby("HUMANS", 2))
    hpos = tile_position("market", "batsman")
    open_contest(human, hpos)
    human_room = TycoonRoom("human-tick-room", "HUMAN", "p0")
    human_room.state = human
    before = human["contest"].copy()
    asyncio.run(hub.auto_room(human_room))
    assert human["contest"] == before

    # With bots on both sides the tick resolves the ball and moves the game on.
    for pid in state["order"]:
        state["franchises"][pid]["is_bot"] = True
    state["phase"] = "roll"
    state["contest"] = None
    state["current_player_id"] = visitor
    state["turn_index"] = state["order"].index(visitor)
    state["rolled"] = False
    state["pending"] = None
    place_before(state, pos)
    tycoon.roll(state, visitor)
    assert state["last_contest"] is not None
    assert hub._signature(room) != signature
    assert state["current_player_id"] != visitor

    # Mixed room: the bot owner submits its plan, the human still picks a shot.
    mixed = tycoon.new_state(lobby("MIXBOT", 2))
    mixed["franchises"]["p1"]["is_bot"] = True
    open_contest(mixed, hpos)
    mixed_room = TycoonRoom("mixed-tick-room", "MIXED", "p0")
    mixed_room.state = mixed
    asyncio.run(hub.auto_room(mixed_room))
    assert mixed["contest"] is not None
    assert mixed["contest"]["visitor_shot"] is None
    assert mixed["contest"]["owner_plan"] in tycoon.PLANS


def test_saved_summaries_hide_old_rulesets_and_host_overrides_are_room_local():
    stale = []
    for ruleset in (2, 6, 7):
        room_id = f"old-{ruleset}-{uuid.uuid4().hex[:6]}"
        code = f"OLD{ruleset}{uuid.uuid4().hex[:4].upper()}"
        payload = {"ruleset": ruleset, "room_id": room_id, "code": code,
                   "host_id": "old", "created_at": 1.0,
                   "state": {"ruleset": ruleset, "franchises": {}}}
        with db._lock:
            with db._connection() as conn:
                conn.execute(db._sql("""
                    INSERT INTO franchise_rooms(room_id, code, host_id, created_at, updated_at, state_json)
                    VALUES(?,?,?,?,?,?)
                    ON CONFLICT(room_id) DO UPDATE SET state_json=excluded.state_json
                """), (room_id, code, "old", 1.0, 1.0, json.dumps(payload)))
        stale.append(room_id)
    assert all(row.get("room_id") not in stale for row in _rows())
    assert all(row["room_id"] not in stale for row in saved_summaries())

    client = client_without_ticks()
    created = client.post("/api/fg/rooms", json={"name": "Host"}).json()
    code, host = created["code"], created["player_id"]
    guest = client.post("/api/fg/rooms/join", json={"code": code, "name": "Guest"}).json()["player_id"]
    client.post(f"/api/fg/rooms/{code}/start", json={"player_id": host})
    room = manager.by_code(code)

    response = client.post(f"/api/fg/rooms/{code}/data", json={
        "player_id": host,
        "overrides": {"players": {"india_batsman_gold": {"batting": 99, "name": "Edited Name"}}},
    })
    assert response.status_code == 200
    edited = next(p for p in response.json()["gamedata"]["players"]
                  if p["id"] == "india_batsman_gold")
    assert edited["batting"] == 99 and edited["name"] == "Edited Name"
    assert room.state["data_overrides"]["players"]["india_batsman_gold"]["batting"] == 99
    pristine = next(p for p in client.get("/api/fg/gamedata").json()["players"]
                    if p["id"] == "india_batsman_gold")
    assert pristine["name"] != "Edited Name"
    assert client.post(f"/api/fg/rooms/{code}/data", json={
        "player_id": guest, "overrides": {},
    }).status_code == 403

    summary = next(row for row in saved_summaries() if row["code"] == code)
    assert summary["turn"] == room.state["turn"]
    assert summary["finished"] is False

    restarted = client.post(f"/api/fg/rooms/{code}/start", json={"player_id": host})
    assert restarted.status_code == 200
    room = manager.by_code(code)
    assert room.state["turn"] == 1
    assert room.state["ruleset"] == 8


def test_clean_settings_clamps_only_published_fields():
    assert clean_settings(None) == {"max_players": 6, "laps": 3, "difficulty": "medium"}
    assert clean_settings({
        "max_players": 99, "laps": 0, "difficulty": "hard", "note": "keep",
    }) == {
        "max_players": 6, "laps": 2, "difficulty": "hard", "note": "keep",
    }
    assert clean_settings({"max_players": "x", "laps": []}) == {
        "max_players": 6, "laps": 3, "difficulty": "medium",
    }


def test_lap_and_last_manager_finish_the_game():
    state = tycoon.new_state(lobby("FINISH", 2, {"laps": 2}))
    state["franchises"]["p0"]["laps"] = 2
    state["franchises"]["p0"]["runs"] = 220
    state["franchises"]["p1"]["runs"] = 100
    # Force the next roll past START so the completed lap is credited.
    steps = sum(tycoon._dice(state))
    state["franchises"]["p0"]["pos"] = 52 - steps + 1
    tycoon.roll(state, "p0")
    assert state["finished"] is True
    assert state["phase"] == "over"
    assert state["winner_id"] == "p0"
    assert state["last_event"]["type"] == "finish"
    with pytest.raises(ValueError, match="complete"):
        tycoon.roll(state, "p1")
