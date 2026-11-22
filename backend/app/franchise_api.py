"""Franchise Crickopoly REST + WebSocket API.

This is the authoritative online layer for the full franchise game (52-tile
board, 96 players, markets, stadiums, auctions, T20 matches and a season). It
lives beside the legacy arcade API so existing rooms/saves keep working, while
all new clients use these endpoints.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from . import franchise_persistence as fdb
from .game import ai, auction, conditions, core, squad, tournament, trades, turn
from .game import franchise_economy as economy
from .game.data52 import (SAFE_RULE_FIELDS, apply_global_overrides, gamedata,
                          sanitise_player_override)
from .state import GameState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fg", tags=["franchise"])

AVATARS = ("🦁", "🦅", "🐯", "🐋", "🦘", "🦓", "🦉", "🐊")
COLORS = ("#c8a24b", "#4fd1c5", "#f56565", "#68d391", "#b794f4", "#f6ad55", "#63b3ed", "#fc8181")


def room_settings_overrides(room: "FranchiseRoom") -> dict:
    value = room.settings.get("data_overrides")
    return value if isinstance(value, dict) else {}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
@dataclass
class FranchiseRoom:
    id: str
    code: str
    host_id: str
    created_at: float
    settings: dict
    lobby: dict[str, dict] = field(default_factory=dict)
    state: GameState | None = None

    def snapshot(self, viewer_id: str | None = None) -> dict:
        if self.state is None:
            members = [
                {"id": pid, "name": m["name"], "avatar": m["avatar"],
                 "color": m["color"], "is_bot": m.get("is_bot", False),
                 "difficulty": m.get("difficulty", "medium"),
                 "is_host": pid == self.host_id, "ready": m.get("ready", False)}
                for pid, m in self.lobby.items()
            ]
            return {
                "room_id": self.id, "code": self.code, "phase": "lobby",
                "started": False, "members": members, "settings": self.settings,
                "host_id": self.host_id, "you": viewer_id,
                "data_overrides": room_settings_overrides(self),
                "gamedata": gamedata(room_settings_overrides(self)),
            }
        data = self.state.to_dict(viewer_id)
        data["host_id"] = self.host_id
        data["gamedata"] = gamedata(data.get("data_overrides"))
        data["standings"] = tournament.standings(self.state)
        data["transfer_window"] = trades.transfer_window_info(self.state)
        data["trade_offers"] = trades.offers_for(self.state, viewer_id)
        data["final_points"] = (tournament.final_points(self.state)
                                if self.state.finished else [])
        pending = self.state.pending or {}
        if pending.get("type") == "match_setup":
            subs = self.state.tactics_submissions
            # Conceal simultaneous plans: a client only sees its own choice and
            # the fact that an opponent has submitted, never their contents.
            data["tactics_submissions"] = (
                {viewer_id: subs[viewer_id]} if viewer_id in subs else {}
            )
            data["tactics_submitted"] = sorted(subs)
            data["tactics_concealed"] = True
        return data


class FranchiseManager:
    def __init__(self) -> None:
        self.rooms: dict[str, FranchiseRoom] = {}
        self.by_code: dict[str, str] = {}

    def create(self, name: str, avatar: str, color: str, settings: dict) -> FranchiseRoom:
        room = FranchiseRoom(
            id=uuid.uuid4().hex, code=self._code(), host_id=uuid.uuid4().hex,
            created_at=time.time(), settings=dict(settings),
        )
        room.lobby[room.host_id] = {
            "name": name, "avatar": avatar, "color": color,
            "ready": False, "is_bot": False,
        }
        self.rooms[room.id] = room
        self.by_code[room.code] = room.id
        return room

    def _code(self) -> str:
        import random
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        while True:
            code = "".join(random.choice(alphabet) for _ in range(5))
            if code not in self.by_code:
                return code

    def get(self, room_id: str) -> FranchiseRoom | None:
        return self.rooms.get(room_id)

    def by_code_get(self, code: str) -> FranchiseRoom | None:
        rid = self.by_code.get(code.strip().upper())
        return self.rooms.get(rid) if rid else None

    def join(self, code: str, name: str, avatar: str, color: str) -> tuple[FranchiseRoom, str]:
        room = self.by_code_get(code)
        if not room:
            raise ValueError("Room not found")
        if room.state:
            raise ValueError("Match already started")
        if len(room.lobby) >= room.settings.get("max_players", 6):
            raise ValueError("Room is full")
        pid = uuid.uuid4().hex
        room.lobby[pid] = {"name": name, "avatar": avatar, "color": color,
                           "ready": False, "is_bot": False}
        return room, pid

    def add_bots(self, room: FranchiseRoom, count: int, difficulty: str) -> None:
        if room.state:
            raise ValueError("Match already started")
        capacity = room.settings.get("max_players", 6)
        room.settings["ai_difficulty"] = difficulty
        for _ in range(count):
            if len(room.lobby) >= capacity:
                break
            idx = len(room.lobby)
            pid = f"bot-{uuid.uuid4().hex[:8]}"
            room.lobby[pid] = {
                "name": f"{difficulty.title()} AI {idx}",
                "avatar": AVATARS[idx % len(AVATARS)],
                "color": COLORS[idx % len(COLORS)],
                "ready": True, "is_bot": True, "difficulty": difficulty,
            }

    def set_ready(self, room: FranchiseRoom, pid: str, ready: bool) -> None:
        if pid not in room.lobby:
            raise ValueError("Not in this room")
        room.lobby[pid]["ready"] = bool(ready)

    def set_settings(self, room: FranchiseRoom, pid: str, settings: dict) -> None:
        if pid != room.host_id:
            raise ValueError("Only the host can change settings")
        if room.state:
            raise ValueError("Settings are locked after kickoff")
        allowed = {"starting_credits", "max_players", "mode", "season_rounds",
                   "ai_difficulty", "transfer_window_every", "tactical_reveal",
                   "pitch", "victory_mode", "data_overrides"}
        for key in allowed:
            if key in settings:
                room.settings[key] = settings[key]
        overrides = room.settings.get("data_overrides")
        if not isinstance(overrides, dict):
            room.settings["data_overrides"] = {}
        room.settings["starting_credits"] = max(500, min(5000, int(room.settings.get("starting_credits", 1500))))
        room.settings["max_players"] = max(2, min(6, int(room.settings.get("max_players", 6))))
        room.settings["season_rounds"] = max(2, min(16, int(room.settings.get("season_rounds", 8))))

    def update_data_overrides(self, room: FranchiseRoom, pid: str,
                              incoming: dict) -> dict:
        """Host-only editor for the fictional roster/rule data."""
        if pid != room.host_id:
            raise ValueError("Only the host can edit game data")
        source = incoming if isinstance(incoming, dict) else {}
        clean: dict[str, dict] = {"players": {}, "rules": {}}
        edits = source.get("players", {})
        if isinstance(edits, dict):
            for player_id, change in edits.items():
                safe = sanitise_player_override(player_id, change)
                if safe:
                    clean["players"][player_id] = safe
        rules = source.get("rules", {})
        if isinstance(rules, dict):
            for key in SAFE_RULE_FIELDS & rules.keys():
                try:
                    clean["rules"][key] = max(1, min(10000, int(rules[key])))
                except (TypeError, ValueError):
                    continue
        if room.state is not None:
            target = room.state.data_overrides
        else:
            target = room.settings.setdefault("data_overrides", {})
        for section, values in clean.items():
            target.setdefault(section, {}).update(values)
        apply_global_overrides(target)
        return target

    def start(self, room: FranchiseRoom, pid: str) -> None:
        if pid != room.host_id:
            raise ValueError("Only the host can start")
        if room.state:
            return
        if len(room.lobby) < 2:
            raise ValueError("At least 2 franchises are required")
        members = [{"id": mid, **m} for mid, m in room.lobby.items()]
        apply_global_overrides(room_settings_overrides(room))
        room.state = core.create_game(room.id, room.code, members, room.settings)
        fdb.save(room.state, room.host_id, room.created_at)

    def remove(self, room: FranchiseRoom) -> None:
        self.rooms.pop(room.id, None)
        self.by_code.pop(room.code, None)

    def restore(self) -> None:
        for room_id in list(self.rooms):
            self.rooms.pop(room_id, None)
        self.by_code.clear()
        for state, host_id, created_at in fdb.load_all():
            room = FranchiseRoom(
                id=state.room_id, code=state.code, host_id=host_id,
                created_at=created_at, settings=state.settings,
                lobby={}, state=state,
            )
            self.rooms[room.id] = room
            self.by_code[room.code] = room.id


manager = FranchiseManager()


# ---------------------------------------------------------------------------
# WebSocket hub
# ---------------------------------------------------------------------------
class FranchiseHub:
    def __init__(self) -> None:
        self.connections: dict[str, dict[str, WebSocket]] = {}

    async def connect(self, room: FranchiseRoom, pid: str, ws: WebSocket) -> None:
        await ws.accept()
        self.connections.setdefault(room.id, {})[pid] = ws
        await self._send(ws, room, pid)
        await self.broadcast(room, exclude_pid=pid)

    async def disconnect(self, room: FranchiseRoom, pid: str) -> None:
        self.connections.get(room.id, {}).pop(pid, None)
        if room.state:
            fdb.save(room.state, room.host_id, room.created_at)
        await self.broadcast(room)

    async def _send(self, ws: WebSocket, room: FranchiseRoom, pid: str,
                    events: list[dict] | None = None) -> None:
        await ws.send_json({
            "type": "update", "state": room.snapshot(pid),
            "events": events or [], "you": pid, "server_time": time.time(),
        })

    async def broadcast(self, room: FranchiseRoom, events: list[dict] | None = None,
                        exclude_pid: str | None = None) -> None:
        for pid, ws in list(self.connections.get(room.id, {}).items()):
            if pid == exclude_pid:
                continue
            try:
                await self._send(ws, room, pid, events)
            except Exception:
                self.connections.get(room.id, {}).pop(pid, None)

    async def error(self, ws: WebSocket, message: str) -> None:
        await ws.send_json({"type": "error", "message": message})

    async def handle(self, ws: WebSocket, room: FranchiseRoom, pid: str) -> None:
        await self.connect(room, pid, ws)
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await self.error(ws, "Invalid JSON")
                    continue
                action = msg.get("action", "ping")
                try:
                    events = self.route(room, pid, action, msg)
                except ValueError as exc:
                    await self.error(ws, str(exc))
                    continue
                except Exception as exc:
                    logger.exception("Franchise action failed: %s", action)
                    await self.error(ws, "Action rejected")
                    continue
                if room.state:
                    fdb.save(room.state, room.host_id, room.created_at)
                await self.broadcast(room, events)
        except WebSocketDisconnect:
            await self.disconnect(room, pid)

    def route(self, room: FranchiseRoom, pid: str, action: str, msg: dict) -> list[dict]:
        state = room.state
        events: list[dict] = []
        apply_global_overrides(
            (state.data_overrides if state else None) or room_settings_overrides(room)
        )
        if action == "ping":
            return []
        if action == "admin_update":
            manager.update_data_overrides(room, pid, msg.get("overrides", {}))
            return []
        if action == "ready":
            manager.set_ready(room, pid, bool(msg.get("ready", True)))
            return []
        if action == "settings":
            manager.set_settings(room, pid, msg.get("settings", {}))
            return []
        if action == "bots":
            manager.add_bots(room, int(msg.get("count", 1)), msg.get("difficulty", "medium"))
            return []
        if action == "start":
            manager.start(room, pid)
            state = room.state
            assert state is not None
            self._auto_ai(state, events)
            return events

        if not state:
            raise ValueError("Match has not started")

        if action == "draft":
            core.draft_pick(state, pid, msg.get("player_id", ""))
        elif action == "roll":
            result = turn.roll_dice(state, pid)
            events.append({"type": "roll", "payload": result})
            self._tile_action(state, pid, result, msg, events)
            # A pending purchase, matchday or auction still needs a human
            # decision. Otherwise the turn is complete and must advance,
            # mirroring core.run_ai_step for bot managers.
            if not state.pending and not state.auction:
                core.advance(state)
                core.maybe_end_season(state)
        elif action == "buy_market":
            turn.buy_market(state, pid, int(msg.get("pos", -1)))
            core.advance(state)
            core.maybe_end_season(state)
        elif action == "buy_stadium":
            turn.buy_stadium(state, pid, int(msg.get("pos", -1)))
            core.advance(state)
            core.maybe_end_season(state)
        elif action == "skip":
            turn.skip_purchase(state, pid)
            core.advance(state)
        elif action == "auction":
            ids = msg.get("player_ids", [])
            auction.create_auction(state, msg.get("kind", "market"), ids, pid,
                                   owner_fid=msg.get("owner_fid"),
                                   base_price=msg.get("base_price"))
        elif action == "bid":
            auction.place_bid(state, pid, int(msg.get("amount", 0)))
        elif action == "pass":
            auction.pass_auction(state, pid)
        elif action == "set_xi":
            ok, errors = squad.set_xi(state, pid, msg.get("xi", []),
                                      msg.get("captain"), msg.get("vice"))
            if not ok:
                raise ValueError("; ".join(errors))
        elif action == "auto_xi":
            ok, errors = squad.auto_xi(state, pid)
            if not ok:
                raise ValueError("; ".join(errors))
        elif action == "train":
            out = conditions.train(state, pid, msg.get("player_id", ""), msg.get("type", "batting"))
            events.append({"type": "training", "payload": out})
        elif action == "rehabilitate":
            conditions.rehabilitate(state, pid, msg.get("player_id", ""))
        elif action == "rest":
            conditions.rest_player(state, pid, msg.get("player_id", ""))
        elif action == "upgrade_stadium":
            turn.upgrade_stadium(state, pid, int(msg.get("pos", -1)), msg.get("upgrade", ""))
        elif action in ("match", "open_match"):
            record = core.open_match(state, pid, msg.get("opponent", ""),
                                     seed=msg.get("seed"))
            if isinstance(record, dict) and record.get("winner_name"):
                events.append({"type": "match", "payload": record})
        elif action == "submit_tactics":
            result = core.submit_tactics(state, pid, msg.get("tactics"), msg.get("card"))
            if isinstance(result, dict) and result.get("winner_name"):
                events.append({"type": "match", "payload": result})
        elif action == "reveal_tactics":
            record = core.reveal_match(state, pid)
            if record:
                events.append({"type": "match", "payload": record})
        elif action == "cancel_match":
            core.cancel_match(state, pid)
        elif action == "trade_offer":
            trade = trades.create_offer(
                state, pid, msg.get("to", ""), msg.get("give", {}),
                msg.get("want", {}), msg.get("message", ""),
            )
            events.append({"type": "trade", "payload": trade})
        elif action == "trade_accept":
            trade = trades.accept_offer(state, str(msg.get("trade_id", "")), pid)
            events.append({"type": "trade", "payload": trade})
        elif action == "trade_reject":
            trades.reject_offer(state, str(msg.get("trade_id", "")), pid)
        elif action == "trade_cancel":
            trades.cancel_offer(state, str(msg.get("trade_id", "")), pid)
        elif action == "next":
            # Host-driven AI progression: run every AI until a human's turn.
            core.series_ai_steps(state, 30)
            auction.tick_auctions(state)
            core.maybe_end_season(state)
        elif action == "tick_auctions":
            for aid in auction.tick_auctions(state):
                events.append({"type": "auction_closed", "payload": {"id": aid}})
        elif action == "restart":
            if pid != room.host_id:
                raise ValueError("Only the host can restart")
            fresh = core.create_game(room.id, room.code, [
                {"id": mid, **m} for mid, m in room.lobby.items()
            ], room.settings)
            room.settings["data_overrides"] = deepcopy(fresh.data_overrides)
            room.state = fresh
            state = fresh
        else:
            raise ValueError("Unknown action")

        self._auto_ai(state, events)
        return events

    def _tile_action(self, state: GameState, pid: str, result: dict,
                     msg: dict, events: list[dict]) -> None:
        action = result.get("action")
        pos = result.get("to")
        if action in ("buy_market", "buy_stadium"):
            if bool(msg.get("auto_buy")) or state.franchises[pid].get("is_bot"):
                fn = turn.buy_market if action == "buy_market" else turn.buy_stadium
                try:
                    out = fn(state, pid, pos)
                    events.append({"type": "purchase", "payload": out})
                except ValueError:
                    pass
        if action == "event" and result.get("event", {}).get("opened"):
            events.append({"type": "event", "payload": result["event"]})

    def _auto_ai(self, state: GameState, events: list[dict]) -> None:
        """Advance bot turns automatically after any human action."""
        if state.phase == "draft":
            for _ in range(60):
                fid = state.current_player_id
                f = state.franchises.get(fid)
                if not f or not f.get("is_bot"):
                    break
                if not core.ai_draft_step(state):
                    break
            return
        if state.pending and state.pending.get("type") == "match_setup":
            core.auto_submit_bots(state)
            record = core.maybe_resolve_match(state)
            if record:
                events.append({"type": "match", "payload": record})
            return
        if state.phase != "season" or state.pending or state.auction:
            return
        for _ in range(30):
            fid = state.current_player_id
            f = state.franchises.get(fid)
            if not f or not f.get("is_bot"):
                break
            step = core.run_ai_step(state)
            events.extend({"type": "ai", "payload": a} for a in step)
            if not step:
                break
            auction.tick_auctions(state)
        core.maybe_end_season(state)

    async def tick_loop(self, stop: asyncio.Event | None = None) -> None:
        while True:
            if stop is not None and stop.is_set():
                return
            await asyncio.sleep(1.0)
            if stop is not None and stop.is_set():
                return
            for room in list(manager.rooms.values()):
                state = room.state
                if not state or state.finished:
                    continue
                events: list[dict] = []
                try:
                    apply_global_overrides(state.data_overrides)
                    closed = auction.tick_auctions(state)
                    events.extend({"type": "auction_closed", "payload": {"id": a}} for a in closed)
                    self._auto_ai(state, events)
                except Exception:
                    logger.exception("Franchise tick failed for %s", room.code)
                    continue
                if events:
                    fdb.save(state, room.host_id, room.created_at)
                    await self.broadcast(room, events)


hub = FranchiseHub()


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------
class CreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=24)
    avatar: str = Field(default="🏏", max_length=8)
    color: str = Field(default="#c8a24b", max_length=20)
    settings: dict = Field(default_factory=dict)


class JoinIn(CreateIn):
    code: str = Field(min_length=4, max_length=8)


class PlayerIn(BaseModel):
    player_id: str
    settings: dict | None = None
    count: int = 1
    difficulty: str = "medium"


@router.get("/gamedata")
def get_gamedata() -> dict:
    return gamedata()


@router.get("/saved")
def saved_rooms() -> list[dict]:
    return fdb.saved_summaries()


@router.post("/rooms", status_code=201)
async def create_room(body: CreateIn) -> dict:
    room = manager.create(body.name, body.avatar, body.color, body.settings)
    fdb.init_db()
    return {"room_id": room.id, "code": room.code,
            "player_id": room.host_id, "state": room.snapshot(room.host_id)}


@router.post("/rooms/join")
async def join_room(body: JoinIn) -> dict:
    try:
        room, pid = manager.join(body.code, body.name, body.avatar, body.color)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await hub.broadcast(room)
    return {"room_id": room.id, "code": room.code,
            "player_id": pid, "state": room.snapshot(pid)}


@router.get("/rooms/{code}")
def get_room(code: str) -> dict:
    room = manager.by_code_get(code)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return room.snapshot()


@router.post("/rooms/{code}/start")
async def start_room(code: str, body: PlayerIn) -> dict:
    room = manager.by_code_get(code)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    try:
        manager.start(room, body.player_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    events: list[dict] = []
    assert room.state is not None
    hub._auto_ai(room.state, events)
    await hub.broadcast(room, events)
    return room.snapshot(body.player_id)


@router.post("/rooms/{code}/bots")
async def add_bots(code: str, body: PlayerIn) -> dict:
    room = manager.by_code_get(code)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    try:
        manager.add_bots(room, body.count, body.difficulty)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await hub.broadcast(room)
    return room.snapshot(body.player_id)


@router.post("/rooms/{code}/settings")
async def update_settings(code: str, body: PlayerIn) -> dict:
    room = manager.by_code_get(code)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    try:
        manager.set_settings(room, body.player_id, body.settings or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await hub.broadcast(room)
    return room.snapshot(body.player_id)


@router.post("/quick")
async def quick_match(body: CreateIn) -> dict:
    """One-call local test match: human + 2 bots, draft auto-skipped by setup."""
    room = manager.create(body.name, body.avatar, body.color, body.settings)
    manager.add_bots(room, 2, body.settings.get("ai_difficulty", "medium"))
    manager.start(room, room.host_id)
    assert room.state is not None
    return {"room_id": room.id, "code": room.code, "player_id": room.host_id,
            "state": room.snapshot(room.host_id)}


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, code: str = Query(...),
                             token: str = Query(...)) -> None:
    room = manager.by_code_get(code)
    if not room or (token not in room.lobby and
                    (not room.state or token not in room.state.franchises)):
        await ws.close(code=4003)
        return
    await hub.handle(ws, room, token)
