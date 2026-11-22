"""Persistence for the Franchise game (separate table from the legacy arcade
game so both save formats can coexist during migration)."""

from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import fields
from typing import Any, Iterator

from . import persistence as db
from .state import GameState


@contextmanager
def _connection() -> Iterator[Any]:
    with db._connection() as conn:
        yield conn


def init_db() -> None:
    with db._lock:
        with _connection() as conn:
            if db.IS_POSTGRES:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS franchise_rooms (
                        room_id TEXT PRIMARY KEY,
                        code TEXT UNIQUE,
                        host_id TEXT,
                        created_at REAL,
                        updated_at REAL,
                        state_json TEXT
                    )
                """)
            else:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS franchise_rooms (
                        room_id TEXT PRIMARY KEY,
                        code TEXT UNIQUE,
                        host_id TEXT,
                        created_at REAL,
                        updated_at REAL,
                        state_json TEXT
                    )
                """)


_STATE_FIELDS = {f.name for f in fields(GameState)}


def save(state: GameState, host_id: str, created_at: float) -> None:
    payload = json.dumps(state.to_dict())
    with db._lock:
        with _connection() as conn:
            conn.execute(db._sql("""
                INSERT INTO franchise_rooms(room_id, code, host_id, created_at, updated_at, state_json)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(room_id) DO UPDATE SET
                    code=excluded.code, updated_at=excluded.updated_at,
                    state_json=excluded.state_json
            """), (state.room_id, state.code, host_id, created_at, time.time(), payload))


def load_all() -> list[tuple[GameState, str, float]]:
    with db._lock:
        with _connection() as conn:
            rows = conn.execute(
                "SELECT state_json, host_id, created_at FROM franchise_rooms"
            ).fetchall()
    result: list[tuple[GameState, str, float]] = []
    for payload, host_id, created_at in rows:
        try:
            result.append((from_dict(json.loads(payload)), host_id, created_at))
        except Exception:
            continue
    return result


def load_one(room_id: str) -> GameState | None:
    with db._lock:
        with _connection() as conn:
            row = conn.execute(
                db._sql("SELECT state_json FROM franchise_rooms WHERE room_id=?"),
                (room_id,),
            ).fetchone()
    return from_dict(json.loads(row[0])) if row else None


def saved_summaries() -> list[dict]:
    """Lightweight save list for Continue / History screens."""
    with db._lock:
        with _connection() as conn:
            rows = conn.execute(
                "SELECT code, host_id, created_at, updated_at, state_json "
                "FROM franchise_rooms ORDER BY updated_at DESC"
            ).fetchall()
    summaries: list[dict] = []
    for code, host_id, created_at, updated_at, payload in rows:
        try:
            data = json.loads(payload)
        except (TypeError, ValueError):
            continue
        fdata = data.get("franchises") or {}
        summaries.append({
            "code": code,
            "room_id": data.get("room_id", ""),
            "host_id": host_id,
            "created_at": created_at,
            "updated_at": updated_at,
            "phase": data.get("phase", "lobby"),
            "round": data.get("round", 1),
            "mode": data.get("mode", "standard"),
            "finished": bool(data.get("finished")),
            "winner_id": data.get("winner_id"),
            "winner_name": (fdata.get(data.get("winner_id"), {}) or {}).get("name"),
            "franchises": [f.get("name", "") for f in fdata.values()],
            "matches": len(data.get("matches") or []),
        })
    return summaries


def delete(room_id: str) -> None:
    with db._lock:
        with _connection() as conn:
            conn.execute(db._sql("DELETE FROM franchise_rooms WHERE room_id=?"), (room_id,))


def to_dict(state: GameState) -> dict:
    """Full serialisation including private fields (for persistence only)."""
    data = state.to_dict()
    data.update({
        "room_id": state.room_id, "code": state.code, "mode": state.mode,
        "season": state.season, "round": state.round,
        "turn_index": state.turn_index, "order": state.order,
        "started": state.started, "finished": state.finished,
        "winner_id": state.winner_id, "pitch": state.pitch,
        "settings": state.settings, "franchises": state.franchises,
        "ownership": state.ownership, "auctions": state.auctions,
        "matches": state.matches, "transactions": state.transactions,
        "log": state.log, "events": state.events, "pending": state.pending,
        "auction": state.active_auction, "turn_deadline": state.turn_deadline,
        "victory_mode": state.victory_mode, "turn_limit": state.turn_limit,
        "extra_turn": state.extra_turn, "doubles_count": state.doubles_count,
        "dice": state.dice, "market": state.market,
        "playoff_bracket": state.playoff_bracket,
        "trades": state.trades, "tactics_submissions": state.tactics_submissions,
        "data_overrides": state.data_overrides,
    })
    return data


def from_dict(data: dict) -> GameState:
    kwargs = {k: data.get(k) for k in _STATE_FIELDS if k in data}
    # Field defaults handle missing keys; coerce mutable containers.
    for key in ("order", "matches", "transactions", "log", "events", "dice"):
        if kwargs.get(key) is None:
            kwargs[key] = []
    for key in ("franchises", "ownership", "auctions", "settings", "trades",
                "tactics_submissions", "data_overrides"):
        if kwargs.get(key) is None:
            kwargs[key] = {}
    state = GameState(**kwargs)
    return state
