"""Focused tests for Cricket Monopoly (ruleset 5)."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.game import data52, cricketmonopoly as tycoon
from app.main import app
from app.tycoon_api import _rows, _save, hub, manager, saved_summaries


def lobby(code: str, players: int = 2, settings: dict | None = None) -> dict:
    members = {}
    for index in range(players):
        pid = f"p{index}"
        members[pid] = {
            "id": pid, "name": f"Manager {index}", "avatar": "🏏",
            "color": "#c8a24b", "is_host": index == 0, "is_bot": False,
            "difficulty": "medium", "ready": True,
        }
    return {
        "room_id": f"r-{code}", "code": code, "host_id": f"h-{code}",
        "created_at": 1.0, "settings": settings or {}, "members": members,
        "data_overrides": {},
    }


def new_client() -> TestClient:
    """A client without the background tick loop; bots are driven explicitly."""
    return TestClient(app)


def tile_pos(state: dict, tile_id: str) -> int:
    return next(int(t["position"]) for t in state["board"] if t["id"] == tile_id)


def dice_total(state: dict) -> int:
    return sum(tycoon._dice(state))


def place_before(state: dict, pid: str, tile_id: str) -> int:
    """Set a manager's position so the next deterministic roll lands on tile_id."""
    target = tile_pos(state, tile_id)
    for turn in range(1, 200):
        state["turn"] = turn
        total = dice_total(state)
        if 0 < target - total:
            state["franchises"][pid]["pos"] = target - total
            return total
    raise AssertionError(f"No safe approach to {tile_id}")


def set_owner(state: dict, tile_id: str, pid: str, level: int = 0) -> None:
    prop = state["properties"][tile_id]
    prop["owner"] = pid
    prop["level"] = level
    owned = state["franchises"][pid]["owned"]
    if tile_id not in owned:
        owned.append(tile_id)


# ---------------------------------------------------------------------------
# Engine: setup, board and table
# ---------------------------------------------------------------------------

def test_rules_constants_setup_and_board_size():
    assert tycoon.RULES_VERSION == 5
    assert tycoon.DEFAULT_SETTINGS == {
        "max_players": 6, "laps": 3, "difficulty": "medium",
    }
    state = tycoon.new_state(lobby("SETUP", 4, {
        "max_players": 99, "laps": 99, "difficulty": "hard",
    }))
    assert set(state) == set(tycoon.STATE_KEYS)
    assert state["settings"] == {"max_players": 6, "laps": 5, "difficulty": "hard"}
    assert state["laps"] == 5
    assert state["ruleset"] == 5
    assert state["started"] is True
    assert state["finished"] is False
    assert state["phase"] == "play"
    assert state["turn"] == 1
    assert state["turn_index"] == 0
    assert state["order"] == ["p0", "p1", "p2", "p3"]
    assert state["current_player_id"] == "p0"
    assert state["dice"] is None and state["rolled"] is False
    assert state["pending"] is None and state["last_event"] is None
    assert state["winner_id"] is None
    assert state["host_id"] == "h-SETUP"

    assert len(state["board"]) == 52
    assert len(data52.BOARD) == 52
    buyables = [t for t in state["board"] if t["kind"] in ("market", "stadium")]
    assert len(buyables) == 40
    assert set(state["properties"]) == {t["id"] for t in buyables}
    for tile in buyables:
        assert state["properties"][tile["id"]] == {
            "owner": None, "level": 0, "price": tile["price"],
        }
    roles = {t.get("role") for t in state["board"] if t["kind"] == "market"}
    assert {"batsman", "bowler", "wicketkeeper", "allrounder"} <= roles

    for pid, franchise in state["franchises"].items():
        assert set(franchise) == set(tycoon.FRANCHISE_KEYS)
        assert franchise == {
            "id": pid, "name": f"Manager {pid[1:]}", "avatar": "🏏",
            "color": "#c8a24b", "is_bot": False, "pos": 0, "fc": 1500,
            "runs": 0, "wickets": 3, "max_wickets": 3, "laps": 0,
            "squad": [], "skipped": 0, "injured": 0, "owned": [], "out": False,
        }

    # The board in state is a deep copy; a consumer cannot corrupt static data.
    state["board"][0]["name"] = "Mutated"
    assert data52.BOARD[0]["name"] != "Mutated"


def test_standings_sort_by_runs_then_fc():
    state = tycoon.new_state(lobby("TABLE", 3))
    state["franchises"]["p0"].update(runs=100, fc=100)
    state["franchises"]["p1"].update(runs=100, fc=200)
    state["franchises"]["p2"].update(runs=90, fc=999)
    table = tycoon.standings(state)
    assert [row["id"] for row in table] == ["p1", "p0", "p2"]
    assert [row["rank"] for row in table] == [1, 2, 3]
    for row in table:
        assert set(row) == set(tycoon.STANDING_KEYS)


# ---------------------------------------------------------------------------
# Engine: buying, charges and special tiles
# ---------------------------------------------------------------------------

def test_buy_property_and_decline_pass_the_turn():
    state = tycoon.new_state(lobby("BUY", 2))
    p0, p1 = state["order"]
    tile_id = "south_africa_batsman"
    price = state["properties"][tile_id]["price"]
    place_before(state, p0, tile_id)

    tycoon.roll(state, p0)
    assert state["pending"] == {
        "type": "buy", "pid": p0, "tile_id": tile_id, "price": price,
    }
    assert state["current_player_id"] == p0
    assert state["franchises"][p0]["fc"] == 1500

    tycoon.buy(state, p0)
    assert state["franchises"][p0]["fc"] == 1500 - price
    assert state["properties"][tile_id]["owner"] == p0
    assert state["franchises"][p0]["owned"] == [tile_id]
    assert state["pending"] is None
    assert state["current_player_id"] == p1
    assert state["last_event"]["type"] == "buy"

    other_tile = "south_africa_bowler"
    place_before(state, p1, other_tile)
    tycoon.roll(state, p1)
    assert state["pending"]["type"] == "buy"
    assert state["pending"]["pid"] == p1
    fc = state["franchises"][p1]["fc"]
    tycoon.decline(state, p1)
    assert state["pending"] is None
    assert state["franchises"][p1]["fc"] == fc
    assert state["properties"][other_tile]["owner"] is None
    assert state["current_player_id"] == p0


def test_wicketkeeper_transfer_and_skipped_turn():
    state = tycoon.new_state(lobby("WK", 2))
    p0, p1 = state["order"]
    tile_id = "south_africa_wicketkeeper"
    place_before(state, p0, tile_id)
    set_owner(state, tile_id, p1, level=2)
    price = state["properties"][tile_id]["price"]
    due = 40 + price // 5 + 2 * 10
    visitor = state["franchises"][p0]
    owner = state["franchises"][p1]
    visitor.update(runs=500, fc=500)
    owner["runs"] = 0

    tycoon.roll(state, p0)
    assert visitor["runs"] == 500 - due
    assert visitor["fc"] == 500
    assert owner["runs"] == due
    assert visitor["skipped"] == 1
    assert state["current_player_id"] == p1

    tycoon.advance_turn(state)  # hand the marker back for the skipped manager
    assert state["current_player_id"] == p0
    landed_at = visitor["pos"]
    tycoon.roll(state, p0)
    assert visitor["skipped"] == 0
    assert visitor["pos"] == landed_at
    assert state["dice"] is None
    assert state["current_player_id"] == p1


@pytest.mark.parametrize("level", [0, 2, 4])
def test_batsman_charge_decreases_with_upgrade(level: int):
    state = tycoon.new_state(lobby(f"BAT{level}", 2))
    p0, p1 = state["order"]
    tile_id = "south_africa_batsman"
    place_before(state, p0, tile_id)
    set_owner(state, tile_id, p1, level=level)
    state["franchises"][p0]["runs"] = 500
    state["franchises"][p1]["runs"] = 0

    tycoon.roll(state, p0)
    due = max(15, 90 - level * 18)
    assert state["franchises"][p1]["runs"] == due
    assert state["franchises"][p0]["runs"] == 500 - due
    assert state["franchises"][p0]["skipped"] == 0


@pytest.mark.parametrize("level", [3, 4])
def test_bowler_charge_runs_fc_and_maxed_wicket_bonus(level: int):
    state = tycoon.new_state(lobby(f"BOWL{level}", 2))
    p0, p1 = state["order"]
    tile_id = "south_africa_bowler"
    place_before(state, p0, tile_id)
    set_owner(state, tile_id, p1, level=level)
    visitor = state["franchises"][p0]
    owner = state["franchises"][p1]
    visitor.update(runs=500, fc=500, wickets=3)
    owner.update(runs=0, fc=0)

    tycoon.roll(state, p0)
    due_runs = 30 + level * 5
    due_fc = 20 + level * 10
    expected_fc = due_fc
    if level >= 4:
        batsman_price = state["properties"]["south_africa_batsman"]["price"]
        expected_fc += batsman_price // 2
    assert owner["runs"] == due_runs
    assert owner["fc"] == expected_fc
    assert visitor["runs"] == 500 - due_runs
    assert visitor["fc"] == 500 - due_fc
    assert visitor["wickets"] == (2 if level >= 4 else 3)


def test_short_payment_costs_a_wicket_and_ends_the_game():
    state = tycoon.new_state(lobby("SHORT", 2))
    p0, p1 = state["order"]
    tile_id = "south_africa_batsman"
    place_before(state, p0, tile_id)
    set_owner(state, tile_id, p1)
    state["franchises"][p0].update(runs=10, fc=0, wickets=1)
    state["franchises"][p1].update(runs=0, fc=0)

    tycoon.roll(state, p0)
    visitor = state["franchises"][p0]
    owner = state["franchises"][p1]
    assert owner["runs"] == 10  # clamped to what the visitor had
    assert owner["fc"] == 0
    assert visitor["wickets"] == 0
    assert visitor["out"] is True
    assert state["finished"] is True
    assert state["phase"] == "over"
    assert state["winner_id"] == p1
    assert state["last_event"]["type"] == "finish"


def test_iconic_allrounder_charges_from_the_dice():
    state = tycoon.new_state(lobby("ICON", 2))
    p0, p1 = state["order"]
    tile_id = "south_africa_allrounder"
    total = place_before(state, p0, tile_id)
    set_owner(state, tile_id, p1)
    state["franchises"][p0].update(runs=500, fc=500)
    state["franchises"][p1].update(runs=0, fc=0)

    tycoon.roll(state, p0)
    assert state["franchises"][p1]["runs"] == total * 2
    assert state["franchises"][p1]["fc"] == total * 8
    assert state["franchises"][p0]["runs"] == 500 - total * 2
    assert state["franchises"][p0]["fc"] == 500 - total * 8


def test_player_auction_signs_a_real_player_and_adds_a_wicket():
    state = tycoon.new_state(lobby("AUCT", 2))
    p0, p1 = state["order"]
    place_before(state, p0, "mega_auction")
    tycoon.roll(state, p0)
    assert state["pending"] == {"type": "auction", "pid": p0, "price": 180}
    assert state["current_player_id"] == p0

    franchise = state["franchises"][p0]
    franchise["fc"] = 10
    with pytest.raises(ValueError, match="Not enough FC"):
        tycoon.auction_buy(state, p0)
    assert state["pending"]["type"] == "auction"

    franchise["fc"] = 200
    expected = data52.merged_players()[0]["id"]
    tycoon.auction_buy(state, p0)
    assert franchise["fc"] == 20
    assert franchise["squad"] == [expected]
    assert franchise["max_wickets"] == 4
    assert franchise["wickets"] == 4
    assert state["pending"] is None
    assert state["current_player_id"] == p1
    assert "signed" in state["last_event"]["text"]


def test_player_auction_can_be_skipped():
    state = tycoon.new_state(lobby("SKIPA", 2))
    p0, p1 = state["order"]
    place_before(state, p0, "mega_auction")
    tycoon.roll(state, p0)
    fc = state["franchises"][p0]["fc"]
    tycoon.auction_skip(state, p0)
    assert state["pending"] is None
    assert state["franchises"][p0]["fc"] == fc
    assert state["franchises"][p0]["squad"] == []
    assert state["franchises"][p0]["wickets"] == 3
    assert state["current_player_id"] == p1


def test_injury_reserve_skips_two_turns():
    state = tycoon.new_state(lobby("INJ", 2))
    p0, _ = state["order"]
    place_before(state, p0, "injury_reserve")
    tycoon.roll(state, p0)
    franchise = state["franchises"][p0]
    assert franchise["pos"] == 39
    assert franchise["injured"] == 2
    assert state["current_player_id"] == "p1"

    tycoon.advance_turn(state)
    tycoon.roll(state, p0)
    assert franchise["injured"] == 1
    assert franchise["pos"] == 39

    tycoon.advance_turn(state)  # the rival's turn
    tycoon.roll(state, p0)
    assert franchise["injured"] == 0
    assert franchise["pos"] == 39

    tycoon.advance_turn(state)
    franchise["pos"] = 20  # avoid a lap for this final movement check
    tycoon.roll(state, p0)
    assert franchise["pos"] != 20


@pytest.mark.parametrize("tile_id,field,delta", [
    ("sponsorship_deal", "fc", 100),
    ("championship_qualifier", "runs", 50),
    ("training_camp", "fc", -50),
    ("matchday_arena", "runs", 40),
    ("strategy_room", "runs", 30),
    ("recovery_camp", "runs", 30),
])
def test_simple_event_tiles(tile_id: str, field: str, delta: int):
    state = tycoon.new_state(lobby(f"EV{tile_id}", 2))
    p0, p1 = state["order"]
    place_before(state, p0, tile_id)
    before = state["franchises"][p0][field]
    tycoon.roll(state, p0)
    assert state["franchises"][p0][field] == before + delta
    assert state["current_player_id"] == p1


def test_stadium_charges_clamped_fc_rent():
    state = tycoon.new_state(lobby("STAD", 2))
    p0, p1 = state["order"]
    tile_id = "newlands"
    place_before(state, p0, tile_id)
    set_owner(state, tile_id, p1, level=1)
    price = state["properties"][tile_id]["price"]
    state["franchises"][p0]["fc"] = 500
    state["franchises"][p1]["fc"] = 0
    tycoon.roll(state, p0)
    assert state["franchises"][p1]["fc"] == price // 8 + 20
    assert state["franchises"][p0]["fc"] == 500 - (price // 8 + 20)


# ---------------------------------------------------------------------------
# Engine: upgrading, laps and bots
# ---------------------------------------------------------------------------

def test_upgrade_requires_ownership_budget_and_keeps_the_turn():
    state = tycoon.new_state(lobby("UPG", 2))
    p0, p1 = state["order"]
    tile_id = "south_africa_batsman"
    set_owner(state, tile_id, p0)
    turn, current = state["turn"], state["current_player_id"]

    tycoon.upgrade(state, p0, tile_id)
    assert state["properties"][tile_id]["level"] == 1
    assert state["franchises"][p0]["fc"] == 1500 - 60
    assert state["turn"] == turn
    assert state["current_player_id"] == current
    assert state["rolled"] is False and state["dice"] is None

    state["current_player_id"] = p1
    with pytest.raises(ValueError, match="own"):
        tycoon.upgrade(state, p1, tile_id)
    state["current_player_id"] = p0
    with pytest.raises(ValueError, match="Unknown"):
        tycoon.upgrade(state, p0, "not_a_tile")

    state["properties"][tile_id]["level"] = 4
    with pytest.raises(ValueError, match="fully upgraded"):
        tycoon.upgrade(state, p0, tile_id)

    state["properties"][tile_id]["level"] = 0
    state["franchises"][p0]["fc"] = 10
    with pytest.raises(ValueError, match="Not enough FC"):
        tycoon.upgrade(state, p0, tile_id)


def test_lap_credit_and_lap_finish_pick_highest_runs():
    state = tycoon.new_state(lobby("LAP", 2))
    p0, _ = state["order"]
    leader = state["franchises"][p0]
    leader.update(pos=50, laps=2, runs=100, fc=200)
    state["franchises"]["p1"].update(runs=50)

    tycoon.roll(state, p0)
    assert state["finished"] is True
    assert state["phase"] == "over"
    assert state["winner_id"] == p0  # runs first, FC only as a tiebreak
    assert leader["laps"] == 3
    assert leader["runs"] == 200
    assert leader["fc"] == 300
    assert state["last_event"]["type"] == "finish"
    assert any(entry["kind"] == "final" for entry in state["log"])
    with pytest.raises(ValueError, match="complete"):
        tycoon.roll(state, p0)

    fresh = tycoon.new_state(lobby("LAP2", 2))
    p0, p1 = fresh["order"]
    fresh["franchises"][p0]["pos"] = 50
    tycoon.roll(fresh, p0)
    assert fresh["finished"] is False
    assert fresh["franchises"][p0]["laps"] == 1
    assert fresh["franchises"][p0]["runs"] == 100
    assert fresh["franchises"][p0]["fc"] == 1600
    assert fresh["current_player_id"] == p1


def test_bot_action_resolves_pending_and_status_without_looping():
    state = tycoon.new_state(lobby("BOT", 2))
    p0, p1 = state["order"]
    state["franchises"][p0]["is_bot"] = True
    tile_id = "south_africa_batsman"
    place_before(state, p0, tile_id)
    tycoon.roll(state, p0)
    assert state["pending"]["type"] == "buy"

    tycoon.bot_action(state, p0)
    assert state["properties"][tile_id]["owner"] == p0
    assert state["pending"] is None
    assert state["current_player_id"] == p1

    state["franchises"][p1]["is_bot"] = True
    state["franchises"][p1]["injured"] = 1
    turn = state["turn"]
    tycoon.bot_action(state, p1)
    assert state["franchises"][p1]["injured"] == 0
    assert state["turn"] == turn + 1
    assert state["dice"] is None


# ---------------------------------------------------------------------------
# API integration
# ---------------------------------------------------------------------------

def test_api_action_flow_rules_report_and_settings_clamp():
    client = new_client()
    rules = client.get("/api/fg/gamedata").json()["rules"]
    assert rules == {"ruleset": 5, "laps": 3, "min_players": 2, "max_players": 6}

    created = client.post("/api/fg/rooms", json={
        "name": "Host",
        "settings": {"max_players": 99, "laps": 99, "difficulty": "hard",
                     "legacy_key": "keep"},
    }).json()
    code, host = created["code"], created["player_id"]
    settings = created["state"]["settings"]
    assert settings["max_players"] == 6
    assert settings["laps"] == 5
    assert settings["difficulty"] == "hard"
    assert settings["legacy_key"] == "keep"

    updated = client.post(f"/api/fg/rooms/{code}/settings", json={
        "player_id": host, "settings": {"max_players": 1, "laps": 1},
    }).json()
    assert updated["settings"]["max_players"] == 2
    assert updated["settings"]["laps"] == 2
    assert updated["gamedata"]["rules"]["laps"] == 2

    guest = client.post("/api/fg/rooms/join", json={
        "code": code, "name": "Guest",
    }).json()["player_id"]
    client.post(f"/api/fg/rooms/{code}/start", json={"player_id": host})
    room = manager.by_code(code)
    state = room.state

    snap = room.snapshot(host)
    for key in tycoon.STATE_KEYS:
        assert key in snap
    assert snap["ruleset"] == 5
    assert snap["gamedata"]["rules"] == {
        "ruleset": 5, "laps": 2, "min_players": 2, "max_players": 6,
    }
    assert snap["standings"] == tycoon.standings(state)
    assert snap["you"] == host
    assert snap["board"] == state["board"]
    assert all("hand" not in f for f in snap["franchises"].values())

    tile_id = "south_africa_batsman"
    place_before(state, host, tile_id)
    assert hub.dispatch(room, host, "roll", {}) == "ok"
    assert state["pending"]["type"] == "buy"
    assert hub.dispatch(room, host, "buy", {}) == "ok"
    assert state["properties"][tile_id]["owner"] == host
    assert state["current_player_id"] == guest

    tycoon.advance_turn(state)  # back to the host
    assert hub.dispatch(room, host, "upgrade", {"tile_id": tile_id}) == "ok"
    assert state["properties"][tile_id]["level"] == 1
    assert hub.dispatch(room, host, "ping", {}) == "pong"

    state["pending"] = {"type": "auction", "pid": host, "price": 180}
    assert hub.dispatch(room, host, "auction_buy", {}) == "ok"
    assert len(state["franchises"][host]["squad"]) == 1

    with pytest.raises(ValueError, match="Unknown action"):
        hub.dispatch(room, host, "play_card", {})

    _save(room)
    summary = next(row for row in saved_summaries() if row["code"] == code)
    assert summary["laps"] == 2
    assert summary["turn"] == state["turn"]
    assert summary["turns"] == state["turn"]


def test_host_data_override_is_room_local_and_used_by_the_auction():
    client = new_client()
    created = client.post("/api/fg/rooms", json={"name": "Host"}).json()
    code, host = created["code"], created["player_id"]
    player = client.get("/api/fg/gamedata").json()["players"][0]
    updated = client.post(f"/api/fg/rooms/{code}/data", json={
        "player_id": host,
        "overrides": {"players": {player["id"]: {"batting": 99, "name": "Edited Name"}}},
    }).json()
    edited = next(p for p in updated["gamedata"]["players"] if p["id"] == player["id"])
    assert edited["batting"] == 99
    assert edited["name"] == "Edited Name"
    pristine = next(p for p in client.get("/api/fg/gamedata").json()["players"]
                    if p["id"] == player["id"])
    assert pristine["batting"] != 99
    assert pristine["name"] != "Edited Name"

    guest = client.post("/api/fg/rooms/join", json={
        "code": code, "name": "Guest",
    }).json()["player_id"]
    client.post(f"/api/fg/rooms/{code}/start", json={"player_id": host})
    state = manager.by_code(code).state
    assert state["data_overrides"]["players"][player["id"]]["batting"] == 99

    place_before(state, host, "mega_auction")
    tycoon.roll(state, host)
    tycoon.auction_buy(state, host)
    assert state["franchises"][host]["squad"] == [player["id"]]
    assert "Edited Name" in state["last_event"]["text"]
    assert data52.PLAYERS_BY_ID[player["id"]]["name"] != "Edited Name"
    assert guest in state["order"]


def test_bot_quick_game_completes():
    client = new_client()
    quick = client.post("/api/fg/quick", json={
        "name": "Solo", "avatar": "🦁", "color": "#c8a24b",
    }).json()
    assert quick["state"]["ruleset"] == 5
    assert quick["state"]["started"] is True
    assert len(quick["state"]["franchises"]) == 3
    room = manager.by_code(quick["code"])
    human = quick["player_id"]

    for _ in range(2000):
        state = room.state
        if state["finished"]:
            break
        pending = state.get("pending") or {}
        actor = pending.get("pid") or state.get("current_player_id")
        franchise = (state.get("franchises") or {}).get(actor) or {}
        if franchise.get("is_bot"):
            asyncio.run(hub.auto_room(room))
        else:
            tycoon.bot_action(state, actor)
    else:
        raise AssertionError("quick game did not finish")

    state = room.state
    assert state["phase"] == "over"
    assert state["winner_id"] in state["order"]
    assert all(f["wickets"] >= 0 for f in state["franchises"].values())
    _save(room)
    summary = next(row for row in saved_summaries() if row["code"] == room.code)
    assert summary["turn"] == state["turn"]
    assert summary["laps"] == state["laps"]


def test_old_saved_rulesets_stay_hidden():
    import json

    from app import persistence as db

    stale = []
    for ruleset, room_id, code in ((3, "old-room-3", "OLD03"), (4, "old-room-4", "OLD04")):
        payload = {"ruleset": ruleset, "room_id": room_id, "code": code,
                   "host_id": "old", "created_at": 1.0, "state": {}}
        with db._lock:
            with db._connection() as conn:
                conn.execute(db._sql("""
                    INSERT INTO franchise_rooms(room_id, code, host_id, created_at, updated_at, state_json)
                    VALUES(?,?,?,?,?,?)
                    ON CONFLICT(room_id) DO UPDATE SET state_json=excluded.state_json
                """), (room_id, code, "old", 1.0, 1.0, json.dumps(payload)))
        stale.append(room_id)
    assert all(row.get("room_id") not in stale for row in _rows())


def test_stale_and_invalid_invites_are_rejected():
    client = new_client()
    with pytest.raises(HTTPException) as exc:
        manager.by_code("NOPE0")
    assert exc.value.status_code == 404

    created = client.post("/api/fg/rooms", json={"name": "Host"}).json()
    code = created["code"]
    with pytest.raises(HTTPException) as exc:
        manager.by_token(code, "not-a-member")
    assert exc.value.status_code == 403

    with client.websocket_connect(f"/api/fg/ws?code={code}&token=not-a-member") as ws:
        message = ws.receive_json()
        assert message["type"] == "error"
        assert "Invalid room link" in message["message"]
