"""Focused tests for Wicket Rush (ruleset 4)."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.game import data52, wicketrush as tycoon
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


def cards(role: str | None = None) -> list[str]:
    return [p["id"] for p in data52.merged_players()
            if role is None or p["role"] == role]


def ratings() -> dict[str, dict]:
    return {p["id"]: p for p in data52.merged_players()}


def give(state: dict, pid: str, hand: list[str]) -> None:
    state["franchises"][pid]["hand"] = list(hand)


def test_rules_constants_and_state_shape():
    assert tycoon.RULES_VERSION == 4
    assert tycoon.DEFAULT_SETTINGS == {"max_players": 6, "hand_size": 7}
    state = tycoon.new_state(lobby("SHAPE", 3))
    assert set(state) == set(tycoon.STATE_KEYS)
    assert state["ruleset"] == 4
    assert state["started"] is True
    assert state["finished"] is False
    assert state["phase"] == "play"
    assert state["turn"] == 1
    assert state["direction"] == 1
    assert state["current_role"] is None
    assert state["last_card"] is None
    assert state["pending"] is None
    assert state["last_event"] is None
    assert state["discard"] == []
    for pid, franchise in state["franchises"].items():
        assert set(franchise) == {
            "id", "name", "avatar", "color", "is_bot", "hand",
            "runs", "wickets", "drawn",
        }
        assert franchise["runs"] == 0
        assert franchise["wickets"] == 0
        assert franchise["drawn"] == 0


def test_new_state_deals_unique_real_cricketer_hands():
    state = tycoon.new_state(lobby("DEAL", 4, {"hand_size": 9}))
    assert state["settings"]["hand_size"] == 9
    valid = set(cards())
    seen: set[str] = set()
    for pid, franchise in state["franchises"].items():
        hand = franchise["hand"]
        assert len(hand) == 9
        assert len(set(hand)) == 9
        assert set(hand) <= valid
        assert not seen.intersection(hand)
        seen.update(hand)
    assert len(state["deck"]) == len(valid) - 36
    assert not seen.intersection(state["deck"])


def test_legal_role_wild_matching_and_forced_bowler():
    state = tycoon.new_state(lobby("LEGAL", 3))
    p0, p1, p2 = state["order"]
    bat, bowl, keeper, wild = (cards(role)[0] for role in
                               ("batsman", "bowler", "wicketkeeper", "allrounder"))
    give(state, p0, [bat, cards("bowler")[1]])
    give(state, p1, [keeper, bowl, cards("allrounder")[1]])
    give(state, p2, [cards("batsman")[2], cards("wicketkeeper")[1]])

    # Any role is legal before the first card.
    assert tycoon.play_card(state, p0, bat) == "ok"
    assert state["current_role"] == "batsman"
    assert state["forced_role"] == "bowler"
    assert state["current_player_id"] == p1

    # A batsman forces the next player to bowl (or play wild).
    with pytest.raises(ValueError, match="bowler"):
        tycoon.play_card(state, p1, keeper)
    assert tycoon.play_card(state, p1, bowl) == "ok"
    assert state["forced_role"] is None
    assert state["current_role"] == "bowler"

    # Now the role is bowler: a batsman is illegal, a wild all-rounder is not.
    bad_bat = cards("batsman")[1]
    wild2 = cards("allrounder")[2]
    give(state, p0, [bad_bat, wild2])
    with pytest.raises(ValueError, match="current role"):
        tycoon.play_card(state, p0, bad_bat)
    assert tycoon.play_card(state, p0, wild2) == "ok"
    assert state["direction"] == -1


def test_batsman_adds_deterministic_runs_and_forces_bowler():
    state = tycoon.new_state(lobby("BAT", 2))
    p0, _ = state["order"]
    bat = cards("batsman")[0]
    give(state, p0, [bat, cards("bowler")[0]])
    expected = 10 + int(ratings()[bat]["batting"]) // 5
    tycoon.play_card(state, p0, bat)
    assert state["franchises"][p0]["runs"] == expected
    assert state["forced_role"] == "bowler"
    assert state["last_event"]["type"] == "batsman"
    assert any(entry["kind"] == "runs" for entry in state["log"])


def test_bowler_gives_next_player_a_wicket_and_skips_them():
    state = tycoon.new_state(lobby("SKIP", 3))
    p0, p1, p2 = state["order"]
    give(state, p0, [cards("bowler")[0], cards("batsman")[1]])
    give(state, p1, [cards("batsman")[0], cards("bowler")[1]])
    give(state, p2, [cards("wicketkeeper")[0], cards("allrounder")[0]])
    turn_before = state["turn"]

    tycoon.play_card(state, p0, cards("bowler")[0])
    assert state["franchises"][p1]["wickets"] == 1
    assert state["franchises"][p0]["wickets"] == 0
    assert state["franchises"][p2]["wickets"] == 0
    assert state["current_player_id"] == p2  # skip p1, advance two places
    assert state["turn"] > turn_before
    assert state["last_event"]["type"] == "bowler"


def test_wicketkeeper_sets_pending_target_and_steals_highest_bat_card():
    state = tycoon.new_state(lobby("STEAL", 3))
    p0, p1, p2 = state["order"]
    keeper = cards("wicketkeeper")[0]
    ranked = sorted(cards("batsman"), key=lambda c: int(ratings()[c]["batting"]))
    low, high = ranked[0], ranked[-1]
    give(state, p0, [keeper, cards("bowler")[0]])
    give(state, p1, [low, high])
    give(state, p2, [cards("allrounder")[0], cards("bowler")[1]])

    tycoon.play_card(state, p0, keeper)
    assert state["pending"] == {
        "type": "target", "pid": p0, "effect": "run_out",
        "candidates": [p1, p2],
    }
    assert state["current_player_id"] == p0  # no advance while choosing

    with pytest.raises(ValueError, match="rival"):
        tycoon.choose_target(state, p0, p0)
    with pytest.raises(ValueError, match="actor"):
        tycoon.choose_target(state, p1, p1)
    assert state["pending"]["pid"] == p0  # failed choices changed nothing

    tycoon.choose_target(state, p0, p1)
    assert high in state["franchises"][p0]["hand"]
    assert low in state["franchises"][p1]["hand"]
    assert high not in state["franchises"][p1]["hand"]
    assert len(state["franchises"][p1]["hand"]) == 2  # stolen one, drew one
    assert state["pending"] is None
    assert state["current_player_id"] == p1  # normal one-place advance
    assert state["last_event"]["type"] == "run_out"


def test_allrounder_reverses_direction_and_plays_again():
    state = tycoon.new_state(lobby("WILD", 3))
    p0, p1, _ = state["order"]
    wild = cards("allrounder")[0]
    give(state, p0, [wild, cards("bowler")[0], cards("wicketkeeper")[1]])
    give(state, p1, [cards("batsman")[0], cards("bowler")[1]])
    give(state, state["order"][2], [cards("wicketkeeper")[0], cards("allrounder")[1]])
    turn_before = state["turn"]

    tycoon.play_card(state, p0, wild)
    assert state["direction"] == -1
    assert state["current_player_id"] == p0
    assert state["turn"] == turn_before
    assert state["franchises"][p0]["runs"] == 5
    assert state["last_card"]["player_id"] == wild
    assert wild not in state["franchises"][p0]["hand"]

    # The same manager immediately plays again; no infinite loop because the
    # wild card is gone. With 3 players and direction -1, skipping two lands
    # back on the first rival after the actor in reverse order.
    next_card = state["franchises"][p0]["hand"][0]
    tycoon.play_card(state, p0, next_card)
    assert state["current_player_id"] == p1


def test_draw_takes_two_cards_reshuffles_and_clears_forced_role():
    state = tycoon.new_state(lobby("DRAW", 2))
    p0, p1 = state["order"]
    current = cards("batsman")[0]
    pool = cards("bowler")[:3]
    state["deck"] = []
    state["discard"] = pool + [current]
    state["last_card"] = {"player_id": current, "name": current,
                          "role": "batsman", "effect": "batsman", "owner_id": p1}
    state["forced_role"] = "bowler"
    before = len(state["franchises"][p0]["hand"])

    tycoon.draw(state, p0)
    assert len(state["franchises"][p0]["hand"]) == before + 2
    assert state["franchises"][p0]["drawn"] == 1
    assert state["deck"] == pool[2:]  # 3 recycled, 2 drawn
    assert state["discard"] == [current]  # current card stays on top
    assert state["forced_role"] is None
    assert state["current_player_id"] == p1
    assert state["last_event"]["type"] == "draw"


def test_empty_hand_finishes_immediately_without_auto_advance():
    state = tycoon.new_state(lobby("FINISH", 2))
    p0, _ = state["order"]
    only_card = cards("allrounder")[0]
    give(state, p0, [only_card])
    turn_before = state["turn"]

    tycoon.play_card(state, p0, only_card)
    assert state["finished"] is True
    assert state["phase"] == "over"
    assert state["winner_id"] == p0
    assert state["current_player_id"] == p0
    assert state["turn"] == turn_before
    assert state["last_event"] == {
        "type": "finish",
        "text": state["last_event"]["text"],
    }
    assert any(entry["kind"] == "final" for entry in state["log"])
    with pytest.raises(ValueError, match="complete"):
        tycoon.draw(state, p0)


def test_standings_sort_by_score_desc():
    state = tycoon.new_state(lobby("TABLE", 3))
    state["franchises"]["p0"].update(runs=90, wickets=1)
    state["franchises"]["p1"].update(runs=75, wickets=0)
    state["franchises"]["p2"].update(runs=110, wickets=4)
    table = tycoon.standings(state)
    assert [row["id"] for row in table] == ["p2", "p0", "p1"]
    assert [row["rank"] for row in table] == [1, 2, 3]
    assert [row["score"] for row in table] == [90, 85, 75]
    for row in table:
        assert set(row) == {
            "id", "name", "avatar", "color", "runs", "wickets",
            "cards", "score", "rank",
        }
        assert row["score"] == row["runs"] - row["wickets"] * 5
        assert row["cards"] == len(state["franchises"][row["id"]]["hand"])


def test_api_conceals_every_hand_except_viewers_and_the_whole_deck():
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

    host_view = room.snapshot(host)
    assert host_view["ruleset"] == 4
    assert host_view["gamedata"]["rules"] == {
        "ruleset": 4, "hand_size": 7, "min_players": 2, "max_players": 6,
    }
    assert host_view["franchises"][host]["hand"] == room.state["franchises"][host]["hand"]
    assert host_view["franchises"][guest]["hand"] == []
    assert host_view["franchises"][guest]["hand_count"] == len(
        room.state["franchises"][guest]["hand"])
    assert "deck" not in host_view
    assert host_view["deck_count"] == len(room.state["deck"])
    for key in ("last_card", "current_role", "last_event", "pending",
                "standings", "franchises", "you", "host_id", "settings",
                "ruleset", "started", "finished", "phase", "turn"):
        assert key in host_view

    guest_view = room.snapshot(guest)
    assert guest_view["franchises"][guest]["hand"] == room.state["franchises"][guest]["hand"]
    assert guest_view["franchises"][host]["hand"] == []
    assert "deck" not in guest_view

    anonymous = client.get(f"/api/fg/rooms/{code}").json()
    assert all(f["hand"] == [] for f in anonymous["franchises"].values())
    assert all("hand_count" in f for f in anonymous["franchises"].values())

    # Concealment must be a copy, never an edit to the authoritative state.
    assert room.state["franchises"][host]["hand"]
    assert room.state["deck"]


def test_dispatch_actions_and_unknown_action_errors():
    client = new_client()
    created = client.post("/api/fg/rooms", json={"name": "Host"}).json()
    code, host = created["code"], created["player_id"]
    guest = client.post("/api/fg/rooms/join", json={
        "code": code, "name": "Guest",
    }).json()["player_id"]
    client.post(f"/api/fg/rooms/{code}/start", json={"player_id": host})
    room = manager.by_code(code)

    give(room.state, host, [cards("batsman")[0], cards("bowler")[0]])
    assert hub.dispatch(room, host, "play_card", {
        "player_id": room.state["franchises"][host]["hand"][0],
    }) == "ok"
    assert room.state["current_player_id"] == guest

    with pytest.raises(ValueError, match="turn"):
        hub.dispatch(room, host, "draw", {})
    size = len(room.state["franchises"][guest]["hand"])
    assert hub.dispatch(room, guest, "draw", {}) == "ok"
    assert len(room.state["franchises"][guest]["hand"]) == size + 2
    assert room.state["franchises"][guest]["drawn"] == 1

    assert hub.dispatch(room, host, "ping", {}) == "pong"
    with pytest.raises(ValueError, match="Unknown action"):
        hub.dispatch(room, host, "next", {})
    with pytest.raises(ValueError, match="Unknown action"):
        hub.dispatch(room, host, "roll", {})


def test_bot_quick_game_completes():
    client = new_client()
    quick = client.post("/api/fg/quick", json={
        "name": "Solo", "avatar": "🦁", "color": "#c8a24b",
    }).json()
    assert quick["state"]["ruleset"] == 4
    assert quick["state"]["started"] is True
    assert len(quick["state"]["franchises"]) == 3
    room = manager.by_code(quick["code"])
    human = quick["player_id"]

    for _ in range(1000):
        state = room.state
        if state["finished"]:
            break
        pending = state.get("pending") or {}
        if pending.get("type") == "target":
            if pending.get("pid") == human:
                tycoon.choose_target(state, human, pending["candidates"][0])
            else:
                asyncio.run(hub.auto_room(room))
            continue
        if state["current_player_id"] == human:
            tycoon.bot_action(state, human)
        else:
            asyncio.run(hub.auto_room(room))
    else:
        raise AssertionError("quick game did not finish")

    state = room.state
    assert state["phase"] == "over"
    assert state["winner_id"] in state["order"]
    assert all(not f["hand"] for pid, f in state["franchises"].items()
               if pid == state["winner_id"])
    summary = next(row for row in saved_summaries() if row["code"] == room.code)
    assert summary["turn"] == state["turn"]
    assert summary["turns"] == state["turn"]
    assert summary["turn"] >= 1


def test_game_rules_report_ruleset_and_settings_are_clamped():
    client = new_client()
    rules = client.get("/api/fg/gamedata").json()["rules"]
    assert rules == {
        "ruleset": 4, "hand_size": 7, "min_players": 2, "max_players": 6,
    }

    created = client.post("/api/fg/rooms", json={
        "name": "Host",
        "settings": {"max_players": 99, "hand_size": 99,
                     "starting_credits": 1, "season_rounds": 3},
    }).json()
    code, host = created["code"], created["player_id"]
    settings = created["state"]["settings"]
    assert settings["max_players"] == 6
    assert settings["hand_size"] == 12
    assert settings["starting_credits"] == 1  # harmless legacy key survives
    assert settings["season_rounds"] == 3

    updated = client.post(f"/api/fg/rooms/{code}/settings", json={
        "player_id": host, "settings": {"max_players": 1, "hand_size": 1},
    }).json()
    assert updated["settings"]["max_players"] == 2
    assert updated["settings"]["hand_size"] == 5
    assert updated["gamedata"]["rules"]["hand_size"] == 5

    assert tycoon.new_state(
        lobby("CLAMP", 2, {"hand_size": 99}))["settings"]["hand_size"] == 12


def test_host_data_override_is_room_local_and_used_by_the_engine():
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

    give(state, host, [player["id"], cards("bowler")[0]])
    tycoon.play_card(state, host, player["id"])
    assert state["franchises"][host]["runs"] == 10 + 99 // 5
    assert data52.PLAYERS_BY_ID[player["id"]]["name"] != "Edited Name"


def test_old_saved_rulesets_stay_hidden():
    from app import persistence as db
    from app.tycoon_api import _rows

    payload = {"ruleset": 3, "room_id": "old-room", "code": "OLD01",
               "host_id": "old", "created_at": 1.0, "state": {}}
    with db._lock:
        with db._connection() as conn:
            conn.execute(db._sql("""
                INSERT INTO franchise_rooms(room_id, code, host_id, created_at, updated_at, state_json)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(room_id) DO UPDATE SET state_json=excluded.state_json
            """), ("old-room", "OLD01", "old", 1.0, 1.0, __import__("json").dumps(payload)))
    assert all(row.get("room_id") != "old-room" for row in _rows())
