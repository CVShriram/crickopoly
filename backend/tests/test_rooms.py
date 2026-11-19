"""Room lifecycle: create, join, ready, host controls and reconnection."""

from __future__ import annotations

import pytest

from app import config
from app.rooms import RoomManager


@pytest.fixture
def rooms() -> RoomManager:
    return RoomManager()


def test_create_and_join_two_players(rooms):
    room = rooms.create("Alice", "🏏", "#22c55e")
    room2, pid = rooms.join(room.code, "Bob", "🏏", "#3b82f6")
    assert room2 is room
    assert len(room.state.players) == 2
    assert pid != room.host_id
    assert rooms.get_by_code(room.code) is room


def test_four_players_join_and_fifth_rejected(rooms):
    room = rooms.create("A", "🏏", "#fff")
    for i in range(3):
        rooms.join(room.code, f"P{i}", "🏏", "#fff")
    assert len(room.state.players) == 4
    with pytest.raises(ValueError):
        rooms.join(room.code, "Late", "🏏", "#fff")


def test_join_unknown_code_rejected(rooms):
    with pytest.raises(ValueError):
        rooms.join("NOPE01", "X", "🏏", "#fff")


def test_ready_and_host_start(rooms):
    room = rooms.create("Host", "🏏", "#fff")
    _, pid = rooms.join(room.code, "Guest", "🏏", "#fff")
    assert all(p.ready for p in room.state.players.values()) is False
    rooms.set_ready(room, pid, True)
    with pytest.raises(ValueError):
        rooms.start(room, pid)
    rooms.start(room, room.host_id)
    assert room.state.started
    assert room.state.phase == "await_roll"


def test_join_after_start_rejected(rooms):
    room = rooms.create("Host", "🏏", "#fff")
    rooms.join(room.code, "Guest", "🏏", "#fff")
    rooms.start(room, room.host_id)
    with pytest.raises(ValueError):
        rooms.join(room.code, "Late", "🏏", "#fff")


def test_reconnect_finds_room_by_player_token(rooms):
    room = rooms.create("Host", "🏏", "#fff")
    _, pid = rooms.join(room.code, "Guest", "🏏", "#fff")
    assert rooms.find_player_room(pid) is room
    assert rooms.find_player_room("invalid-token") is None


def test_host_migration_when_host_leaves_lobby(rooms):
    room = rooms.create("Host", "🏏", "#fff")
    _, pid = rooms.join(room.code, "Guest", "🏏", "#fff")
    rooms.remove(room, room.host_id)
    assert room.host_id == pid
    assert room.state.players[pid].is_host


def test_starting_player_count_minimum(rooms):
    room = rooms.create("Only", "🏏", "#fff")
    with pytest.raises(ValueError):
        rooms.start(room, room.host_id)
