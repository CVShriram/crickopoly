"""FastAPI application: REST lobby API + authoritative WebSocket gameplay."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .game.board import serialize_board
from .persistence import (global_leaderboard, init_db, load_rooms,
                          match_history, save_room)
from .rooms import manager
from .ws import hub

# Ensure the schema exists even when the app is imported in a test client
# that does not run the ASGI lifespan. Safe and idempotent.
init_db()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    for state, host_id, created_at in load_rooms():
        manager.restore(state, host_id, created_at)
    stop = asyncio.Event()
    task = asyncio.create_task(hub.tick_loop(stop))
    try:
        yield
    finally:
        stop.set()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Cricket Monopoly API", version="1.0.0", lifespan=lifespan)

# Same-origin deployments do not need CORS. The defaults below keep the local
# Vite dev server working; set CORS_ORIGINS for a separate static host.
_cors_origins = [origin.strip() for origin in
                 os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
                 .split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


class CreateRoomIn(BaseModel):
    name: str = Field(min_length=1, max_length=20)
    avatar: str = Field(default="🏏", max_length=8)
    color: str = Field(default="#22c55e", max_length=20)


class JoinRoomIn(CreateRoomIn):
    code: str = Field(min_length=4, max_length=8)


class ReadyIn(BaseModel):
    player_id: str
    ready: bool = True


class PlayerIn(BaseModel):
    player_id: str


class MessageIn(BaseModel):
    player_id: str
    message: str = Field(default="", max_length=160)


class BotsIn(BaseModel):
    count: int = Field(default=1, ge=1, le=3)
    strategy: str = Field(default="smart")


class QuickMatchIn(BaseModel):
    name: str = Field(default="Test Manager", min_length=1, max_length=20)
    avatar: str = Field(default="🏏", max_length=8)
    color: str = Field(default="#22c55e", max_length=20)
    bots: int = Field(default=2, ge=1, le=3)
    strategy: str = Field(default="smart")
    victory_mode: str = Field(default=config.DEFAULT_VICTORY_MODE)
    turn_limit: int = Field(default=config.DEFAULT_TURN_LIMIT, ge=1, le=200)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "rooms": len(manager.rooms)}


@app.get("/api/board")
def board() -> list[dict]:
    return serialize_board()


@app.get("/api/config")
def game_config() -> dict[str, Any]:
    return {
        "starting_money": config.STARTING_MONEY,
        "salary": config.SALARY,
        "batsmen": config.BATSMEN,
        "bowlers": config.BOWLERS,
        "wicket_keepers": config.WICKET_KEEPERS,
        "fielders": config.FIELDERS,
        "stadiums": config.STADIUMS,
        "achievements": config.ACHIEVEMENTS,
        "max_level": config.MAX_LEVEL,
        "famous_batsmen": config.FAMOUS_BATSMEN,
        "custom_defaults": config.CUSTOM_IDENTITY_DEFAULTS,
        "custom_skin_options": config.CUSTOM_SKIN_OPTIONS,
        "custom_hair_options": config.CUSTOM_HAIR_OPTIONS,
        "custom_face_options": config.CUSTOM_FACE_OPTIONS,
        "custom_countries": config.CUSTOM_COUNTRIES,
        "batsman_starting_wickets": config.BATSMAN_STARTING_WICKETS,
        "max_batsmen": config.MAX_BATSMEN_PER_PLAYER,
        "max_batsman_level": config.MAX_BATSMAN_LEVEL,
        "batsman_upgrade_costs": {str(k): v for k, v in config.BATSMAN_UPGRADE_COSTS.items()},
        "six_runs_per_level": config.SIX_RUNS_PER_LEVEL,
        "no_ball_runs_per_turn": config.NO_BALL_RUNS_PER_TURN,
        "recruitment_cost": config.RECRUITMENT_COST,
        "victory_modes": list(config.VICTORY_MODES),
        "default_turn_limit": config.DEFAULT_TURN_LIMIT,
        "gift_min_coins": config.GIFT_MIN_COINS,
        "gift_max_coins": config.GIFT_MAX_COINS,
        "gift_reserve_coins": config.GIFT_RESERVE_COINS,
        "gifts_per_round": config.GIFTS_PER_ROUND,
    }


@app.post("/api/rooms", status_code=201)
def create_room(body: CreateRoomIn) -> dict:
    room = manager.create(body.name, body.avatar, body.color)
    save_room(room.state, room.host_id, room.created_at)
    return {"room_id": room.id, "code": room.code, "player_id": room.host_id,
            "state": room.state.to_dict(room.host_id)}


@app.post("/api/rooms/join")
def join_room(body: JoinRoomIn) -> dict:
    try:
        room, player_id = manager.join(body.code, body.name, body.avatar, body.color)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    save_room(room.state, room.host_id, room.created_at)
    return {"room_id": room.id, "code": room.code, "player_id": player_id,
            "state": room.state.to_dict(player_id)}


@app.get("/api/rooms/{code}")
def get_room(code: str) -> dict:
    room = manager.get_by_code(code)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return room.state.to_dict()


@app.post("/api/rooms/{code}/ready")
def set_ready(code: str, body: ReadyIn) -> dict:
    room = manager.get_by_code(code)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    try:
        manager.set_ready(room, body.player_id, body.ready)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    save_room(room.state, room.host_id, room.created_at)
    return room.state.to_dict(body.player_id)


@app.post("/api/rooms/{code}/start")
def start_game(code: str, body: PlayerIn) -> dict:
    room = manager.get_by_code(code)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    try:
        manager.start(room, body.player_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    save_room(room.state, room.host_id, room.created_at)
    return room.state.to_dict(body.player_id)


@app.post("/api/rooms/{code}/bots")
def add_bots(code: str, body: BotsIn) -> dict:
    """Fill empty slots in a lobby with server-side AI managers."""
    room = manager.get_by_code(code)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    try:
        manager.add_bots(room, body.count, body.strategy)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    save_room(room.state, room.host_id, room.created_at)
    return room.state.to_dict(room.host_id)


@app.post("/api/test/match")
def quick_match(body: QuickMatchIn, request: Request) -> dict:
    """Create and immediately start a match against AI managers.

    The response includes a URL that opens the browser straight into the game
    as the human manager, so the whole game can be tested with one request.
    """
    room = manager.create(body.name, body.avatar, body.color)
    try:
        manager.add_bots(room, body.bots, body.strategy)
        room.engine.set_victory_mode(room.host_id, body.victory_mode, body.turn_limit)
        manager.start(room, room.host_id)
    except ValueError as exc:
        manager.remove(room, room.host_id)
        raise HTTPException(status_code=400, detail=str(exc))
    save_room(room.state, room.host_id, room.created_at)
    configured = os.getenv("FRONTEND_URL", "").strip().rstrip("/")
    origin = request.headers.get("origin", "").strip().rstrip("/")
    frontend = configured or origin or str(request.base_url).rstrip("/")
    url = (f"{frontend}/?code={room.code}&token={room.host_id}"
           f"&name={quote(body.name)}&avatar={quote(body.avatar)}"
           f"&color={quote(body.color)}")
    return {
        "code": room.code,
        "player_id": room.host_id,
        "url": url,
        "strategy": body.strategy,
        "state": room.state.to_dict(room.host_id),
    }


@app.get("/api/history")
def history() -> list[dict]:
    return match_history()


@app.get("/api/leaderboard")
def leaderboard(limit: int = Query(50, ge=1, le=200),
                include_bots: bool = Query(False)) -> list[dict]:
    return global_leaderboard(limit, include_bots)


@app.websocket("/ws")
async def websocket_endpoint(
    ws: WebSocket,
    code: str = Query(...),
    token: str = Query(...),
) -> None:
    room = manager.get_by_code(code)
    if not room or token not in room.state.players:
        await ws.close(code=4003)
        return
    await hub.handle(ws, room, token)


# ---------------------------------------------------------------------------
# Single-service production build. Registered last so every API route and the
# WebSocket endpoint above always take precedence over the SPA fallback.
# ---------------------------------------------------------------------------
DIST_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if (DIST_DIR / "index.html").is_file():
    if (DIST_DIR / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        root = DIST_DIR.resolve()
        candidate = (DIST_DIR / full_path).resolve()
        if candidate.is_file() and root in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(DIST_DIR / "index.html")
