"""Regression tests for snapshot migration and live-tick isolation."""

from __future__ import annotations

from dataclasses import asdict

from app.persistence import _state_from_dict
from app.rooms import manager
from app.ws import hub

from .conftest import make_state


def test_legacy_player_defaults_are_merged_on_restore():
    state = make_state(1)
    player = state.players["p0"]
    player.effects = {"free_hit": 2}
    player.stats = {"six_runs": 7}

    payload = asdict(state)
    stored = payload["players"]["p0"]
    # Older snapshots only contained the keys they had touched. Missing keys
    # used to survive restore and then crash the live timer loop.
    stored["effects"] = {"free_hit": 2}
    stored["stats"] = {"six_runs": 7}

    restored = _state_from_dict(payload)
    restored_player = restored.players["p0"]

    assert restored_player.stats["six_runs"] == 7
    assert restored_player.stats["no_ball_bonus_runs"] == 0
    assert restored_player.stats["wickets_saved"] == 0
    assert restored_player.effects["free_hit"] == 2
    assert restored_player.effects["powerplay_rounds"] == 0


def test_tick_room_isolates_a_bad_snapshot(monkeypatch):
    room = manager.create("Legacy", "🏏", "#22c55e")
    try:
        manager.add_bots(room, 1)
        manager.start(room, room.host_id)
        room.state.turn_deadline = 10**12

        def broken_tick(now=None):
            raise KeyError("legacy statistic")

        monkeypatch.setattr(room.engine, "tick", broken_tick)
        assert hub.tick_room(room) == []
    finally:
        manager.rooms.pop(room.id, None)
        manager.by_code.pop(room.code, None)


def test_tick_room_advances_a_bot_turn():
    room = manager.create("BotTick", "🏏", "#22c55e")
    try:
        manager.add_bots(room, 1)
        manager.start(room, room.host_id)
        bot_id = next(pid for pid, player in room.state.players.items()
                      if player.is_bot)
        room.state.current_index = room.state.order.index(bot_id)
        room.state.turn_deadline = 10**12
        room.engine.take_events()

        events = hub.tick_room(room)
        assert any(event["type"] == "dice" for event in events)
    finally:
        manager.rooms.pop(room.id, None)
        manager.by_code.pop(room.code, None)
