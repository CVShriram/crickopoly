"""Tests for the rebuilt Stadium Tycoon ruleset (ruleset 2)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.game import data52, tycoon
from app.main import app
from app.tycoon_api import manager


def lobby(code: str, players: int = 2) -> dict:
    members = {}
    for i in range(players):
        pid = f"p{i}"
        members[pid] = {
            "id": pid, "name": f"Manager {i}", "avatar": "🏏",
            "color": "#c8a24b", "is_host": i == 0, "is_bot": False,
            "difficulty": "medium", "ready": True,
        }
    return {"room_id": f"r-{code}", "code": code, "host_id": "p0",
            "created_at": 1.0, "settings": {}, "members": members, "data_overrides": {}}


def test_real_player_data_is_still_the_source():
    assert len(data52.PLAYERS) == 96
    names = {p["name"] for p in data52.PLAYERS}
    assert {"Virat Kohli", "Jasprit Bumrah", "Babar Azam", "Joe Root"} <= names
    assert not any("Aarav" in name or "Rohan" in name for name in names)


def test_new_game_starts_in_season_with_six_free_starters():
    state = tycoon.new_state(lobby("START"))
    assert state["ruleset"] == tycoon.RULES_VERSION
    assert state["phase"] == "season"
    assert not state.get("pending")
    assert "draft" not in state["phase"]
    for f in state["franchises"].values():
        assert len(f["squad"]) == 6
        assert len(f["tactics"]) == 5
        assert "pressure" in f["tactics"]
        assert f["balance"] == 1500


def test_squad_ratings_reward_specialists():
    pmap = {p["id"]: p for p in data52.PLAYERS}
    ratings = tycoon.squad_ratings(tycoon.starter_squad(), pmap)
    assert ratings["bat"] > 240
    assert ratings["bowl"] > 240
    assert ratings["field"] > 200


def test_roll_uses_one_die_and_pays_for_passing_start():
    state = tycoon.new_state(lobby("ROLL1"))
    state["franchises"]["p0"]["pos"] = 51
    before = state["franchises"]["p0"]["balance"]
    pending = tycoon.roll(state, "p0")
    assert 1 <= state["dice"][0] <= 6
    assert state["franchises"]["p0"]["pos"] == (51 + state["dice"][0]) % 52
    assert state["franchises"]["p0"]["balance"] >= before + 200
    assert pending is not None
    assert state["pending"] is pending


def test_managers_start_with_distinct_starter_squads():
    state = tycoon.new_state(lobby("UNIQUE", 3))
    squads = [set(f["squad"]) for f in state["franchises"].values()]
    assert all(len(squad) == 6 for squad in squads)
    assert all(not (a & b) for i, a in enumerate(squads) for b in squads[i + 1:])


def test_market_tile_signs_a_real_cricketer_and_spends_fc():
    pos = next(t["position"] for t in data52.BOARD if t["kind"] == "market")
    state = tycoon.new_state(lobby("SIGN1"))
    state["pending"] = {"type": "sign_player", "pid": "p0", "pos": pos,
                        "candidates": ["india_batsman_silver"], "price": 150}
    before = state["franchises"]["p0"]["balance"]
    message = tycoon.sign_player(state, "p0", "india_batsman_silver")
    assert "Rohit Sharma" in message
    assert "india_batsman_silver" in state["franchises"]["p0"]["squad"]
    assert state["franchises"]["p0"]["balance"] == before - 150
    assert state["pending"] is None


def test_duel_uses_both_secret_cards_and_sets_scorecard():
    state = tycoon.new_state(lobby("DUEL1"))
    pending = tycoon.roll(state, "p0")
    while pending is None or pending.get("type") != "duel":
        state["franchises"]["p0"]["pos"] = 0
        state["current_player_id"] = "p0"
        state["pending"] = None
        state["franchises"]["p1"]["pos"] = 1
        pending = {"type": "duel", "pid": "p0", "defender": "p1", "pos": 3,
                   "rent": 55, "pot": False, "cards": {}, "result": None,
                   "label": "Rent duel"}
        state["pending"] = pending
        break
    c0 = state["franchises"]["p0"]["tactics"][0]
    c1 = state["franchises"]["p1"]["tactics"][1]
    assert tycoon.submit_card(state, "p0", c0) is None
    result = tycoon.submit_card(state, "p1", c1)
    assert result and result["type"] == "result"
    card = result["scorecard"]
    assert 70 <= card["challenger"]["runs"] <= 250
    assert 0 <= card["defender"]["wickets"] <= 10
    assert result["winner_id"] in ("p0", "p1")
    assert result["paid"] > 0


def test_used_tactic_is_replaced_and_foreign_cards_are_rejected():
    state = tycoon.new_state(lobby("CARD1"))
    hand = state["franchises"]["p0"]["tactics"]
    before_hand = list(hand)
    foreign = next(card for card in tycoon.TACTICS if card not in hand)
    state["pending"] = {"type": "duel", "pid": "p0", "defender": "p1", "pos": None,
                        "rent": 50, "pot": True, "cards": {}, "result": None,
                        "label": "Practice"}
    assert tycoon.submit_card(state, "p0", foreign) is None
    assert hand == before_hand
    chosen = hand[0]
    assert tycoon.submit_card(state, "p0", chosen) is None
    assert len(hand) == 5
    assert chosen not in hand
    assert state["pending"]["cards"]["p0"] == chosen


def test_pitch_changes_tactic_strength():
    card = "powerplay"
    results = {}
    for pitch in ("flat", "slow"):
        state = tycoon.new_state(lobby(f"PITCH-{pitch}"))
        state["pitch"] = pitch
        state["pending"] = {"type": "duel", "pid": "p0", "defender": "p1", "pos": None,
                            "rent": 50, "pot": True, "cards": {"p0": card, "p1": "pressure"},
                            "result": None, "label": "Pitch test"}
        results[pitch] = tycoon.resolve_duel(state)["scorecard"]["challenger"]["run_mod"]
    assert results["flat"] > results["slow"]


def test_sealed_auction_hides_competing_bids_from_the_snapshot():
    state = tycoon.new_state(lobby("BID1"))
    state["auction"] = {"id": "a1", "player_id": "india_batsman_gold",
                        "base_price": 100, "bids": {"p0": 120, "p1": 150},
                        "passed": [], "opened_by": "p0", "revealed": False}
    from app.tycoon_api import TycoonRoom

    manager.rooms["r-BID1"] = TycoonRoom("r-BID1", "BID1", "p0", 1.0)
    room = manager.rooms["r-BID1"]
    room.members.update(state["franchises"].copy())
    room.state = state
    snap = room.snapshot("p0")
    assert snap["auction"]["bids"] == {}
    assert snap["auction"]["my_bid"] == 120
    assert "player" in snap["auction"]
    manager.rooms.pop("r-BID1", None)


def test_buying_a_ground_stores_its_id_and_raises_brand_value():
    tile = next(t for t in data52.BOARD if t["kind"] == "stadium")
    state = tycoon.new_state(lobby("GROUND"))
    before = tycoon.brand_value(state["franchises"]["p0"], state)
    state["pending"] = {"type": "buy_stadium", "pid": "p0", "pos": tile["position"],
                        "price": int(tile["price"]), "title": tile["name"]}
    tycoon.buy_stadium(state, "p0", tile["position"])
    assert tile["id"] in state["franchises"]["p0"]["stadiums"]
    assert state["ownership"][str(tile["position"])] == "p0"
    assert tycoon.brand_value(state["franchises"]["p0"], state) > before


def test_brand_value_rewards_grounds_players_and_duels():
    state = tycoon.new_state(lobby("VALUE"))
    base = tycoon.brand_value(state["franchises"]["p0"], state)
    state["franchises"]["p0"]["stadiums"] = ["melbourne"]
    state["franchises"]["p0"]["duels_won"] = 2
    boosted = tycoon.brand_value(state["franchises"]["p0"], state)
    assert boosted > base + 700


def test_api_quick_match_returns_session_envelope():
    with TestClient(app) as client:
        quick = client.post("/api/fg/quick", json={
            "name": "Solo Manager", "avatar": "🦁", "color": "#c8a24b",
        }).json()
        assert quick["code"]
        assert quick["room_id"]
        assert quick["player_id"]
        assert quick["state"]["started"] is True
        assert quick["state"]["ruleset"] == tycoon.RULES_VERSION
        assert len(quick["state"]["franchises"]) == 3


def test_api_settings_clamp_to_supported_limits():
    with TestClient(app) as client:
        created = client.post("/api/fg/rooms", json={
            "name": "Host", "avatar": "🦁", "color": "#c8a24b",
            "settings": {"max_players": 99, "season_rounds": 99, "starting_credits": 1},
        }).json()
        code, token = created["code"], created["player_id"]
        settings = created["state"]["settings"]
        assert settings["max_players"] == 6
        assert settings["season_rounds"] == 16
        assert settings["starting_credits"] == 500

        updated = client.post(f"/api/fg/rooms/{code}/settings", json={
            "player_id": token, "settings": {"max_players": 1},
        }).json()
        assert updated["settings"]["max_players"] == 2


def test_api_host_data_edit_is_room_local():
    with TestClient(app) as client:
        created = client.post("/api/fg/rooms", json={
            "name": "Host", "avatar": "🦁", "color": "#c8a24b",
        }).json()
        code, token = created["code"], created["player_id"]
        player = client.get("/api/fg/gamedata").json()["players"][0]
        updated = client.post(f"/api/fg/rooms/{code}/data", json={
            "player_id": token,
            "overrides": {"players": {player["id"]: {"batting": 99, "name": "Edited Name"}}},
        }).json()
        edited = next(p for p in updated["gamedata"]["players"] if p["id"] == player["id"])
        assert edited["batting"] == 99
        assert edited["name"] == "Edited Name"
        pristine = next(p for p in client.get("/api/fg/gamedata").json()["players"]
                        if p["id"] == player["id"])
        assert pristine["batting"] != 99


def test_api_create_start_and_roll_use_new_rules():
    with TestClient(app) as client:
        created = client.post("/api/fg/rooms", json={
            "name": "API Host", "avatar": "🦁", "color": "#c8a24b",
        }).json()
        code, token = created["code"], created["player_id"]
        assert created["state"]["started"] is False
        assert created["state"]["ruleset"] == tycoon.RULES_VERSION

        joined = client.post("/api/fg/rooms/join", json={
            "code": code, "name": "API Friend", "avatar": "🦅", "color": "#4fd1c5",
        }).json()
        assert joined["player_id"] != token

        started = client.post(f"/api/fg/rooms/{code}/start", json={"player_id": token}).json()
        assert started["phase"] == "season"
        assert len(started["franchises"]) == 2
        assert all(len(f["squad"]) == 6 for f in started["franchises"].values())

        with client.websocket_connect(f"/api/fg/ws?code={code}&token={token}") as ws:
            update = ws.receive_json()
            assert update["you"] == token
            ws.send_json({"action": "roll"})
            rolled = ws.receive_json()
            assert 1 <= rolled["state"]["dice"][0] <= 6
            assert rolled["state"]["franchises"][token]["pos"] > 0
            assert rolled["state"]["pending"] is not None


def test_result_scorecard_can_be_closed_by_either_viewer():
    state = tycoon.new_state(lobby("ACK"))
    state["pending"] = {"type": "result", "pid": "p0", "viewers": ["p0", "p1"]}
    assert tycoon.next_turn(state, "p1") == "Turn passed."
    assert state["pending"] is None
