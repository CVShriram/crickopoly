"""Focused tests for Cricket Card Battle (ruleset 3)."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.game import cardbattle as tycoon, data52
from app.main import app
from app.tycoon_api import hub, manager, saved_summaries


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
        "room_id": f"r-{code}", "code": code, "host_id": "p0",
        "created_at": 1.0, "settings": settings or {}, "members": members,
        "data_overrides": {},
    }


def new_client() -> TestClient:
    """A client without the background tick loop; bots are driven explicitly."""
    return TestClient(app)


def test_rules_constants_match_the_published_contract():
    assert tycoon.RULES_VERSION == 3
    assert tycoon.DEFAULT_SETTINGS == {
        "max_players": 6, "rounds": 6, "difficulty": "medium",
    }
    assert set(tycoon.TACTICS) == {"attack", "anchor", "slog"}
    for tactic in tycoon.TACTICS.values():
        assert set(tactic) == {
            "id", "name", "icon", "desc", "run_mod", "wicket_mod",
            "pitch", "pitch_run", "pitch_wicket",
        }
    assert (tycoon.TACTICS["attack"]["run_mod"], tycoon.TACTICS["attack"]["wicket_mod"]) == (25, 1)
    assert (tycoon.TACTICS["anchor"]["run_mod"], tycoon.TACTICS["anchor"]["wicket_mod"]) == (10, -1)
    assert (tycoon.TACTICS["slog"]["run_mod"], tycoon.TACTICS["slog"]["wicket_mod"]) == (34, 3)
    assert set(tycoon.PITCH_EFFECTS) == {"flat", "green", "dry", "slow"}
    for effect in tycoon.PITCH_EFFECTS.values():
        assert set(effect) == {"runs", "wickets", "note"}


def test_new_state_deals_unique_real_cricketer_hands():
    state = tycoon.new_state(lobby("DEAL", 4, {"rounds": 3}))

    assert set(state) == set(tycoon.STATE_KEYS)
    assert state["ruleset"] == 3
    assert state["started"] is True
    assert state["finished"] is False
    assert state["phase"] == "battle"
    assert state["round"] == 1
    assert state["rounds"] == 3
    assert state["revealed"] is False
    assert state["pending"] is None
    assert state["last_result"] is None
    assert state["current_player_id"] == "p0"
    assert state["pitch"] == "flat"

    valid = {p["id"] for p in data52.merged_players()}
    seen: set[str] = set()
    for pid, franchise in state["franchises"].items():
        assert set(franchise) == {
            "id", "name", "avatar", "color", "is_bot", "hand",
            "points", "total_score", "played",
        }
        hand = franchise["hand"]
        assert len(hand) == 8
        assert len(set(hand)) == 8
        assert set(hand) <= valid
        assert not seen.intersection(hand)
        seen.update(hand)
        assert not set(tycoon.TACTICS).intersection(hand)
        assert franchise["points"] == 0
        assert franchise["total_score"] == 0
        assert franchise["played"] == 0


def test_two_human_round_resolves_without_auto_advance():
    state = tycoon.new_state(lobby("ROUND1", 2, {"rounds": 2}))
    order = list(state["order"])
    first, second = order

    assert tycoon.play_card(state, first, state["franchises"][first]["hand"][0], "attack") == "ok"
    assert state["current_player_id"] == second
    assert state["turn_index"] == 1
    assert state["revealed"] is False
    assert state["pending"] is None

    tycoon.play_card(state, second, state["franchises"][second]["hand"][0], "anchor")
    assert state["revealed"] is True
    assert state["pending"] == {"type": "result", "viewers": order}
    assert state["round"] == 1  # frontend sends "next"; engine must not advance
    assert set(state["plays"]) == set(order)

    result = state["last_result"]
    assert set(result) == {"round", "pitch", "rows", "winner_id"}
    assert result["round"] == 1
    assert result["pitch"] == "flat"
    assert result["winner_id"] in order
    assert len(result["rows"]) == 2
    for row in result["rows"]:
        assert set(row) == {
            "pid", "name", "avatar", "color", "runs", "wickets", "score",
            "player_id", "tactic_id", "won",
        }
        assert row["score"] == row["runs"] - row["wickets"] * 5
        assert row["won"] is (row["pid"] == result["winner_id"])
        assert state["franchises"][row["pid"]]["total_score"] == row["score"]
    assert sum(f["points"] for f in state["franchises"].values()) == 1
    assert any(e["kind"] == "round" for e in state["log"])

    tycoon.advance_turn(state)
    assert state["plays"] == {}
    assert state["revealed"] is False
    assert state["pending"] is None
    assert state["round"] == 2
    assert state["pitch"] == "green"
    assert state["order"] == [second, first]
    assert state["turn_index"] == 0
    assert state["current_player_id"] == second
    assert state["last_result"] is result or state["last_result"]["round"] == 1

    tycoon.advance_turn(state)
    assert state["finished"] is True
    assert state["phase"] == "over"
    assert state["winner_id"] in order


def test_standings_sort_by_points_then_total_score():
    state = tycoon.new_state(lobby("TABLE", 3))
    state["franchises"]["p0"].update(points=2, total_score=310)
    state["franchises"]["p1"].update(points=2, total_score=455)
    state["franchises"]["p2"].update(points=1, total_score=900)

    table = tycoon.standings(state)
    assert [row["pid"] for row in table] == ["p1", "p0", "p2"]
    assert [row["rank"] for row in table] == [1, 2, 3]
    for row in table:
        assert row["id"] == row["pid"]
        assert set(row) == {
            "pid", "id", "name", "avatar", "color", "points",
            "total_score", "rank",
        }


def test_invalid_plays_are_rejected_without_mutating_the_hand():
    state = tycoon.new_state(lobby("INVALID", 2))
    hand = list(state["franchises"]["p0"]["hand"])
    try:
        tycoon.play_card(state, "p1", hand[0], "attack")
    except ValueError as exc:
        assert "turn" in str(exc)
    else:
        raise AssertionError("wrong player was allowed to play")
    assert state["franchises"]["p0"]["hand"] == hand

    try:
        tycoon.play_card(state, "p0", "not_a_real_cricketer", "attack")
    except ValueError as exc:
        assert "hand" in str(exc)
    else:
        raise AssertionError("foreign card was allowed")

    try:
        tycoon.play_card(state, "p0", hand[0], "powerplay")
    except ValueError as exc:
        assert "tactic" in str(exc)
    else:
        raise AssertionError("unknown tactic was allowed")
    assert state["franchises"]["p0"]["hand"] == hand
    assert state["plays"] == {}


def test_api_hides_other_managers_cards_until_reveal():
    client = new_client()
    created = client.post("/api/fg/rooms", json={
        "name": "Host", "avatar": "🦁", "color": "#c8a24b",
    }).json()
    code, host = created["code"], created["player_id"]
    guest = client.post("/api/fg/rooms/join", json={
        "code": code, "name": "Guest", "avatar": "🦅", "color": "#4fd1c5",
    }).json()["player_id"]
    client.post(f"/api/fg/rooms/{code}/start", json={"player_id": host})
    room = manager.by_code(code)

    with client.websocket_connect(f"/api/fg/ws?code={code}&token={host}") as hws:
        assert hws.receive_json()["you"] == host

        card_host = room.state["franchises"][host]["hand"][0]
        hws.send_json({"action": "play_card", "player_id": card_host, "tactic_id": "attack"})
        h_update = hws.receive_json()
        assert h_update["state"]["plays"][host] == {
            "player_id": card_host, "tactic_id": "attack",
        }
        assert h_update["state"]["plays"][guest] is None
        assert h_update["state"]["revealed"] is False
        assert h_update["state"]["last_result"] is None

        guest_view = room.snapshot(guest)
        # The guest has not played yet, so every slot is still concealed.
        assert guest_view["plays"][host] is None
        assert guest_view["plays"][guest] is None

        card_guest = room.state["franchises"][guest]["hand"][0]
        assert hub.dispatch(room, guest, "play_card", {
            "player_id": card_guest, "tactic_id": "anchor",
        }) == "ok"
        asyncio.run(hub.broadcast(room))
        h_done = hws.receive_json()
        assert h_done["state"]["revealed"] is True
        assert h_done["state"]["plays"][host]["player_id"] == card_host
        assert h_done["state"]["plays"][guest]["player_id"] == card_guest
        assert h_done["state"]["last_result"]["round"] == 1
        assert h_done["state"]["ruleset"] == 3
        assert "board" not in h_done["state"]
        assert room.snapshot(guest)["plays"][host]["player_id"] == card_host

        # "next" is sent by the client; any result viewer may close it.
        hws.send_json({"action": "next"})
        h_next = hws.receive_json()
        assert h_next["state"]["round"] == 2
        assert h_next["state"]["plays"] == {}
        assert h_next["state"]["pending"] is None
        assert h_next["state"]["revealed"] is False
        assert h_next["state"]["last_result"]["round"] == 1

    try:
        hub.dispatch(room, "stranger", "next", {})
    except ValueError as exc:
        assert "Wait" in str(exc)
    else:
        raise AssertionError("non-viewer closed the result")


def test_bot_auto_play_completes_a_quick_game():
    client = new_client()
    quick = client.post("/api/fg/quick", json={
        "name": "Solo", "avatar": "🦁", "color": "#c8a24b",
        "settings": {"rounds": 2},
    }).json()
    assert quick["room_id"] and quick["code"] and quick["player_id"]
    assert quick["state"]["started"] is True
    assert quick["state"]["ruleset"] == 3
    assert len(quick["state"]["franchises"]) == 3

    room = manager.by_code(quick["code"])
    human = quick["player_id"]
    finished = False
    for _ in range(60):
        state = room.state
        if state["finished"]:
            finished = True
            break
        if state.get("revealed"):
            assert hub.dispatch(room, human, "next", {}) == "ok"
        elif state["current_player_id"] == human:
            card = state["franchises"][human]["hand"][0]
            hub.dispatch(room, human, "play_card", {
                "player_id": card, "tactic_id": "anchor",
            })
        else:
            asyncio.run(hub.auto_room(room))
    assert finished
    state = room.state
    assert state["phase"] == "over"
    assert state["winner_id"] in state["order"]
    assert state["round"] == 2
    assert state["pending"] is None
    assert all(f["played"] == 2 for f in state["franchises"].values())
    assert sum(f["points"] for f in state["franchises"].values()) == 2

    summary = next(row for row in saved_summaries() if row["code"] == room.code)
    assert summary["rounds"] == 2
    assert summary["matches"] >= 4  # start logs and resolved rounds are "round" entries


def test_game_rules_report_rounds_and_settings_are_clamped():
    client = new_client()
    rules = client.get("/api/fg/gamedata").json()["rules"]
    assert rules["ruleset"] == 3
    assert rules["rounds"] == 6
    assert "season_rounds" not in rules
    assert len(rules["pitch_effects"]) == 4
    assert len(client.get("/api/fg/gamedata").json()["tactical_cards"]) == 3

    created = client.post("/api/fg/rooms", json={
        "name": "Host", "avatar": "🦁", "color": "#c8a24b",
        "settings": {"max_players": 99, "rounds": 99,
                     "starting_credits": 1, "difficulty": 7},
    }).json()
    code, host = created["code"], created["player_id"]
    settings = created["state"]["settings"]
    assert settings["max_players"] == 6
    assert settings["rounds"] == 12
    assert settings["starting_credits"] == 1  # harmless key survives
    assert settings["difficulty"] == "medium"

    updated = client.post(f"/api/fg/rooms/{code}/settings", json={
        "player_id": host, "settings": {"max_players": 1, "rounds": 0},
    }).json()
    assert updated["settings"]["max_players"] == 2
    assert updated["settings"]["rounds"] == 2
    assert updated["gamedata"]["rules"]["rounds"] == 2


def test_host_data_override_is_room_local():
    client = new_client()
    created = client.post("/api/fg/rooms", json={
        "name": "Host", "avatar": "🦁", "color": "#c8a24b",
    }).json()
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

    # The override also changes the ratings used by this room's new state.
    guest = client.post("/api/fg/rooms/join", json={
        "code": code, "name": "Guest", "avatar": "🦅", "color": "#4fd1c5",
    }).json()["player_id"]
    started = client.post(f"/api/fg/rooms/{code}/start", json={"player_id": host}).json()
    state = manager.by_code(code).state
    assert state["data_overrides"]["players"][player["id"]]["batting"] == 99
    assert started["franchises"][guest]["hand"]


def test_stale_token_invalid_room_and_unknown_actions_behave_as_before():
    client = new_client()
    assert client.get("/api/fg/rooms/NOTHERE").status_code == 404
    assert client.post("/api/fg/rooms/NOTHERE/start", json={"player_id": "x"}).status_code == 404

    created = client.post("/api/fg/rooms", json={
        "name": "Host", "avatar": "🦁", "color": "#c8a24b",
    }).json()
    code, host = created["code"], created["player_id"]
    guest = client.post("/api/fg/rooms/join", json={
        "code": code, "name": "Guest", "avatar": "🦅", "color": "#4fd1c5",
    }).json()["player_id"]

    for path in ("start", "settings", "data"):
        body = {"player_id": guest}
        if path == "settings":
            body["settings"] = {"rounds": 3}
        if path == "data":
            body["overrides"] = {}
        assert client.post(f"/api/fg/rooms/{code}/{path}", json=body).status_code == 403

    client.post(f"/api/fg/rooms/{code}/start", json={"player_id": host})

    with client.websocket_connect(f"/api/fg/ws?code={code}&token=stale-token") as ws:
        message = ws.receive_json()
        assert message["type"] == "error"
        assert "Invalid room link" in message["message"]

    with client.websocket_connect(f"/api/fg/ws?code={code}&token={host}") as ws:
        assert ws.receive_json()["you"] == host
        ws.send_json({"action": "roll"})
        error = ws.receive_json()
        assert error["type"] == "error"
        assert error["message"] == "Unknown action: roll"
        ws.send_json({"action": "next"})
        error = ws.receive_json()
        assert "Wait" in error["message"]
        ws.send_json({"action": "ping"})
        assert ws.receive_json()["state"]["ruleset"] == 3
