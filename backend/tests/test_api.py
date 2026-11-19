"""REST + WebSocket integration tests."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.rooms import Room, manager

from .conftest import ScriptedRng

client = TestClient(app)


def create_room(name: str = "Host") -> dict:
    response = client.post("/api/rooms", json={"name": name, "avatar": "🏏", "color": "#22c55e"})
    assert response.status_code == 201
    return response.json()


def join_room(code: str, name: str) -> dict:
    response = client.post("/api/rooms/join", json={
        "code": code, "name": name, "avatar": "🏏", "color": "#3b82f6",
    })
    assert response.status_code == 200
    return response.json()


def recv_until(ws, predicate, limit: int = 30, allow_error: bool = False) -> dict:
    for _ in range(limit):
        message = ws.receive_json()
        if message.get("type") == "error" and not allow_error:
            raise AssertionError(f"Unexpected WebSocket error: {message.get('message')}")
        if predicate(message):
            return message
    raise AssertionError("Expected WebSocket message not received")


def player_state(state: dict, player_id: str) -> dict:
    return next(p for p in state["players"] if p["id"] == player_id)


def start_lobby(host_name: str = "ActionHost") -> tuple[dict, dict, Room]:
    """Create a two-player room, start it, and pin its engine for API tests."""
    host = create_room(host_name)
    guest = join_room(host["code"], "Guest")
    started = client.post(f"/api/rooms/{host['code']}/start",
                          json={"player_id": host["player_id"]})
    assert started.status_code == 200
    room = manager.get_by_code(host["code"])
    assert room is not None
    # Scripted RNG plus a far-future deadline keeps these tests independent of
    # random outcomes and wall-clock timers. The tick loop is not running in
    # these TestClient sessions, but pinning the deadline makes that explicit.
    room.engine.rng = ScriptedRng(dice=[1, 2], seed=11)
    room.engine.take_events()
    room.state.turn_deadline = 10**12
    room.state.pending = None
    room.state.market = None
    room.state.auction = None
    room.state.extra_turn = False
    return host, guest, room


def set_current_turn(room: Room, player_id: str) -> None:
    room.state.current_index = room.state.order.index(player_id)
    room.state.phase = "await_roll"
    room.state.pending = None
    room.state.market = None
    room.state.auction = None
    room.state.extra_turn = False
    room.state.players[player_id].debt = None


def unused_identity(room: Room) -> str:
    claimed = room.engine._claimed_identities()
    return next(key for key in config.FAMOUS_BATSMEN if key not in claimed)


def make_market(player_id: str, identities: list[str]) -> dict:
    return {
        "player_id": player_id,
        "price": config.RECRUITMENT_COST,
        "options": [
            {"identity_id": key, "name": config.FAMOUS_BATSMEN[key]["name"]}
            for key in identities
        ],
        "expires_at": 10**12,
    }


def set_debt(room: Room, player_id: str, receiver_id: str, amount: int) -> None:
    room.state.players[player_id].debt = {
        "payer_id": player_id, "receiver_id": receiver_id,
        "amount": amount, "paid": 0, "original": amount,
        "reason": "test debt", "expires_at": 10**12,
    }
    room.state.pending = {
        "type": "debt", "player_id": player_id, "expires_at": 10**12,
    }


def test_health_and_board():
    assert client.get("/api/health").json()["status"] == "ok"
    board = client.get("/api/board").json()
    assert len(board) == 32
    assert board[0]["type"] == "start"
    assert board[1]["type"] == "run_1"
    assert any(space["type"] == "run_6" for space in board)
    assert any(space["type"] == "recruit" for space in board)
    assert any(space["type"] == "no_ball" for space in board)


def test_add_bots_to_lobby():
    host = create_room("BotHost")
    response = client.post(f"/api/rooms/{host['code']}/bots",
                           json={"count": 2, "strategy": "smart"})
    assert response.status_code == 200
    state = response.json()
    assert len(state["players"]) == 3
    bots = [p for p in state["players"] if p["is_bot"]]
    assert len(bots) == 2
    assert all(p["ready"] and p["bot_strategy"] == "smart" for p in bots)


def test_add_bots_rejects_started_match():
    host = create_room("LateBots")
    join_room(host["code"], "Human")
    client.post(f"/api/rooms/{host['code']}/start",
                json={"player_id": host["player_id"]})
    response = client.post(f"/api/rooms/{host['code']}/bots",
                           json={"count": 1})
    assert response.status_code == 400


def test_quick_match_starts_immediately_with_bots():
    response = client.post("/api/test/match", json={"name": "Tester", "bots": 2})
    assert response.status_code == 200
    data = response.json()
    assert data["state"]["started"] is True
    assert len(data["state"]["players"]) == 3
    assert sum(1 for p in data["state"]["players"] if p["is_bot"]) == 2
    assert data["player_id"] in {p["id"] for p in data["state"]["players"]}
    assert "token=" in data["url"] and "code=" in data["url"]


def test_room_create_join_ready_and_start():
    host = create_room("Alice")
    guest = join_room(host["code"], "Bob")
    assert len(client.get(f"/api/rooms/{host['code']}").json()["players"]) == 2

    ready = client.post(f"/api/rooms/{host['code']}/ready",
                        json={"player_id": guest["player_id"], "ready": True})
    assert ready.status_code == 200
    started = client.post(f"/api/rooms/{host['code']}/start",
                          json={"player_id": host["player_id"]})
    assert started.status_code == 200
    assert started.json()["started"] is True
    assert len(started.json()["players"][0]["batsmen"]) == 1


def test_only_host_can_start():
    host = create_room("Host")
    guest = join_room(host["code"], "Guest")
    response = client.post(f"/api/rooms/{host['code']}/start",
                           json={"player_id": guest["player_id"]})
    assert response.status_code == 400


def test_rest_join_pushes_live_roster_update_to_host():
    """Regression: a friend joining over REST must refresh the host's lobby
    over the socket. Without this push the host sees a one-player room and the
    Start button stays disabled with "At least 2 managers are needed"."""
    host = create_room("LiveHost")
    with client.websocket_connect(
        f"/ws?code={host['code']}&token={host['player_id']}"
    ) as host_ws:
        first = host_ws.receive_json()
        assert len(first["state"]["players"]) == 1

        join_room(host["code"], "LiveGuest")

        # The host sends no action — the refreshed roster must arrive on its own.
        update = recv_until(
            host_ws,
            lambda m: len(m.get("state", {}).get("players", [])) == 2,
        )
        names = {p["name"] for p in update["state"]["players"]}
        assert {"LiveHost", "LiveGuest"} == names


def test_websocket_start_and_roll():
    host = create_room("WSHost")
    guest = join_room(host["code"], "WSGuest")
    with client.websocket_connect(f"/ws?code={host['code']}&token={host['player_id']}") as host_ws, \
         client.websocket_connect(f"/ws?code={host['code']}&token={guest['player_id']}") as guest_ws:
        first = host_ws.receive_json()
        assert first["type"] == "update" and len(first["board"]) == 32
        guest_ws.receive_json()
        host_ws.send_json({"action": "start"})
        update = recv_until(host_ws, lambda m: any(
            e["type"] == "game_started" for e in m.get("events", [])))
        assert update["state"]["started"] is True
        current = update["state"]["current_player_id"]
        current_ws = host_ws if current == host["player_id"] else guest_ws
        current_ws.send_json({"action": "roll"})
        rolled = recv_until(current_ws, lambda m: any(
            e["type"] == "dice" for e in m.get("events", [])))
        dice_event = next(e for e in rolled["events"] if e["type"] == "dice")
        assert len(dice_event["payload"]["dice"]) == 2
        assert 2 <= dice_event["payload"]["total"] <= 12
        assert current in [p["id"] for p in rolled["state"]["players"]]


def test_websocket_rejects_unauthorized_roll():
    host = create_room("AuthHost")
    guest = join_room(host["code"], "AuthGuest")
    with client.websocket_connect(f"/ws?code={host['code']}&token={host['player_id']}") as host_ws, \
         client.websocket_connect(f"/ws?code={host['code']}&token={guest['player_id']}") as guest_ws:
        host_ws.receive_json()
        guest_ws.receive_json()
        host_ws.send_json({"action": "start"})
        recv_until(host_ws, lambda m: m.get("state", {}).get("started"))
        # Find whichever player is not current and try to roll.
        state = client.get(f"/api/rooms/{host['code']}").json()
        other = next(p["id"] for p in state["players"]
                     if p["id"] != state["current_player_id"])
        ws = host_ws if other == host["player_id"] else guest_ws
        ws.send_json({"action": "roll"})
        error = recv_until(ws, lambda m: m.get("type") == "error",
                           allow_error=True)
        assert "turn" in error["message"]


def test_history_endpoint():
    response = client.get("/api/history")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_public_leaderboard_endpoint():
    response = client.get("/api/leaderboard?limit=5")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_websocket_gift_coins_updates_both_managers():
    host, guest, room = start_lobby("GiftHost")
    set_current_turn(room, host["player_id"])
    host_before = room.state.players[host["player_id"]].money
    guest_before = room.state.players[guest["player_id"]].money

    with client.websocket_connect(f"/ws?code={host['code']}&token={host['player_id']}") as host_ws, \
         client.websocket_connect(f"/ws?code={host['code']}&token={guest['player_id']}") as guest_ws:
        host_ws.receive_json()
        guest_ws.receive_json()
        host_ws.send_json({
            "action": "gift_coins",
            "to_player_id": guest["player_id"],
            "amount": 150,
        })
        update = recv_until(host_ws, lambda m: any(
            e["type"] == "coins_gifted" for e in m.get("events", [])))
        guest_update = recv_until(guest_ws, lambda m: any(
            e["type"] == "coins_gifted" for e in m.get("events", [])))

    assert player_state(update["state"], host["player_id"])["money"] == host_before - 150
    assert player_state(update["state"], guest["player_id"])["money"] == guest_before + 150
    assert player_state(guest_update["state"], guest["player_id"])["money"] == guest_before + 150


# ---------------------------------------------------------------------------
# Phase 7 — deterministic API / WebSocket coverage
# ---------------------------------------------------------------------------
def test_config_exposes_phase7_catalog_and_costs():
    cfg = client.get("/api/config").json()
    assert cfg["famous_batsmen"] == config.FAMOUS_BATSMEN
    assert cfg["custom_defaults"] == config.CUSTOM_IDENTITY_DEFAULTS
    assert cfg["custom_skin_options"] == config.CUSTOM_SKIN_OPTIONS
    assert cfg["custom_hair_options"] == config.CUSTOM_HAIR_OPTIONS
    assert cfg["custom_face_options"] == config.CUSTOM_FACE_OPTIONS
    assert cfg["custom_countries"] == config.CUSTOM_COUNTRIES

    tables = {
        "batsmen": config.BATSMEN,
        "bowlers": config.BOWLERS,
        "wicket_keepers": config.WICKET_KEEPERS,
        "fielders": config.FIELDERS,
        "stadiums": config.STADIUMS,
    }
    for key, expected in tables.items():
        assert cfg[key] == expected

    assert cfg["batsman_upgrade_costs"] == {
        str(level): cost for level, cost in config.BATSMAN_UPGRADE_COSTS.items()
    }
    assert cfg["max_batsman_level"] == config.MAX_BATSMAN_LEVEL
    assert cfg["max_batsmen"] == config.MAX_BATSMEN_PER_PLAYER
    assert cfg["six_runs_per_level"] == config.SIX_RUNS_PER_LEVEL
    assert cfg["recruitment_cost"] == config.RECRUITMENT_COST
    assert cfg["gift_min_coins"] == config.GIFT_MIN_COINS
    assert cfg["gift_max_coins"] == config.GIFT_MAX_COINS
    assert cfg["gift_reserve_coins"] == config.GIFT_RESERVE_COINS
    assert cfg["gifts_per_round"] == config.GIFTS_PER_ROUND
    assert set(cfg["victory_modes"]) == set(config.VICTORY_MODES)


def test_websocket_draft_rejects_duplicate_and_accepts_custom():
    host = create_room("DraftHost")
    guest = join_room(host["code"], "DraftGuest")
    famous = "virat_kohli"

    with client.websocket_connect(f"/ws?code={host['code']}&token={host['player_id']}") as host_ws, \
         client.websocket_connect(f"/ws?code={host['code']}&token={guest['player_id']}") as guest_ws:
        host_ws.receive_json()
        guest_ws.receive_json()

        host_ws.send_json({"action": "select_batsman", "identity_id": famous})
        selected = recv_until(host_ws, lambda m: any(
            e["type"] == "batsman_selected"
            and e["payload"]["player_id"] == host["player_id"]
            for e in m.get("events", [])))
        guest_ws.receive_json()  # consume the host's broadcast
        assert player_state(selected["state"], host["player_id"])["selection"]["identity_id"] == famous

        guest_ws.send_json({"action": "select_batsman", "identity_id": famous})
        error = recv_until(guest_ws, lambda m: m.get("type") == "error",
                           allow_error=True)
        assert "already" in error["message"].lower()

        custom = {
            "name": "My Slugger", "jersey_number": 9, "jersey_color": "#ff0000",
            "skin": "#f1c27d", "hair": "spiky", "face": "grin",
        }
        guest_ws.send_json({"action": "create_batsman", "custom": custom})
        created = recv_until(guest_ws, lambda m: any(
            e["type"] == "batsman_selected"
            and e["payload"]["selection"].get("is_custom")
            for e in m.get("events", [])))
        host_ws.receive_json()  # consume the guest's broadcast
        selection = player_state(created["state"], guest["player_id"])["selection"]
        assert selection["name"] == "My Slugger"
        assert selection["is_custom"] is True and selection["identity_id"] is None

        host_ws.send_json({"action": "start"})
        started = recv_until(host_ws, lambda m: m.get("state", {}).get("started"))
        guest_ws.receive_json()
        by_id = {p["id"]: p for p in started["state"]["players"]}
        assert by_id[host["player_id"]]["batsmen"][0]["identity_id"] == famous
        custom_batsman = by_id[guest["player_id"]]["batsmen"][0]
        assert custom_batsman["name"] == "My Slugger"
        assert custom_batsman["is_custom"] is True


def test_websocket_victory_mode_is_host_only():
    host = create_room("VictoryHost")
    guest = join_room(host["code"], "VictoryGuest")

    with client.websocket_connect(f"/ws?code={host['code']}&token={host['player_id']}") as host_ws, \
         client.websocket_connect(f"/ws?code={host['code']}&token={guest['player_id']}") as guest_ws:
        host_ws.receive_json()
        guest_ws.receive_json()

        guest_ws.send_json({"action": "victory_mode", "mode": "turn_limit", "turn_limit": 5})
        error = recv_until(guest_ws, lambda m: m.get("type") == "error",
                           allow_error=True)
        assert "host" in error["message"].lower()

        host_ws.send_json({"action": "victory_mode", "mode": "turn_limit", "turn_limit": 5})
        updated = recv_until(host_ws, lambda m: any(
            e["type"] == "victory_settings" for e in m.get("events", [])))
        guest_ws.receive_json()
        assert updated["state"]["victory_mode"] == "turn_limit"
        assert updated["state"]["turn_limit"] == 5


def test_quick_match_accepts_victory_settings():
    response = client.post("/api/test/match", json={
        "name": "VictoryTester", "bots": 2,
        "victory_mode": "turn_limit", "turn_limit": 7,
    })
    assert response.status_code == 200
    state = response.json()["state"]
    assert state["started"] is True
    assert state["victory_mode"] == "turn_limit"
    assert state["turn_limit"] == 7

    default = client.post("/api/test/match", json={
        "name": "DefaultVictory", "bots": 1,
        "victory_mode": "last_standing", "turn_limit": 99,
    })
    assert default.status_code == 200
    assert default.json()["state"]["victory_mode"] == "last_standing"
    assert default.json()["state"]["turn_limit"] == 0


def test_started_match_state_exposes_phase7_fields():
    host = create_room("StateHost")
    join_room(host["code"], "StateGuest")
    started = client.post(f"/api/rooms/{host['code']}/start",
                          json={"player_id": host["player_id"]})
    assert started.status_code == 200
    manager.get_by_code(host["code"]).engine.take_events()

    with client.websocket_connect(f"/ws?code={host['code']}&token={host['player_id']}") as ws:
        state = ws.receive_json()["state"]
        assert state["started"] is True
        assert state["victory_mode"] in config.VICTORY_MODES
        assert "turn_limit" in state and "extra_turn" in state
        assert "market" in state and "ranking" in state
        assert isinstance(state["ranking"], list)

        for player in state["players"]:
            assert len(player["batsmen"]) == 1
            assert player["active_batsman_id"] == player["batsmen"][0]["id"]
            assert player["no_ball_turns"] == 0
            assert player["no_ball_protection"] == 0
            assert "debt" in player and "selection" in player

    rest = client.get(f"/api/rooms/{host['code']}").json()
    assert rest["victory_mode"] == state["victory_mode"]
    assert "market" in rest and "ranking" in rest


def test_websocket_routes_switch_and_upgrade_batsman():
    host, guest, room = start_lobby("SwitchHost")
    pid = host["player_id"]
    set_current_turn(room, pid)
    player = room.state.players[pid]
    second = room.engine._create_batsman(player, unused_identity(room))
    room.engine.take_events()

    with client.websocket_connect(f"/ws?code={host['code']}&token={pid}") as ws:
        ws.receive_json()

        ws.send_json({"action": "switch_batsman", "batsman_id": second.id})
        switched = recv_until(ws, lambda m: any(
            e["type"] == "batsman_switched" for e in m.get("events", [])))
        assert player.active_batsman_id == second.id
        assert player_state(switched["state"], pid)["active_batsman_id"] == second.id

        money = player.money
        ws.send_json({"action": "upgrade_batsman", "batsman_id": second.id})
        upgraded = recv_until(ws, lambda m: any(
            e["type"] == "batsman_upgraded" for e in m.get("events", [])))
        assert second.level == 2
        assert player.money == money - config.BATSMAN_UPGRADE_COSTS[1]
        batsman = next(b for b in player_state(upgraded["state"], pid)["batsmen"]
                       if b["id"] == second.id)
        assert batsman["level"] == 2


def test_websocket_routes_recruit_and_decline_recruit():
    host, guest, room = start_lobby("RecruitHost")
    pid = host["player_id"]
    set_current_turn(room, pid)
    player = room.state.players[pid]
    identity = unused_identity(room)
    room.state.market = make_market(pid, [identity])
    room.engine.take_events()

    with client.websocket_connect(f"/ws?code={host['code']}&token={pid}") as ws:
        ws.receive_json()
        money = player.money

        ws.send_json({"action": "recruit", "identity_id": identity})
        recruited = recv_until(ws, lambda m: any(
            e["type"] == "batsman_recruited" for e in m.get("events", [])))
        assert len(player.batsmen) == 2
        assert player.money == money - config.RECRUITMENT_COST
        assert room.state.pending["type"] == "recruit_activate"
        assert any(b["identity_id"] == identity
                   for b in player_state(recruited["state"], pid)["batsmen"])

        # Reopen the market directly so the decline route has a decision to reject.
        room.state.market = make_market(pid, [unused_identity(room)])
        room.engine.take_events()
        ws.send_json({"action": "decline_recruit"})
        recv_until(ws, lambda m: any(
            e["type"] == "recruit_declined" for e in m.get("events", [])))
        assert room.state.market is None
        assert room.state.pending is None


def test_websocket_routes_downgrade_pay_debt_and_bankrupt():
    host, guest, room = start_lobby("DebtHost")
    pid, receiver = host["player_id"], guest["player_id"]
    set_current_turn(room, pid)
    player = room.state.players[pid]
    asset = room.engine._create_asset(player, 2)  # Club Bowler, upgrade cost 180
    player.assets[asset.id] = asset
    asset.level = 1
    set_debt(room, pid, receiver, 100)
    base_cost = int(asset.config.get("upgrade_cost", 0))
    refund = int(base_cost * (1 + config.PROPERTY_LEVEL_INCOME_MULTIPLIER
                              * (asset.level - 1)) * 0.6)
    room.engine.take_events()

    with client.websocket_connect(f"/ws?code={host['code']}&token={pid}") as ws:
        ws.receive_json()
        money = player.money

        ws.send_json({"action": "downgrade", "asset_id": asset.id})
        downgraded = recv_until(ws, lambda m: any(
            e["type"] == "downgrade" for e in m.get("events", [])))
        assert asset.level == 0
        assert player.money == money + refund
        assert next(a for a in player_state(downgraded["state"], pid)["assets"]
                    if a["id"] == asset.id)["level"] == 0

        ws.send_json({"action": "pay_debt"})
        recv_until(ws, lambda m: any(
            e["type"] == "debt_paid" for e in m.get("events", [])))
        assert player.debt is None
        assert room.state.pending is None
        assert player.money == money + refund - 100

        set_debt(room, pid, receiver, 10**6)
        room.engine.take_events()
        ws.send_json({"action": "bankrupt"})
        bankrupt = recv_until(ws, lambda m: any(
            e["type"] == "bankrupt" for e in m.get("events", [])))
        assert player.eliminated is True
        assert room.state.phase == "over"
        assert bankrupt["state"]["winner_id"] == receiver
        assert asset.id in room.state.players[receiver].assets
