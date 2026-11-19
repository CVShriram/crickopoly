"""Deterministic tests for coin gifting and the global leaderboard."""

from __future__ import annotations

import pytest

from app import config, persistence
from .conftest import make_engine, make_state


def test_gift_coins_transfers_once_per_round():
    engine, state = make_engine(2)
    sender = state.players["p0"]
    receiver = state.players["p1"]
    state.order = ["p0", "p1"]
    state.current_index = 0
    state.phase = "await_roll"

    engine.take_events()
    engine.gift_coins("p0", "p1", 250)

    assert sender.money == config.STARTING_MONEY - 250
    assert receiver.money == config.STARTING_MONEY + 250
    assert sender.stats["coins_gifted"] == 250
    assert receiver.stats["coins_received"] == 250
    assert sender.gift_round == state.round
    assert any(event["type"] == "coins_gifted" for event in engine.take_events())

    with pytest.raises(ValueError, match="once per round"):
        engine.gift_coins("p0", "p1", 50)


def test_gift_coins_rejects_invalid_transfers():
    engine, state = make_engine(2)
    state.order = ["p0", "p1"]
    state.current_index = 0
    state.phase = "await_roll"
    sender = state.players["p0"]

    with pytest.raises(ValueError):
        engine.gift_coins("p0", "p0", 100)
    with pytest.raises(ValueError):
        engine.gift_coins("p0", "p1", config.GIFT_MIN_COINS - 1)
    with pytest.raises(ValueError):
        engine.gift_coins("p0", "p1", sender.money + 1)
    # A low balance leaves no room inside the configured max to preserve the
    # reserve, so the reserve guard must reject an otherwise bounded gift.
    sender.money = 300
    with pytest.raises(ValueError, match="reserve"):
        engine.gift_coins("p0", "p1", 250)

    sender.debt = {"amount": 50, "reason": "test"}
    with pytest.raises(ValueError, match="active and debt-free"):
        engine.gift_coins("p0", "p1", 100)


def test_global_leaderboard_records_each_match_once(monkeypatch, tmp_path):
    monkeypatch.setattr(persistence, "DB_PATH", str(tmp_path / "ladder.db"))
    persistence.init_db()

    state = make_state(2)
    state.finished_at = "2026-01-01T00:00:00Z"
    state.winner_id = "p0"
    state.players["p0"].runs = 120
    state.players["p0"].money = 1450
    state.players["p0"].stats["coins_gifted"] = 100
    state.players["p1"].runs = 40

    persistence.save_room(state, "p0", 1000.0)
    # Repeated saves after elimination must not duplicate ladder rows.
    persistence.save_room(state, "p0", 1000.0)

    rows = persistence.global_leaderboard()
    assert [row["name"] for row in rows] == ["Player 0", "Player 1"]
    assert rows[0]["matches_played"] == 1
    assert rows[0]["wins"] == 1
    assert rows[0]["runs"] == 120
    assert rows[0]["gifts_sent"] == 100
    assert rows[1]["wins"] == 0


def test_bots_are_excluded_from_global_leaderboard_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr(persistence, "DB_PATH", str(tmp_path / "ladder.db"))
    persistence.init_db()

    state = make_state(2)
    state.finished_at = "2026-01-01T00:00:00Z"
    state.winner_id = "p0"
    state.players["p1"].is_bot = True
    persistence.save_room(state, "p0", 1000.0)

    assert len(persistence.global_leaderboard()) == 1
    assert len(persistence.global_leaderboard(include_bots=True)) == 2
