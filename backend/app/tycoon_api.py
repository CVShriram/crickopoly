"""HTTP + WebSocket API for Wicket Rush (ruleset 4).

Registered as /api/fg in main.py, replacing the old franchise router while
keeping the same room codes, sessions, save table and socket envelope.
"""

from __future__ import annotations

import asyncio
import json
import random
import string
import time
import uuid
from copy import deepcopy
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from . import persistence as db
from .game import data52, wicketrush as tycoon

FG = "/api/fg"
router = APIRouter(prefix=FG, tags=["crickopoly-tycoon"])


# ---------------------------------------------------------------------------
# Persistence (same table, versioned payloads)
# ---------------------------------------------------------------------------

def init_db() -> None:
    with db._lock:
        with db._connection() as conn:
            conn.execute(db._sql("""
                CREATE TABLE IF NOT EXISTS franchise_rooms (
                    room_id TEXT PRIMARY KEY,
                    code TEXT UNIQUE,
                    host_id TEXT,
                    created_at REAL,
                    updated_at REAL,
                    state_json TEXT
                )
            """))


init_db()


def _save(room: "TycoonRoom") -> None:
    payload = {
        "ruleset": tycoon.RULES_VERSION,
        "room_id": room.room_id,
        "code": room.code,
        "host_id": room.host_id,
        "created_at": room.created_at,
        "lobby": room.lobby,
        "state": room.state,
    }
    with db._lock:
        with db._connection() as conn:
            conn.execute(db._sql("""
                INSERT INTO franchise_rooms(room_id, code, host_id, created_at, updated_at, state_json)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(room_id) DO UPDATE SET
                    code=excluded.code, host_id=excluded.host_id,
                    updated_at=excluded.updated_at, state_json=excluded.state_json
            """), (room.room_id, room.code, room.host_id, room.created_at, time.time(),
                   json.dumps(payload)))


def _rows() -> list[dict]:
    with db._lock:
        with db._connection() as conn:
            rows = conn.execute(db._sql(
                "SELECT state_json FROM franchise_rooms ORDER BY updated_at DESC"
            )).fetchall()
    result: list[dict] = []
    for (payload,) in rows:
        try:
            data = json.loads(payload)
        except (TypeError, ValueError):
            continue
        if data.get("ruleset") == tycoon.RULES_VERSION:
            result.append(data)
    return result


def saved_summaries() -> list[dict]:
    rows = []
    for data in _rows():
        state = data.get("state") or {}
        settings = state.get("settings") or {}
        franchises = state.get("franchises") or {}
        turns = int(state.get("turn", 1) or 1)
        rows.append({
            "code": data.get("code", ""),
            "room_id": data.get("room_id", ""),
            "host_id": data.get("host_id", ""),
            "created_at": data.get("created_at", 0),
            "updated_at": data.get("updated_at", time.time()),
            "phase": state.get("phase", "lobby"),
            "turn": turns,
            "turns": turns,
            "round": turns,  # legacy alias for clients that still read it
            "hand_size": settings.get("hand_size", tycoon.DEFAULT_SETTINGS["hand_size"]),
            "mode": settings.get("difficulty", "medium"),
            "finished": bool(state.get("finished")),
            "winner_id": state.get("winner_id"),
            "winner_name": (franchises.get(state.get("winner_id"), {}) or {}).get("name"),
            "franchises": [f.get("name", "") for f in franchises.values()],
            "matches": len([e for e in state.get("log", []) if e.get("kind") == "card"]),
        })
    return rows


# ---------------------------------------------------------------------------
# Room model
# ---------------------------------------------------------------------------

def clean_settings(raw: dict | None) -> dict:
    """Clamp host-editable lobby settings to the published game limits.

    Unknown keys are deliberately preserved so invitations and older saves can
    carry harmless metadata without breaking the room.
    """
    raw = dict(raw or {})
    settings = dict(tycoon.DEFAULT_SETTINGS)
    settings.update(raw)
    for key, low, high in (("max_players", 2, 6), ("hand_size", 5, 12)):
        try:
            settings[key] = max(low, min(high, int(settings[key])))
        except (TypeError, ValueError):
            settings[key] = tycoon.DEFAULT_SETTINGS[key]
    return settings


def _code() -> str:
    return "".join(random.choice(string.ascii_uppercase.replace("O", "").replace("I", "")) for _ in range(5))


class TycoonRoom:
    def __init__(self, room_id: str, code: str, host_id: str, created_at: float | None = None):
        self.room_id = room_id
        self.code = code
        self.host_id = host_id
        self.created_at = created_at or time.time()
        self.lobby: dict[str, Any] = {
            "room_id": room_id, "code": code, "host_id": host_id,
            "created_at": self.created_at, "settings": clean_settings(None),
            "members": {}, "data_overrides": {},
        }
        self.state: dict | None = None

    @property
    def members(self) -> dict[str, dict]:
        return self.lobby.setdefault("members", {})

    def snapshot(self, viewer_id: str | None = None) -> dict:
        overrides = self.lobby.get("data_overrides") or (self.state or {}).get("data_overrides") or {}
        gamedata = data52.gamedata(overrides)
        live_settings = ((self.state or {}).get("settings")
                         or self.lobby.get("settings", {}) or {})
        hand_size = live_settings.get("hand_size", tycoon.DEFAULT_SETTINGS["hand_size"])
        gamedata["rules"] = {
            "ruleset": tycoon.RULES_VERSION,
            "hand_size": hand_size,
            "min_players": 2,
            "max_players": 6,
        }

        if not self.state:
            return {
                "room_id": self.room_id, "code": self.code, "host_id": self.host_id,
                "phase": "lobby", "started": False, "finished": False, "ruleset": tycoon.RULES_VERSION,
                "members": list(self.members.values()), "settings": self.lobby.get("settings", {}),
                "you": viewer_id, "data_overrides": overrides, "gamedata": gamedata,
            }

        state = deepcopy(self.state)
        state["gamedata"] = gamedata
        state["standings"] = tycoon.standings(self.state)
        state["host_id"] = self.host_id
        state["you"] = viewer_id
        state["ruleset"] = tycoon.RULES_VERSION

        # Hidden information stays hidden. A manager sees only their own hand;
        # every rival gets an empty hand plus a count, and the draw pile is
        # replaced by its size. The authoritative state is never mutated here.
        for pid, franchise in (state.get("franchises") or {}).items():
            if pid == viewer_id:
                continue
            franchise["hand_count"] = len(franchise.get("hand") or [])
            franchise["hand"] = []
        state["deck_count"] = len(state.pop("deck", []) or [])

        return state


class TycoonManager:
    def __init__(self) -> None:
        self.rooms: dict[str, TycoonRoom] = {}
        self.codes: dict[str, str] = {}

    def restore(self) -> None:
        for data in _rows():
            room_id = data.get("room_id")
            code = data.get("code")
            if not room_id or not code:
                continue
            host_id = data.get("host_id", "")
            room = TycoonRoom(room_id, code, host_id, data.get("created_at"))
            lobby = data.get("lobby") or {}
            if lobby.get("members"):
                room.lobby = lobby
            else:
                state = data.get("state") or {}
                room.lobby["settings"] = state.get("settings") or room.lobby["settings"]
                room.lobby["data_overrides"] = state.get("data_overrides") or {}
                for pid, f in (state.get("franchises") or {}).items():
                    room.members[pid] = {
                        "id": pid, "name": f.get("name"), "avatar": f.get("avatar"),
                        "color": f.get("color"), "is_host": pid == host_id,
                        "is_bot": bool(f.get("is_bot")),
                        "difficulty": (state.get("settings") or {}).get("difficulty", "medium"),
                        "ready": True,
                    }
            room.state = data.get("state")
            self.rooms[room_id] = room
            self.codes[code] = room_id

    def by_code(self, code: str) -> TycoonRoom:
        room_id = self.codes.get(code.upper())
        room = self.rooms.get(room_id or "")
        if not room:
            raise HTTPException(404, "Room not found")
        return room

    def by_token(self, code: str, token: str) -> TycoonRoom:
        room = self.by_code(code)
        valid = token in room.members or (room.state and token in room.state.get("franchises", {}))
        if not valid:
            raise HTTPException(403, "Not a member of this room")
        return room

    def create(self, body: "CreateRoomIn") -> dict:
        code = _code()
        while code in self.codes:
            code = _code()
        room_id = uuid.uuid4().hex
        pid = uuid.uuid4().hex
        host = {
            "id": pid, "name": body.name.strip() or "Manager", "avatar": body.avatar,
            "color": body.color, "is_host": True, "is_bot": False,
            "difficulty": "medium", "ready": True,
        }
        room = TycoonRoom(room_id, code, pid)
        room.lobby["settings"] = clean_settings(body.settings)
        room.members[pid] = host
        self.rooms[room_id] = room
        self.codes[code] = room_id
        _save(room)
        return {"room_id": room_id, "code": code, "player_id": pid, "state": room.snapshot(pid)}

    def join(self, body: "JoinRoomIn") -> dict:
        room = self.by_code(body.code)
        max_players = int(room.lobby["settings"].get("max_players", 6))
        if room.state:
            raise HTTPException(409, "Game already started")
        if len(room.members) >= max_players:
            raise HTTPException(409, "Room is full")
        pid = uuid.uuid4().hex
        room.members[pid] = {
            "id": pid, "name": body.name.strip() or "Manager", "avatar": body.avatar,
            "color": body.color, "is_host": False, "is_bot": False,
            "difficulty": "medium", "ready": True,
        }
        _save(room)
        return {"room_id": room.room_id, "code": room.code, "player_id": pid, "state": room.snapshot(pid)}

    def add_bots(self, code: str, player_id: str, count: int, difficulty: str) -> dict:
        room = self.by_code(code)
        if room.host_id != player_id:
            raise HTTPException(403, "Only the host can add bots")
        if room.state:
            raise HTTPException(409, "Game already started")
        max_players = int(room.lobby["settings"].get("max_players", 6))
        for _ in range(max(0, min(5, int(count)))):
            if len(room.members) >= max_players:
                break
            number = len(room.members) + 1
            pid = uuid.uuid4().hex
            room.members[pid] = {
                "id": pid, "name": f"AI Manager {number}", "avatar": "🤖",
                "color": "#4fd1c5", "is_host": False, "is_bot": True,
                "difficulty": difficulty, "ready": True,
            }
        _save(room)
        return room.snapshot(player_id)

    def update_settings(self, code: str, player_id: str, settings: dict) -> dict:
        room = self.by_code(code)
        if room.host_id != player_id:
            raise HTTPException(403, "Only the host can edit settings")
        if room.state:
            raise HTTPException(409, "Game already started")
        room.lobby["settings"] = clean_settings({**room.lobby["settings"], **(settings or {})})
        _save(room)
        return room.snapshot(player_id)

    def update_data(self, code: str, player_id: str, overrides: dict) -> dict:
        room = self.by_code(code)
        if room.host_id != player_id:
            raise HTTPException(403, "Only the host can edit player data")
        room.lobby["data_overrides"] = overrides or {}
        if room.state:
            room.state["data_overrides"] = deepcopy(room.lobby["data_overrides"])
        _save(room)
        return room.snapshot(player_id)

    def start(self, code: str, player_id: str) -> dict:
        room = self.by_code(code)
        if room.host_id != player_id:
            raise HTTPException(403, "Only the host can start")
        if room.state:
            return room.snapshot(player_id)
        if len(room.members) < 2:
            raise HTTPException(409, "Need at least two managers")
        room.state = tycoon.new_state(room.lobby, room.lobby.get("data_overrides"))
        tycoon.add_log(room.state, "Wicket Rush started — play a card to begin the rush.", "game")
        _save(room)
        return room.snapshot(player_id)

    def restart(self, code: str, player_id: str) -> dict:
        room = self.by_code(code)
        if room.host_id != player_id:
            raise HTTPException(403, "Only the host can restart")
        room.state = None
        return self.start(code, player_id)


manager = TycoonManager()


# ---------------------------------------------------------------------------
# WebSocket hub
# ---------------------------------------------------------------------------

class TycoonHub:
    def __init__(self) -> None:
        self.connections: dict[str, WebSocket] = {}

    async def broadcast(self, room: TycoonRoom) -> None:
        update = {
            "type": "update",
            "server_time": time.time(),
        }
        dead: list[str] = []
        for pid, ws in list(self.connections.items()):
            if pid not in room.members and not (room.state and pid in room.state.get("franchises", {})):
                continue
            update["state"] = room.snapshot(pid)
            update["you"] = pid
            update["events"] = [
                {"type": e.get("kind", "info"), "text": e.get("text", "")}
                for e in (room.state or {}).get("events", [])[-5:]
            ]
            try:
                await ws.send_json(update)
            except Exception:
                dead.append(pid)
        for pid in dead:
            self.connections.pop(pid, None)

    def dispatch(self, room: TycoonRoom, pid: str, action: str, payload: dict) -> str:
        state = room.state
        if not state:
            if action == "ready":
                member = room.members.get(pid)
                if member:
                    member["ready"] = bool(payload.get("ready", not member.get("ready", True)))
                    return "Ready state updated."
            if action == "settings" and room.host_id == pid:
                room.lobby["settings"] = clean_settings({
                    **room.lobby["settings"], **(payload.get("settings") or {}),
                })
                _save(room)
                return "Settings updated."
            if action == "bots" and room.host_id == pid:
                manager.add_bots(room.code, pid, int(payload.get("count", 0)), payload.get("difficulty", "medium"))
                return "AI managers added."
            if action == "start":
                manager.start(room.code, pid)
                return "Wicket Rush started."
            return "Action unavailable in the lobby."

        if action == "ping":
            return "pong"
        if action == "admin_update" and room.host_id == pid:
            manager.update_data(room.code, pid, payload.get("overrides") or {})
            return "Player data updated."
        if action == "restart" and room.host_id == pid:
            manager.restart(room.code, pid)
            return "Wicket Rush restarted."
        if state.get("finished") and action not in ("ping", "restart"):
            raise ValueError("Wicket Rush is complete.")

        if action == "play_card":
            tycoon.play_card(state, pid, payload.get("player_id"), payload.get("target_id"))
            return "ok"
        if action == "draw":
            tycoon.draw(state, pid)
            return "ok"
        if action == "target":
            tycoon.choose_target(state, pid, payload.get("target_id"))
            return "ok"
        raise ValueError(f"Unknown action: {action}")

    @staticmethod
    def _signature(room: TycoonRoom) -> str:
        state = room.state or {}
        return json.dumps([
            state.get("turn"), state.get("current_player_id"),
            state.get("current_role"),
            {pid: len(f.get("hand") or [])
             for pid, f in (state.get("franchises") or {}).items()},
            state.get("pending"), state.get("finished"),
            len(state.get("discard") or []),
        ], sort_keys=True, default=str)

    async def auto_room(self, room: TycoonRoom) -> None:
        """Drive bots only; humans keep every play/draw/target decision."""
        state = room.state
        if not state or state.get("finished"):
            return
        before = self._signature(room)
        for _ in range(32):
            if state.get("finished"):
                break
            pending = state.get("pending") or {}
            if pending.get("type") == "target":
                actor = pending.get("pid")
                franchise = state.get("franchises", {}).get(actor) or {}
                if franchise.get("is_bot"):
                    previous = self._signature(room)
                    tycoon.bot_action(state, actor)
                    if self._signature(room) == previous:
                        break
                    continue
                break

            current = state.get("current_player_id")
            franchise = state.get("franchises", {}).get(current) or {}
            if not pending and franchise.get("is_bot"):
                previous = self._signature(room)
                tycoon.bot_action(state, current)
                if self._signature(room) == previous:
                    break
                continue
            break

        if self._signature(room) != before:
            _save(room)
            await self.broadcast(room)

    async def tick_loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=0.6)
                break
            except asyncio.TimeoutError:
                pass
            for room in list(manager.rooms.values()):
                if room.state and not room.state.get("finished"):
                    try:
                        await self.auto_room(room)
                    except Exception:
                        continue

    async def connect(self, websocket: WebSocket, code: str, token: str) -> None:
        await websocket.accept()
        try:
            room = manager.by_token(code, token)
        except HTTPException:
            await websocket.send_json({"type": "error", "message": "Invalid room link"})
            await websocket.close(code=4003)
            return
        self.connections[token] = websocket
        await websocket.send_json({
            "type": "update", "state": room.snapshot(token), "you": token,
            "events": [], "server_time": time.time(),
        })
        try:
            while True:
                message = await websocket.receive_json()
                try:
                    self.dispatch(room, token, message.get("action", ""), message)
                    _save(room)
                    await self.broadcast(room)
                except Exception as exc:
                    await websocket.send_json({"type": "error", "message": str(exc)})
        except WebSocketDisconnect:
            pass
        finally:
            self.connections.pop(token, None)


hub = TycoonHub()


# ---------------------------------------------------------------------------
# REST models + routes
# ---------------------------------------------------------------------------

class SettingsIn(BaseModel):
    settings: dict[str, Any] = Field(default_factory=dict)


class CreateRoomIn(BaseModel):
    name: str = Field(min_length=1, max_length=20)
    avatar: str = Field(default="🏏", max_length=8)
    color: str = Field(default="#c8a24b", max_length=20)
    settings: dict[str, Any] | None = None


class JoinRoomIn(CreateRoomIn):
    code: str = Field(min_length=4, max_length=8)


class ActorIn(BaseModel):
    player_id: str


class BotsIn(ActorIn):
    count: int = 2
    difficulty: str = "medium"


class SettingsBody(ActorIn):
    settings: dict[str, Any] = Field(default_factory=dict)


class DataBody(ActorIn):
    overrides: dict[str, Any] = Field(default_factory=dict)


@router.get("/gamedata")
def gamedata() -> dict:
    data = data52.gamedata()
    data["rules"] = {
        "ruleset": tycoon.RULES_VERSION,
        "hand_size": tycoon.DEFAULT_SETTINGS["hand_size"],
        "min_players": 2,
        "max_players": 6,
    }
    return data


@router.get("/saved")
def saved() -> list[dict]:
    return saved_summaries()


@router.post("/rooms")
def create_room(body: CreateRoomIn) -> dict:
    return manager.create(body)


@router.post("/rooms/join")
def join_room(body: JoinRoomIn) -> dict:
    return manager.join(body)


@router.get("/rooms/{code}")
def get_room(code: str) -> dict:
    return manager.by_code(code).snapshot(None)


@router.post("/rooms/{code}/start")
def start_room(code: str, body: ActorIn) -> dict:
    return manager.start(code, body.player_id)


@router.post("/rooms/{code}/bots")
def add_bots(code: str, body: BotsIn) -> dict:
    return manager.add_bots(code, body.player_id, body.count, body.difficulty)


@router.post("/rooms/{code}/settings")
def update_settings(code: str, body: SettingsBody) -> dict:
    return manager.update_settings(code, body.player_id, body.settings)


@router.post("/rooms/{code}/data")
def update_data(code: str, body: DataBody) -> dict:
    return manager.update_data(code, body.player_id, body.overrides)


@router.post("/quick")
def quick_match(body: CreateRoomIn) -> dict:
    data = dict(body.settings or {})
    data["max_players"] = 3
    created = manager.create(CreateRoomIn(**{**body.model_dump(), "settings": data}))
    code = created["code"]
    pid = created["player_id"]
    manager.add_bots(code, pid, 2, "medium")
    return {
        "room_id": created["room_id"], "code": code, "player_id": pid,
        "state": manager.start(code, pid),
    }


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, code: str, token: str) -> None:
    await hub.connect(websocket, code, token)
