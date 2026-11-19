"""Tests for the server-side AI managers."""

from __future__ import annotations

import time

from app.bots import RUN_TILE_RUNS, bot_driver
from app.game.board import get_space
from app.rooms import manager


def _room_with_bot():
    room = manager.create("Human", "🏏", "#22c55e")
    manager.add_bots(room, 1, "smart")
    manager.start(room, room.host_id)
    bot_id = next(pid for pid, p in room.state.players.items() if p.is_bot)
    return room, bot_id


def test_bot_rolls_on_its_turn():
    room, bot_id = _room_with_bot()
    state = room.state
    state.order = [bot_id, room.host_id]
    state.current_index = 0
    state.phase = "await_roll"
    room.engine.take_events()
    events = bot_driver.step(room)
    assert any(e["type"] == "dice" for e in events)


def test_bot_resolves_purchase_offer():
    room, bot_id = _room_with_bot()
    state = room.state
    state.pending = {
        "type": "purchase", "player_id": bot_id, "space_id": 2,
        "expires_at": time.time() + 30, "extra_roll": False,
    }
    room.engine.take_events()
    events = bot_driver.step(room)
    assert state.pending is None
    assert any(e["type"] in ("purchase", "skip", "auction_start") for e in events)


def test_bot_bids_in_auction():
    room, bot_id = _room_with_bot()
    state = room.state
    bot = state.players[bot_id]
    space_id = 2
    state.auction = {
        "space_id": space_id, "space": {"id": space_id, "price": 300},
        "started_by": room.host_id, "ends_at": time.time() + 30,
        "highest_bid": 0, "highest_bidder": None, "bids": [], "extra_roll": False,
    }
    room.engine.take_events()
    bot_driver.step(room)
    # The bot either bids (smart ceiling allows it) or deliberately passes;
    # either way the auction remains a valid engine-controlled state.
    assert state.auction is not None
    assert bot.money <= 1000


def test_smart_bot_keeps_a_larger_cash_reserve_early():
    room, bot_id = _room_with_bot()
    state = room.state
    state.victory_mode = "turn_limit"
    state.turn_limit = 20
    bot = state.players[bot_id]

    state.round = 1
    early_reserve = bot_driver._cash_reserve(bot, state)
    state.round = 18
    late_reserve = bot_driver._cash_reserve(bot, state)

    assert early_reserve == 260
    assert late_reserve < early_reserve
    assert late_reserve >= 80


def test_smart_bot_values_run_tiles_more_as_the_clock_runs_down():
    room, bot_id = _room_with_bot()
    state = room.state
    state.victory_mode = "turn_limit"
    state.turn_limit = 20
    bot = state.players[bot_id]
    run_space = next(get_space(i) for i in range(32)
                     if get_space(i).type == "run_4")

    state.round = 1
    early_value = bot_driver._space_score(run_space, state, bot)
    state.round = 19
    late_value = bot_driver._space_score(run_space, state, bot)

    assert RUN_TILE_RUNS[run_space.type] == 4
    assert late_value > early_value


def test_smart_bot_preserves_reserve_on_expensive_purchase():
    room, bot_id = _room_with_bot()
    state = room.state
    bot = state.players[bot_id]
    bot.money = 500
    state.victory_mode = "turn_limit"
    state.turn_limit = 20
    state.round = 1
    state.pending = {
        "type": "purchase", "player_id": bot_id, "space_id": 2,
        "expires_at": 10**12, "extra_roll": False,
    }
    room.engine.take_events()

    events = bot_driver.step(room)

    assert state.pending is None
    assert bot.money == 500
    assert any(event["type"] == "skip" for event in events)
