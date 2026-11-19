"""WebSocket connection manager and action router."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

from fastapi import WebSocket, WebSocketDisconnect

from .bots import bot_driver
from .game.board import serialize_board
from .persistence import save_room
from .rooms import Room, manager

BOARD = serialize_board()


class SocketHub:
    def __init__(self) -> None:
        self.connections: dict[str, dict[str, WebSocket]] = {}

    async def connect(self, room: Room, player_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self.connections.setdefault(room.id, {})[player_id] = ws
        room.engine.set_connected(player_id, True)
        await self._send(ws, room, player_id, room.engine.take_events())

    async def disconnect(self, room: Room, player_id: str) -> None:
        self.connections.get(room.id, {}).pop(player_id, None)
        room.engine.set_connected(player_id, False)
        room.engine.take_events()
        save_room(room.state, room.host_id, room.created_at)
        await self.broadcast(room)

    async def _send(self, ws: WebSocket, room: Room, viewer_id: str,
                    events: list[dict]) -> None:
        payload = {
            "type": "update",
            "board": BOARD,
            "state": room.state.to_dict(viewer_id),
            "events": events,
            "you": viewer_id,
            "server_time": time.time(),
        }
        await ws.send_json(payload)

    async def broadcast(self, room: Room, events: list[dict] | None = None) -> None:
        events = events or []
        for pid, ws in list(self.connections.get(room.id, {}).items()):
            try:
                await self._send(ws, room, pid, events)
            except Exception:
                self.connections.get(room.id, {}).pop(pid, None)

    async def handle(self, ws: WebSocket, room: Room, player_id: str) -> None:
        await self.connect(room, player_id, ws)
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    await ws.send_json({"type": "error", "message": "Invalid JSON"})
                    continue
                events: list[dict] = []
                try:
                    events = await self._route(room, player_id, message)
                except ValueError as exc:
                    await ws.send_json({"type": "error", "message": str(exc)})
                    continue
                except Exception as exc:  # pragma: no cover - defensive
                    await ws.send_json({"type": "error", "message": "Action rejected"})
                    continue
                save_room(room.state, room.host_id, room.created_at)
                await self.broadcast(room, events)
        except WebSocketDisconnect:
            await self.disconnect(room, player_id)

    async def _route(self, room: Room, player_id: str, message: dict) -> list[dict]:
        engine = room.engine
        action = message.get("action")
        if action == "ping":
            return []
        if action == "ready":
            manager.set_ready(room, player_id, bool(message.get("ready")))
            engine._emit("ready", player_id=player_id, ready=bool(message.get("ready")))
        elif action == "select_batsman":
            engine.select_batsman(player_id, message.get("identity_id", ""))
        elif action == "create_batsman":
            engine.create_batsman(player_id, message.get("custom", {}))
        elif action == "victory_mode":
            engine.set_victory_mode(player_id, message.get("mode", "last_standing"),
                                    message.get("turn_limit", 20))
        elif action == "switch_batsman":
            engine.switch_batsman(player_id, message.get("batsman_id", ""))
        elif action == "gift_coins":
            engine.gift_coins(player_id, message.get("to_player_id", ""),
                              message.get("amount", 0))
        elif action == "upgrade_batsman":
            engine.upgrade_batsman(player_id, message.get("batsman_id", ""))
        elif action == "recruit":
            engine.recruit_batsman(player_id, message.get("identity_id", ""))
        elif action == "decline_recruit":
            engine.decline_recruit(player_id)
        elif action == "activate_recruit":
            engine.activate_recruit(player_id, bool(message.get("activate")))
        elif action == "pay_debt":
            engine.pay_debt(player_id)
        elif action == "bankrupt":
            engine.declare_bankruptcy(player_id)
        elif action == "downgrade":
            engine.downgrade_asset(player_id, message.get("asset_id", ""))
        elif action == "start":
            manager.start(room, player_id)
        elif action == "roll":
            engine.roll_dice(player_id)
        elif action == "buy":
            engine.buy_property(player_id)
        elif action == "skip":
            engine.skip_property(player_id)
        elif action == "auction":
            engine.auction_property(player_id)
        elif action == "bid":
            engine.place_bid(player_id, message.get("amount", 0))
        elif action == "upgrade":
            engine.upgrade_asset(player_id, message.get("asset_id", ""))
        elif action == "sell":
            engine.sell_asset(player_id, message.get("asset_id", ""))
        elif action == "trade":
            engine.propose_trade(
                player_id, message.get("to", ""),
                message.get("give_assets", []), message.get("give_money", 0),
                message.get("want_assets", []), message.get("want_money", 0),
            )
        elif action == "trade_response":
            engine.respond_trade(message.get("trade_id", ""), player_id,
                                 bool(message.get("accept")))
        else:
            raise ValueError("Unknown action")
        return engine.take_events()

    def tick_room(self, room: Room) -> list[dict]:
        """Advance one room without letting a bad snapshot stall the whole loop."""
        try:
            room.engine.tick()
            events = room.engine.take_events()
            # Bots act through the exact same validated engine methods as
            # human clients, one decision per tick so play stays watchable.
            events.extend(bot_driver.step(room))
            return events
        except Exception:
            logger.exception("Tick failed for room %s", room.code)
            return []

    async def tick_loop(self, stop: asyncio.Event | None = None) -> None:
        while True:
            if stop is not None and stop.is_set():
                return
            await asyncio.sleep(0.5)
            if stop is not None and stop.is_set():
                return
            for room in list(manager.rooms.values()):
                if not room.state.started or room.state.phase == "over":
                    continue
                events = self.tick_room(room)
                if events:
                    save_room(room.state, room.host_id, room.created_at)
                    await self.broadcast(room, events)


hub = SocketHub()
