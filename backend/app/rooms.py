"""Room registry: lobby lifecycle, host controls and reconnection tokens."""

from __future__ import annotations

import secrets
import string
import time
from dataclasses import dataclass

from . import config
from .game.engine import GameEngine
from .models import GameState, Player


@dataclass
class Room:
    id: str
    code: str
    host_id: str
    created_at: float
    state: GameState
    engine: GameEngine

    def public(self) -> dict:
        return self.state.to_dict()


class RoomManager:
    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}
        self.by_code: dict[str, str] = {}

    @staticmethod
    def _code() -> str:
        alphabet = string.ascii_uppercase.replace("O", "").replace("I", "")
        return "".join(secrets.choice(alphabet) for _ in range(6))

    def create(self, name: str, avatar: str, color: str) -> Room:
        room_id = secrets.token_urlsafe(12)
        code = self._code()
        while code in self.by_code:
            code = self._code()
        player_id = secrets.token_urlsafe(12)
        state = GameState(room_id=room_id, code=code)
        host = Player(id=player_id, name=name, avatar=avatar, color=color,
                      is_host=True, ready=True,
                      money=config.STARTING_MONEY)
        state.players[player_id] = host
        room = Room(id=room_id, code=code, host_id=player_id,
                    created_at=time.time(), state=state, engine=GameEngine(state))
        self.rooms[room_id] = room
        self.by_code[code] = room_id
        return room

    def join(self, code: str, name: str, avatar: str, color: str) -> tuple[Room, str]:
        room_id = self.by_code.get(code.strip().upper())
        room = self.rooms.get(room_id) if room_id else None
        if room is None:
            raise ValueError("Room not found")
        if room.state.started:
            raise ValueError("Game has already started")
        if len(room.state.players) >= config.MAX_PLAYERS:
            raise ValueError("Room is full")
        player_id = secrets.token_urlsafe(12)
        room.state.players[player_id] = Player(
            id=player_id, name=name, avatar=avatar, color=color,
            money=config.STARTING_MONEY,
        )
        return room, player_id

    def add_bots(self, room: Room, count: int = 1,
                 strategy: str = "smart") -> list[str]:
        """Add AI managers to a lobby. Returns their player tokens."""
        from .bots import BOT_AVATARS, BOT_COLORS, BOT_NAMES

        if room.state.started:
            raise ValueError("Bots can only join before the match starts")
        if strategy not in ("smart", "random"):
            raise ValueError("Strategy must be 'smart' or 'random'")
        free = config.MAX_PLAYERS - len(room.state.players)
        if count > free:
            raise ValueError(f"Only {free} bot slot(s) available in this room")
        used_names = {p.name for p in room.state.players.values()}
        added: list[str] = []
        for i in range(count):
            name = next((n for n in BOT_NAMES if n not in used_names),
                        f"Bot {len(added) + 1}")
            used_names.add(name)
            player_id = secrets.token_urlsafe(12)
            slot = len(added)
            room.state.players[player_id] = Player(
                id=player_id, name=name,
                avatar=BOT_AVATARS[slot % len(BOT_AVATARS)],
                color=BOT_COLORS[slot % len(BOT_COLORS)],
                money=config.STARTING_MONEY,
                ready=True, connected=True,
                is_bot=True, bot_strategy=strategy,
            )
            added.append(player_id)
        return added

    def get_by_code(self, code: str) -> Room | None:
        return self.rooms.get(self.by_code.get(code.strip().upper(), ""))

    def get(self, room_id: str) -> Room | None:
        return self.rooms.get(room_id)

    def find_player_room(self, player_id: str) -> Room | None:
        for room in self.rooms.values():
            if player_id in room.state.players:
                return room
        return None

    def set_ready(self, room: Room, player_id: str, ready: bool) -> None:
        player = room.state.players.get(player_id)
        if not player:
            raise ValueError("Player not found")
        player.ready = bool(ready)

    def start(self, room: Room, player_id: str) -> None:
        if room.host_id != player_id:
            raise ValueError("Only the host can start the game")
        room.engine.start()

    def remove(self, room: Room, player_id: str) -> None:
        if room.state.started:
            room.state.players[player_id].connected = False
            return
        room.state.players.pop(player_id, None)
        if player_id == room.host_id and room.state.players:
            room.host_id = next(iter(room.state.players))
            room.state.players[room.host_id].is_host = True
        if not room.state.players:
            self.by_code.pop(room.code, None)
            self.rooms.pop(room.id, None)

    def restore(self, state: GameState, host_id: str, created_at: float) -> None:
        room = Room(id=state.room_id, code=state.code, host_id=host_id,
                    created_at=created_at, state=state, engine=GameEngine(state))
        self.rooms[room.id] = room
        self.by_code[room.code] = room.id


manager = RoomManager()
