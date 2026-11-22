"""Focused tests for Auction + Tournament (ruleset 7)."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import persistence as db
from app.game import auctiontournament as tycoon
from app.game import data52
from app.main import app
from app.tycoon_api import _rows, _save, clean_settings, hub, manager, saved_summaries


STATE_KEYS = {
    "ruleset", "started", "finished", "phase", "turn", "order",
    "turn_index", "current_player_id", "lot_index", "lots", "budget",
    "current_lot", "bids", "last_result", "pending", "franchises",
    "fixtures", "match_index", "match_results", "settings",
    "data_overrides", "log", "events", "winner_id", "host_id", "last_event",
}


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


def client_without_ticks() -> TestClient:
    """A client whose bot loop is not running; bots are driven explicitly."""
    return TestClient(app)


def queue_ids(state: dict) -> list[str]:
    return [str(lot["id"]) for lot in tycoon._lot_queue_for(state)]


def expected_side(ids: list[str], captain: str | None, tactic: str,
                  overrides: dict | None = None) -> tuple[int, int, int]:
    players = {str(p["id"]): p for p in data52.merged_players(overrides)}
    batting = sorted((int(players[i]["batting"]) for i in ids), reverse=True)[:6]
    bowling = sorted((int(players[i]["bowling"]) for i in ids), reverse=True)[:3]
    runs = sum(batting) + tycoon.TACTICS[tactic]["runs"]
    wickets = sum(bowling) // 4 + tycoon.TACTICS[tactic]["wickets"]
    if captain and captain in ids:
        runs += 2 * int(players[captain]["batting"])
        wickets += int(players[captain]["bowling"]) // 10
    return runs, wickets, runs - wickets * 4


# ---------------------------------------------------------------------------
# Engine: setup, lots and table
# ---------------------------------------------------------------------------

def test_rules_constants_and_exact_state_contract():
    assert tycoon.RULES_VERSION == 7
    assert tycoon.DEFAULT_SETTINGS == {"max_players": 6, "budget": 1200, "lots": 18}
    assert set(tycoon.STATE_KEYS) == STATE_KEYS

    state = tycoon.new_state(lobby("SETUP", 4, {
        "max_players": 99, "budget": 9999, "lots": 99, "difficulty": "hard",
    }))
    assert set(state) == STATE_KEYS
    assert state["ruleset"] == 7
    assert state["started"] is True
    assert state["finished"] is False
    assert state["phase"] == "auction"
    assert state["turn"] == 1
    assert state["turn_index"] == 0
    assert state["current_player_id"] == "p0"
    assert state["order"] == ["p0", "p1", "p2", "p3"]
    assert state["lot_index"] == 0
    assert state["lots"] == 30
    assert state["budget"] == 3000
    assert state["settings"] == {
        "max_players": 6, "budget": 3000, "lots": 30, "difficulty": "hard",
    }
    assert state["bids"] == {"p0": None, "p1": None, "p2": None, "p3": None}
    assert state["last_result"] is None
    assert state["pending"] is None
    assert state["fixtures"] == []
    assert state["match_index"] == 0
    assert state["match_results"] == []
    assert state["winner_id"] is None
    assert state["host_id"] == "h-SETUP"
    assert state["data_overrides"] == {}

    ids = queue_ids(state)
    assert len(ids) == 30
    assert len(set(ids)) == 30
    assert state["current_lot"]["id"] == ids[0]
    assert isinstance(state["current_lot"], dict)
    assert {"id", "name", "batting", "bowling"} <= set(state["current_lot"])
    assert state["last_event"]["type"] == "game"
    assert state["log"] and state["events"]

    for pid, franchise in state["franchises"].items():
        assert set(franchise) == set(tycoon.FRANCHISE_KEYS)
        assert franchise == {
            "id": pid, "name": f"Manager {pid[1:]}", "avatar": "🏏",
            "color": "#c8a24b", "is_bot": False, "fc": 3000,
            "squad": [], "captain": None, "tactic": "balanced",
            "points": 0, "total_score": 0, "wins": 0, "losses": 0,
        }

    original_name = state["current_lot"]["name"]
    state["current_lot"]["name"] = "Mutated"
    assert data52.PLAYERS_BY_ID[ids[0]]["name"] == original_name


def test_lot_queue_is_deterministic_for_host_and_order():
    first = tycoon.new_state(lobby("SEED"))
    second = tycoon.new_state(lobby("SEED"))
    other = tycoon.new_state(lobby("OTHER"))
    assert queue_ids(first) == queue_ids(second)
    assert queue_ids(first) != queue_ids(other)
    assert first["current_lot"]["id"] == second["current_lot"]["id"]


def test_standings_sort_points_then_total_score_then_fc():
    state = tycoon.new_state(lobby("TABLE", 3))
    state["franchises"]["p0"].update(points=4, total_score=100, fc=100, squad=["a", "b"])
    state["franchises"]["p1"].update(points=4, total_score=100, fc=250)
    state["franchises"]["p2"].update(points=4, total_score=150, fc=10)

    table = tycoon.standings(state)
    assert [row["id"] for row in table] == ["p2", "p1", "p0"]
    assert [row["rank"] for row in table] == [1, 2, 3]
    assert table[0]["squad_size"] == 0
    assert table[2]["squad_size"] == 2
    for row in table:
        assert set(row) == set(tycoon.STANDING_KEYS)


# ---------------------------------------------------------------------------
# Engine: sealed bidding
# ---------------------------------------------------------------------------

def test_sealed_bids_resolve_automatically_and_winner_pays():
    state = tycoon.new_state(lobby("BID", 3))
    player_id = state["current_lot"]["id"]

    tycoon.bid(state, "p0", 100)
    assert state["pending"] is None
    assert state["last_result"] is None
    assert state["bids"]["p0"] == {"player_id": player_id, "amount": 100}
    assert all("100" not in entry["text"] for entry in state["log"])

    tycoon.bid(state, "p1", 250)
    assert state["pending"] is None
    tycoon.bid(state, "p2", 50)  # last manager in -> automatic resolution

    result = state["last_result"]
    assert result == {
        "type": "lot",
        "player_id": player_id,
        "name": state["current_lot"]["name"],
        "winner_id": "p1",
        "amount": 250,
        "bids": {"p0": 100, "p1": 250, "p2": 50},
    }
    assert state["pending"] == {"type": "next"}
    assert state["franchises"]["p1"]["fc"] == state["budget"] - 250
    assert state["franchises"]["p1"]["squad"] == [player_id]
    assert state["franchises"]["p0"]["fc"] == state["budget"]
    assert state["franchises"]["p2"]["squad"] == []
    assert any(entry["kind"] == "lot" and "sold" in entry["text"] for entry in state["log"])

    with pytest.raises(ValueError, match="already been resolved"):
        tycoon.bid(state, "p0", 10)
    with pytest.raises(ValueError, match="already been resolved"):
        tycoon.resolve_lot(state)


def test_tie_break_prefers_earlier_manager_in_rotation():
    state = tycoon.new_state(lobby("TIE", 3))
    for pid in state["order"]:
        tycoon.bid(state, pid, 200)
    assert state["last_result"]["winner_id"] == "p0"
    assert state["last_result"]["amount"] == 200
    assert state["franchises"]["p0"]["squad"] == [state["current_lot"]["id"]]
    assert state["franchises"]["p1"]["squad"] == []


def test_passes_and_bid_validation():
    state = tycoon.new_state(lobby("PASS", 2))
    p0, p1 = state["order"]

    with pytest.raises(ValueError, match="not in this game"):
        tycoon.bid(state, "outsider", 10)
    with pytest.raises(ValueError, match="whole number"):
        tycoon.bid(state, p0, 10.5)
    with pytest.raises(ValueError, match="between 0 and"):
        tycoon.bid(state, p0, -1)
    with pytest.raises(ValueError, match="between 0 and"):
        tycoon.bid(state, p0, state["budget"] + 1)

    tycoon.bid(state, p0, 0)
    with pytest.raises(ValueError, match="already bid"):
        tycoon.bid(state, p0, 10)
    tycoon.bid(state, p1, 0)

    assert state["last_result"]["winner_id"] is None
    assert state["last_result"]["amount"] == 0
    assert state["last_result"]["bids"] == {p0: 0, p1: 0}
    assert all(f["squad"] == [] and f["fc"] == state["budget"]
               for f in state["franchises"].values())
    assert any(entry["kind"] == "lot" and "unsigned" in entry["text"]
               for entry in state["log"])


def test_next_step_advances_lots_then_enters_tournament():
    fresh = tycoon.new_state(lobby("NEXT0", 2))
    with pytest.raises(ValueError, match="waiting for NEXT"):
        tycoon.next_step(fresh, fresh["order"][0])

    state = tycoon.new_state(lobby("NEXT", 3, {"lots": 8}))
    first_lot = state["current_lot"]["id"]
    for pid in state["order"]:
        tycoon.bid(state, pid, 10)
    tycoon.next_step(state, "p0")
    assert state["lot_index"] == 1
    assert state["current_lot"]["id"] == queue_ids(state)[1]
    assert state["current_lot"]["id"] != first_lot
    assert state["bids"] == {"p0": None, "p1": None, "p2": None}
    assert state["last_result"] is None
    assert state["pending"] is None
    assert state["turn"] == 2
    assert state["current_player_id"] == "p1"

    for pid in state["order"]:
        tycoon.bid(state, pid, 15)
    # Eight lots means seven more advances; run them with fresh bids each time.
    for _ in range(6):
        tycoon.next_step(state, "p0")
        for pid in state["order"]:
            tycoon.bid(state, pid, 15)
    tycoon.next_step(state, "p0")

    assert state["phase"] == "tournament"
    assert state["fixtures"] == [["p0", "p1"], ["p0", "p2"], ["p1", "p2"]]
    assert state["match_index"] == 0
    assert state["match_results"] == []
    assert state["current_lot"] is None
    assert state["bids"] == {}
    assert state["last_result"] is None
    assert state["pending"] is None
    assert any(entry["kind"] == "tournament" for entry in state["log"])


# ---------------------------------------------------------------------------
# Engine: tournament scoring
# ---------------------------------------------------------------------------

def test_match_scoring_uses_captain_squad_and_tactic():
    state = tycoon.new_state(lobby("MATCH", 2))
    a, b = state["order"]
    top = [
        "new_zealand_batsman_gold", "india_batsman_gold",
        "south_africa_wicketkeeper_gold", "west_indies_batsman_gold",
        "sri_lanka_batsman_gold", "england_allrounder_gold",
    ]
    bottom = [
        "sri_lanka_bowler_bronze", "west_indies_bowler_silver",
        "india_bowler_bronze", "pakistan_bowler_bronze",
        "australia_bowler_bronze", "new_zealand_bowler_bronze",
    ]
    state["franchises"][a]["squad"] = list(top)
    state["franchises"][a]["captain"] = top[0]
    state["franchises"][a]["tactic"] = "attack"
    state["franchises"][b]["squad"] = list(bottom)
    state["franchises"][b]["tactic"] = "balanced"
    state["phase"] = "tournament"
    state["fixtures"] = [[a, b]]
    state["match_index"] = 0
    state["pending"] = {"type": "next"}

    a_expected = expected_side(top, top[0], "attack")
    b_expected = expected_side(bottom, None, "balanced")
    tycoon.next_step(state, a)

    result = state["last_result"]
    assert (result["a_runs"], result["a_wickets"], result["a_score"]) == a_expected
    assert (result["b_runs"], result["b_wickets"], result["b_score"]) == b_expected
    assert result["winner_id"] == a
    assert result == state["match_results"][-1]
    assert state["franchises"][a]["points"] == 2
    assert state["franchises"][a]["wins"] == 1
    assert state["franchises"][a]["total_score"] == a_expected[2]
    assert state["franchises"][b]["points"] == 0
    assert state["franchises"][b]["losses"] == 1
    assert state["franchises"][b]["total_score"] == b_expected[2]
    assert state["match_index"] == 1
    assert state["pending"] == {"type": "next"}


def test_tie_awards_one_point_each():
    state = tycoon.new_state(lobby("DRAW", 2))
    a, b = state["order"]
    squad = ["new_zealand_batsman_gold", "india_batsman_gold"]
    for pid in (a, b):
        state["franchises"][pid]["squad"] = list(squad)
        state["franchises"][pid]["captain"] = squad[0]
        state["franchises"][pid]["tactic"] = "defensive"
    state["phase"] = "tournament"
    state["fixtures"] = [[a, b]]
    state["pending"] = {"type": "next"}

    tycoon.next_step(state, a)
    assert state["last_result"]["winner_id"] is None
    assert state["franchises"][a]["points"] == 1
    assert state["franchises"][b]["points"] == 1
    assert state["franchises"][a]["wins"] == 0
    assert state["franchises"][b]["losses"] == 0


def test_captain_and_tactic_validation():
    state = tycoon.new_state(lobby("SETUP2", 2))
    a = state["order"][0]
    with pytest.raises(ValueError, match="own squad"):
        tycoon.set_captain(state, a, "india_batsman_gold")
    with pytest.raises(ValueError, match="Unknown tactic"):
        tycoon.set_tactic(state, a, "lucky")

    player_id = state["current_lot"]["id"]
    tycoon.bid(state, a, 10)
    tycoon.bid(state, state["order"][1], 0)
    tycoon.next_step(state, a)  # advance to lot 2, still in auction
    state["franchises"][a]["squad"] = [player_id]
    assert tycoon.set_captain(state, a, player_id) == "ok"
    assert state["franchises"][a]["captain"] == player_id
    assert tycoon.set_captain(state, a, "") == "ok"
    assert state["franchises"][a]["captain"] is None
    assert tycoon.set_tactic(state, a, "attack") == "ok"
    assert state["franchises"][a]["tactic"] == "attack"


def test_full_round_robin_completes_with_a_winner():
    state = tycoon.new_state(lobby("FULL", 3, {"lots": 8}))
    order = state["order"]

    while state["phase"] == "auction":
        for pid in order:
            tycoon.bid(state, pid, 0)
        tycoon.next_step(state, order[0])

    assert state["phase"] == "tournament"
    first_match_index = state["match_index"]
    tycoon.next_step(state, order[0])
    assert state["match_index"] == first_match_index + 1
    assert state["pending"] == {"type": "next"}

    for _ in range(20):
        if state["phase"] == "over":
            break
        tycoon.next_step(state, order[0])
    else:
        raise AssertionError("round robin did not finish")

    assert state["finished"] is True
    assert state["phase"] == "over"
    assert len(state["match_results"]) == 3
    assert state["match_index"] == 3
    assert state["winner_id"] in order
    assert tycoon.standings(state)[0]["id"] == state["winner_id"]
    assert state["last_event"]["type"] == "finish"
    assert any(entry["kind"] == "final" for entry in state["log"])
    with pytest.raises(ValueError, match="complete"):
        tycoon.next_step(state, order[0])


# ---------------------------------------------------------------------------
# Bots
# ---------------------------------------------------------------------------

def test_bot_bids_quality_amounts_and_advances_tournament():
    state = tycoon.new_state(lobby("BOT", 3))
    for pid in state["order"]:
        state["franchises"][pid]["is_bot"] = True
    lot = state["current_lot"]
    quality = 40 + (int(lot["batting"]) + int(lot["bowling"])) // 4

    for index, pid in enumerate(state["order"]):
        tycoon.bot_action(state, pid)
        expected = min(state["budget"], max(0, quality + ((index * 7) % 15) - 7))
        assert state["bids"][pid] == {"player_id": lot["id"], "amount": expected}

    assert state["pending"] == {"type": "next"}
    before = json.dumps(state["bids"], sort_keys=True)
    tycoon.bot_action(state, state["order"][0])  # already resolved: no-op
    assert json.dumps(state["bids"], sort_keys=True) == before

    # Walk the remaining lots with all bots, then drive the tournament.
    while state["phase"] == "auction":
        tycoon.next_step(state, state["order"][0])
        if state["phase"] == "auction":
            for pid in state["order"]:
                tycoon.bot_action(state, pid)
    assert state["phase"] == "tournament"
    assert state["pending"] is None

    tycoon.bot_action(state, state["order"][0])  # no pending: no-op
    assert state["match_index"] == 0
    state["pending"] = {"type": "next"}
    tycoon.bot_action(state, state["order"][0])
    assert state["match_index"] == 1
    assert state["pending"] == {"type": "next"}


def test_auto_room_drives_all_bots_but_not_humans():
    client = client_without_ticks()
    created = client.post("/api/fg/rooms", json={
        "name": "Bot", "settings": {"lots": 8},
    }).json()
    code, host = created["code"], created["player_id"]
    guest = client.post("/api/fg/rooms/join", json={
        "code": code, "name": "Other Bot",
    }).json()["player_id"]
    client.post(f"/api/fg/rooms/{code}/start", json={"player_id": host})
    room = manager.by_code(code)
    for franchise in room.state["franchises"].values():
        franchise["is_bot"] = True

    asyncio.run(hub.auto_room(room))
    state = room.state
    assert state["finished"] is True
    assert state["phase"] == "over"
    assert len(state["match_results"]) == 1
    assert state["winner_id"] in state["order"]

    # Mixed room: bots bid, but a human still owns the NEXT reveal.
    mixed = client.post("/api/fg/rooms", json={
        "name": "Human", "settings": {"lots": 8},
    }).json()
    mcode, mhost = mixed["code"], mixed["player_id"]
    mguest = client.post("/api/fg/rooms/join", json={
        "code": mcode, "name": "Guest Bot",
    }).json()["player_id"]
    client.post(f"/api/fg/rooms/{mcode}/start", json={"player_id": mhost})
    mroom = manager.by_code(mcode)
    mroom.state["franchises"][mguest]["is_bot"] = True
    hub.dispatch(mroom, mhost, "bid", {"amount": 100})
    asyncio.run(hub.auto_room(mroom))
    assert mroom.state["bids"][mhost]["amount"] == 100
    assert mroom.state["bids"][mguest] is not None
    assert mroom.state["pending"] == {"type": "next"}
    assert mroom.state["lot_index"] == 0


# ---------------------------------------------------------------------------
# API integration
# ---------------------------------------------------------------------------

def test_api_rules_settings_dispatch_and_sealed_bid_concealment():
    client = client_without_ticks()
    rules = client.get("/api/fg/gamedata").json()["rules"]
    assert rules == {
        "ruleset": 7, "budget": 1200, "lots": 18,
        "min_players": 2, "max_players": 6,
        "tactics": {
            "attack": {"runs": 25, "wickets": 0},
            "balanced": {"runs": 10, "wickets": -3},
            "defensive": {"runs": -5, "wickets": -8},
        },
    }

    created = client.post("/api/fg/rooms", json={
        "name": "Host",
        "settings": {"max_players": 99, "budget": 99999, "lots": 0,
                     "legacy_key": "keep"},
    }).json()
    code, host = created["code"], created["player_id"]
    assert created["state"]["settings"] == {
        "max_players": 6, "budget": 3000, "lots": 8, "legacy_key": "keep",
    }
    assert created["state"]["gamedata"]["rules"]["budget"] == 3000
    assert created["state"]["gamedata"]["rules"]["lots"] == 8

    updated = client.post(f"/api/fg/rooms/{code}/settings", json={
        "player_id": host, "settings": {"max_players": 1, "budget": 1, "lots": 999},
    }).json()
    assert updated["settings"]["max_players"] == 2
    assert updated["settings"]["budget"] == 600
    assert updated["settings"]["lots"] == 30
    assert updated["gamedata"]["rules"]["budget"] == 600
    assert updated["gamedata"]["rules"]["lots"] == 30

    guest = client.post("/api/fg/rooms/join", json={
        "code": code, "name": "Guest",
    }).json()["player_id"]
    client.post(f"/api/fg/rooms/{code}/start", json={"player_id": host})
    room = manager.by_code(code)
    state = room.state

    host_snap = room.snapshot(host)
    assert set(host_snap) == STATE_KEYS | {"gamedata", "standings", "you"}
    assert host_snap["ruleset"] == 7
    assert host_snap["standings"] == tycoon.standings(state)
    assert host_snap["you"] == host
    assert set(host_snap["franchises"][host]) == set(tycoon.FRANCHISE_KEYS)

    assert hub.dispatch(room, host, "bid", {"amount": 100}) == "ok"
    host_snap = room.snapshot(host)
    guest_snap = room.snapshot(guest)
    assert host_snap["bids"][host]["amount"] == 100
    assert guest_snap["bids"][host]["amount"] is None
    assert host_snap["bids"][host]["player_id"] == state["current_lot"]["id"]
    assert guest_snap["bids"][host]["player_id"] == state["current_lot"]["id"]
    assert state["bids"][host]["amount"] == 100

    public = client.get(f"/api/fg/rooms/{code}").json()
    assert public["bids"][host]["amount"] is None
    assert all("100" not in entry["text"] for entry in public["log"])

    host_snap["bids"][host]["amount"] = 999
    assert state["bids"][host]["amount"] == 100

    assert hub.dispatch(room, guest, "bid", {"amount": 50}) == "ok"
    assert state["last_result"]["bids"] == {host: 100, guest: 50}
    for viewer in (host, guest):
        snap = room.snapshot(viewer)
        assert snap["last_result"] == state["last_result"]
        assert snap["bids"][host]["amount"] == 100
        assert snap["bids"][guest]["amount"] == 50

    player_id = state["current_lot"]["id"]
    stranger = next(p["id"] for p in data52.merged_players() if p["id"] != player_id)
    with pytest.raises(ValueError, match="own squad"):
        hub.dispatch(room, host, "set_captain", {"player_id": stranger})
    assert hub.dispatch(room, host, "set_tactic", {"tactic": "attack"}) == "ok"
    assert state["franchises"][host]["tactic"] == "attack"
    state["franchises"][host]["squad"] = [player_id]
    assert hub.dispatch(room, host, "set_captain", {"player_id": player_id}) == "ok"
    assert state["franchises"][host]["captain"] == player_id

    assert hub.dispatch(room, host, "next", {}) == "ok"
    assert state["lot_index"] == 1
    assert state["pending"] is None
    assert hub.dispatch(room, host, "ping", {}) == "pong"
    with pytest.raises(ValueError, match="Unknown action"):
        hub.dispatch(room, host, "roll", {})

    _save(room)
    summary = next(row for row in saved_summaries() if row["code"] == code)
    assert summary["lot_index"] == 1
    assert summary["match_index"] == 0
    assert summary["turn"] == state["turn"]
    assert summary["finished"] is False
    assert summary["matches"] == 0


def test_clean_settings_clamps_and_preserves_metadata():
    assert clean_settings(None) == {"max_players": 6, "budget": 1200, "lots": 18}
    assert clean_settings({
        "max_players": 99, "budget": 1, "lots": 1,
        "difficulty": "hard", "note": "keep",
    }) == {
        "max_players": 6, "budget": 600, "lots": 8,
        "difficulty": "hard", "note": "keep",
    }
    assert clean_settings({
        "max_players": "x", "budget": None, "lots": [],
    }) == {"max_players": 6, "budget": 1200, "lots": 18}


def test_host_override_is_room_local_and_used_by_match_scoring():
    client = client_without_ticks()
    created = client.post("/api/fg/rooms", json={"name": "Host"}).json()
    code, host = created["code"], created["player_id"]
    guest = client.post("/api/fg/rooms/join", json={
        "code": code, "name": "Guest",
    }).json()["player_id"]
    client.post(f"/api/fg/rooms/{code}/start", json={"player_id": host})
    room = manager.by_code(code)
    state = room.state
    lot_id = state["current_lot"]["id"]

    response = client.post(f"/api/fg/rooms/{code}/data", json={
        "player_id": host,
        "overrides": {"players": {lot_id: {"batting": 99, "name": "Edited Name"}}},
    })
    assert response.status_code == 200
    edited = next(p for p in response.json()["gamedata"]["players"] if p["id"] == lot_id)
    assert edited["batting"] == 99
    assert edited["name"] == "Edited Name"
    pristine = next(p for p in client.get("/api/fg/gamedata").json()["players"]
                    if p["id"] == lot_id)
    assert pristine["name"] != "Edited Name"
    assert state["current_lot"]["batting"] == 99
    assert state["current_lot"]["name"] == "Edited Name"

    denied = client.post(f"/api/fg/rooms/{code}/data", json={
        "player_id": guest, "overrides": {},
    })
    assert denied.status_code == 403

    other_id = next(p["id"] for p in data52.merged_players() if p["id"] != lot_id)
    state["franchises"][host]["squad"] = [lot_id]
    state["franchises"][host]["captain"] = lot_id
    state["franchises"][host]["tactic"] = "attack"
    state["franchises"][guest]["squad"] = [other_id]
    result = tycoon._simulate_match(state, host, guest)
    expected = expected_side([lot_id], lot_id, "attack", state["data_overrides"])
    assert (result["a_runs"], result["a_wickets"], result["a_score"]) == expected

    other = client.post("/api/fg/rooms", json={"name": "Clean"}).json()
    clean_players = other["state"]["gamedata"]["players"]
    clean = next(p for p in clean_players if p["id"] == lot_id)
    assert clean["name"] != "Edited Name"


def test_old_saved_rulesets_stay_hidden_and_invites_are_validated():
    stale = []
    for ruleset, room_id, code in (
        (3, "old-room-3", "OLD03"), (4, "old-room-4", "OLD04"),
        (5, "old-room-5", "OLD05"), (6, "old-room-6", "OLD06"),
    ):
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

    client = client_without_ticks()
    with pytest.raises(HTTPException) as exc:
        manager.by_code("NOPE0")
    assert exc.value.status_code == 404

    created = client.post("/api/fg/rooms", json={"name": "Invite"}).json()
    code = created["code"]
    with pytest.raises(HTTPException) as exc:
        manager.by_token(code, "not-a-member")
    assert exc.value.status_code == 403

    with client.websocket_connect(f"/api/fg/ws?code={code}&token=not-a-member") as ws:
        message = ws.receive_json()
        assert message["type"] == "error"
        assert "Invalid room link" in message["message"]
