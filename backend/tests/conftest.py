"""Shared test fixtures and deterministic RNG helpers."""

from __future__ import annotations

import random
from typing import Iterable

import pytest

from app import config
from app.game.engine import GameEngine
from app.models import GameState, Player


class ScriptedRng(random.Random):
    """RNG with scripted dice rolls and probability draws for reproducible tests."""

    def __init__(self, dice: Iterable[int] = (), rolls: Iterable[float] = (), seed: int = 7):
        super().__init__(seed)
        self.dice = list(dice)
        self.rolls = list(rolls)

    def randint(self, a: int, b: int) -> int:
        if self.dice:
            return self.dice.pop(0)
        return super().randint(a, b)

    def random(self) -> float:
        if self.rolls:
            return self.rolls.pop(0)
        return super().random()


@pytest.fixture
def rng() -> ScriptedRng:
    return ScriptedRng()


def make_player(pid: str, name: str, **kwargs) -> Player:
    return Player(
        id=pid, name=name, avatar="🏏", color="#22c55e",
        money=kwargs.pop("money", config.STARTING_MONEY),
        is_host=kwargs.pop("is_host", False),
        **kwargs,
    )


def make_state(count: int = 2) -> GameState:
    state = GameState(room_id="test-room", code="TEST01")
    for i in range(count):
        state.players[f"p{i}"] = make_player(f"p{i}", f"Player {i}", is_host=(i == 0))
    return state


def make_engine(count: int = 2, rng: random.Random | None = None,
                started: bool = True) -> tuple[GameEngine, GameState]:
    state = make_state(count)
    engine = GameEngine(state, rng or ScriptedRng())
    if started:
        engine.start()
    return engine, state


def give_property(state: GameState, owner_id: str, space_id: int):
    engine = GameEngine(state)
    asset = engine._create_asset(state.players[owner_id], space_id)
    state.players[owner_id].assets[asset.id] = asset
    return asset
