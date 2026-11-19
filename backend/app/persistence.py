"""SQLite/PostgreSQL persistence for rooms, matches and the global ladder.

Local development and the default Render deployment use SQLite. When
``DATABASE_URL`` is supplied (for example a Render PostgreSQL database), the
same queries are transparently rewritten for psycopg so rooms, match history
and the global leaderboard survive instance restarts.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

from .models import Asset, Batsman, GameState, Player

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                               "data", "crickopoly.db")
DB_PATH = os.getenv("DB_PATH", DEFAULT_DB_PATH)
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
IS_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))

_lock = threading.Lock()


@contextmanager
def _connection() -> Iterator[Any]:
    if IS_POSTGRES:
        import psycopg  # type: ignore
        # Render may start the web process while the managed database is still
        # finishing its first boot; retry briefly instead of crashing at import.
        for attempt in range(5):
            try:
                conn = psycopg.connect(DATABASE_URL, connect_timeout=5)
                break
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(1 + attempt)
    else:
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA journal_mode=WAL")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _sql(query: str) -> str:
    return query.replace("?", "%s") if IS_POSTGRES else query


def init_db() -> None:
    with _lock:
        with _connection() as conn:
            if IS_POSTGRES:
                seq_type = "BIGSERIAL"
            else:
                seq_type = "INTEGER PRIMARY KEY AUTOINCREMENT"

            conn.execute("""
                CREATE TABLE IF NOT EXISTS rooms (
                    room_id TEXT PRIMARY KEY,
                    code TEXT UNIQUE,
                    host_id TEXT,
                    created_at REAL,
                    state_json TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS matches (
                    room_id TEXT,
                    winner_id TEXT,
                    finished_at TEXT,
                    state_json TEXT
                )
            """)
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS transactions (
                    seq {seq_type},
                    room_id TEXT,
                    data TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS match_results (
                    room_id TEXT NOT NULL,
                    player_key TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    avatar TEXT,
                    color TEXT,
                    is_bot INTEGER DEFAULT 0,
                    won INTEGER DEFAULT 0,
                    runs INTEGER DEFAULT 0,
                    coins INTEGER DEFAULT 0,
                    best_runs INTEGER DEFAULT 0,
                    wickets_taken INTEGER DEFAULT 0,
                    wickets_lost INTEGER DEFAULT 0,
                    properties INTEGER DEFAULT 0,
                    upgrades INTEGER DEFAULT 0,
                    gifts_sent INTEGER DEFAULT 0,
                    gifts_received INTEGER DEFAULT 0,
                    finished_at TEXT,
                    PRIMARY KEY (room_id, player_key)
                )
            """)
            _backfill_match_results(conn)


def _backfill_match_results(conn: Any) -> None:
    """Populate the ladder from legacy match snapshots on first upgrade."""
    try:
        rows = conn.execute(
            "SELECT state_json FROM matches WHERE state_json IS NOT NULL"
        ).fetchall()
    except Exception:
        return
    for (payload,) in rows:
        try:
            state = _state_from_dict(json.loads(payload))
            _write_match_results(conn, state)
        except Exception:
            continue


def _write_match_results(conn: Any, state: GameState) -> None:
    """Idempotently write one ladder row per human manager per match."""
    if not state.finished_at:
        return
    for player in state.players.values():
        key = (player.name or "").strip().casefold() or player.id
        properties = [a for a in player.assets.values() if a.space_id is not None]
        values = (
            state.room_id, key, player.id, player.name[:40], player.avatar[:8],
            player.color[:20], 1 if player.is_bot else 0,
            1 if state.winner_id == player.id else 0,
            player.runs, player.money, player.runs,
            int(player.stats.get("wickets_taken", 0)),
            int(player.stats.get("wickets_lost", 0)),
            len(properties), sum(a.level for a in properties),
            int(player.stats.get("coins_gifted", 0)),
            int(player.stats.get("coins_received", 0)),
            state.finished_at,
        )
        conn.execute(_sql("""
            INSERT INTO match_results (
                room_id, player_key, player_id, name, avatar, color, is_bot, won,
                runs, coins, best_runs, wickets_taken, wickets_lost,
                properties, upgrades, gifts_sent, gifts_received, finished_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(room_id, player_key) DO UPDATE SET
                player_id=excluded.player_id, name=excluded.name,
                avatar=excluded.avatar, color=excluded.color,
                is_bot=excluded.is_bot,
                won=excluded.won, runs=excluded.runs, coins=excluded.coins,
                best_runs=excluded.best_runs,
                wickets_taken=excluded.wickets_taken,
                wickets_lost=excluded.wickets_lost,
                properties=excluded.properties, upgrades=excluded.upgrades,
                gifts_sent=excluded.gifts_sent,
                gifts_received=excluded.gifts_received,
                finished_at=excluded.finished_at
        """), values)


def save_room(state: GameState, host_id: str, created_at: float) -> None:
    payload = json.dumps(_state_to_dict(state))
    with _lock:
        with _connection() as conn:
            conn.execute(_sql("""
                INSERT INTO rooms(room_id, code, host_id, created_at, state_json)
                VALUES(?,?,?,?,?)
                ON CONFLICT(room_id) DO UPDATE SET
                    code=excluded.code, state_json=excluded.state_json
            """), (state.room_id, state.code, host_id, created_at, payload))
            if state.finished_at:
                conn.execute(_sql("""
                    INSERT INTO matches(room_id, winner_id, finished_at, state_json)
                    SELECT ?,?,?,? WHERE NOT EXISTS (
                        SELECT 1 FROM matches WHERE room_id = ?
                    )
                """), (state.room_id, state.winner_id, state.finished_at,
                       payload, state.room_id))
                _write_match_results(conn, state)


def delete_room(room_id: str) -> None:
    with _lock:
        with _connection() as conn:
            conn.execute(_sql("DELETE FROM rooms WHERE room_id=?"), (room_id,))


def load_rooms() -> list[tuple[GameState, str, float]]:
    with _lock:
        with _connection() as conn:
            rows = conn.execute(
                "SELECT state_json, host_id, created_at FROM rooms"
            ).fetchall()
    result = []
    for payload, host_id, created_at in rows:
        try:
            result.append((_state_from_dict(json.loads(payload)), host_id, created_at))
        except Exception:  # corrupt snapshot — skip it
            continue
    return result


def match_history(limit: int = 20) -> list[dict[str, Any]]:
    with _lock:
        with _connection() as conn:
            rows = conn.execute(
                _sql("SELECT room_id, winner_id, finished_at, state_json "
                     "FROM matches ORDER BY finished_at DESC LIMIT ?"), (limit,)
            ).fetchall()
    history = []
    for room_id, winner_id, finished_at, payload in rows:
        state = _state_from_dict(json.loads(payload))
        history.append({
            "room_id": room_id,
            "winner_id": winner_id,
            "winner_name": state.players[winner_id].name if winner_id in state.players else None,
            "finished_at": finished_at,
            "round": state.round,
            "players": [
                {"name": p.name, "runs": p.runs, "money": p.money,
                 "wickets_lost": p.stats["wickets_lost"]}
                for p in state.players.values()
            ],
        })
    return history


def global_leaderboard(limit: int = 50, include_bots: bool = False) -> list[dict[str, Any]]:
    """Aggregate every completed match into a persistent manager leaderboard."""
    where = "" if include_bots else "WHERE is_bot = 0"
    with _lock:
        with _connection() as conn:
            rows = conn.execute(_sql(f"""
                SELECT player_key, MAX(name) AS name, MAX(avatar) AS avatar,
                       MAX(color) AS color, COUNT(*) AS matches_played,
                       SUM(won) AS wins, SUM(runs) AS runs,
                       MAX(best_runs) AS best_runs, MAX(coins) AS coins,
                       SUM(wickets_taken) AS wickets_taken,
                       SUM(wickets_lost) AS wickets_lost,
                       SUM(properties) AS properties, SUM(upgrades) AS upgrades,
                       SUM(gifts_sent) AS gifts_sent,
                       SUM(gifts_received) AS gifts_received,
                       MAX(finished_at) AS last_finished_at
                FROM match_results {where}
                GROUP BY player_key
                ORDER BY wins DESC, runs DESC, best_runs DESC, coins DESC
                LIMIT ?
            """), (limit,)).fetchall()
    keys = ("player_key", "name", "avatar", "color", "matches_played", "wins",
            "runs", "best_runs", "coins", "wickets_taken", "wickets_lost",
            "properties", "upgrades", "gifts_sent", "gifts_received",
            "last_finished_at")
    return [dict(zip(keys, row)) for row in rows]


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------
def _state_to_dict(state: GameState) -> dict:
    from dataclasses import asdict
    return asdict(state)


def _state_from_dict(data: dict) -> GameState:
    state = GameState(
        room_id=data["room_id"], code=data["code"],
        current_index=data.get("current_index", 0),
        round=data.get("round", 1), phase=data.get("phase", "lobby"),
        started=data.get("started", False), winner_id=data.get("winner_id"),
        dice=data.get("dice", []), doubles_count=data.get("doubles_count", 0),
        log=data.get("log", []), deck=data.get("deck", []),
        auction=data.get("auction"), pending=data.get("pending"),
        trades=data.get("trades", {}), transactions=data.get("transactions", []),
        started_at=data.get("started_at", ""), finished_at=data.get("finished_at", ""),
        turn_deadline=data.get("turn_deadline", 0.0),
        victory_mode=data.get("victory_mode", "last_standing"),
        turn_limit=data.get("turn_limit", 0),
        extra_turn=data.get("extra_turn", False),
        market=data.get("market"),
        ranking=data.get("ranking", []),
    )
    for pid, pdata in data.get("players", {}).items():
        defaults = Player(id=pid, name=pdata["name"],
                          avatar=pdata.get("avatar", "🏏"),
                          color=pdata.get("color", "#22c55e"))
        effects = defaults.effects
        effects.update(pdata.get("effects") or {})
        stats = defaults.stats
        stats.update(pdata.get("stats") or {})
        player = Player(
            id=pid, name=pdata["name"], avatar=pdata.get("avatar", "🏏"),
            color=pdata.get("color", "#22c55e"),
            money=pdata.get("money", 1000), runs=pdata.get("runs", 0),
            position=pdata.get("position", 0),
            connected=pdata.get("connected", True),
            ready=pdata.get("ready", False), is_host=pdata.get("is_host", False),
            is_bot=pdata.get("is_bot", False),
            bot_strategy=pdata.get("bot_strategy", "smart"),
            eliminated=pdata.get("eliminated", False),
            batsmen={}, active_batsman_id=pdata.get("active_batsman_id"),
            selection=pdata.get("selection", {}),
            no_ball_turns=pdata.get("no_ball_turns", 0),
            no_ball_protection=pdata.get("no_ball_protection", 0),
            gift_round=pdata.get("gift_round", 0),
            debt=pdata.get("debt"),
            effects=effects, stats=stats,
            achievements=pdata.get("achievements", []),
        )
        for bid, bdata in pdata.get("batsmen", {}).items():
            player.batsmen[bid] = Batsman(
                id=bid, owner_id=pid, name=bdata.get("name", "Batsman"),
                identity_id=bdata.get("identity_id"),
                country=bdata.get("country", "Custom"),
                avatar=bdata.get("avatar", "🏏"),
                jersey_color=bdata.get("jersey_color", "#22c55e"),
                jersey_number=bdata.get("jersey_number", 18),
                skin=bdata.get("skin", "#f1c27d"), hair=bdata.get("hair", "short"),
                face=bdata.get("face", "smile"),
                hair_color=bdata.get("hair_color", "#2d1b0e"),
                is_custom=bdata.get("is_custom", False),
                level=bdata.get("level", 1), wickets=bdata.get("wickets", 3),
                max_wickets=bdata.get("max_wickets", 3),
                retired=bdata.get("retired", False), runs=bdata.get("runs", 0),
                injured_until_round=bdata.get("injured_until_round", 0),
            )
        # Migrate legacy snapshots that only had a starter Asset batsman.
        if not player.batsmen:
            for aid, adata in pdata.get("assets", {}).items():
                if adata.get("kind") == "batsman" and adata.get("space_id") is None:
                    player.batsmen[aid] = Batsman(
                        id=aid, owner_id=pid, name=adata.get("name", "Batsman"),
                        identity_id=None, is_custom=True,
                        level=max(1, adata.get("level", 0) + 1),
                        wickets=adata.get("wickets", 3),
                        max_wickets=adata.get("max_wickets", 3),
                        retired=adata.get("wickets", 3) <= 0,
                        runs=adata.get("runs", 0),
                    )
                    player.active_batsman_id = player.active_batsman_id or aid
        for aid, adata in pdata.get("assets", {}).items():
            player.assets[aid] = Asset(
                id=aid, owner_id=pid, space_id=adata.get("space_id"),
                kind=adata["kind"], category=adata["category"],
                name=adata["name"], level=adata.get("level", 0),
                wickets=adata.get("wickets", 0),
                max_wickets=adata.get("max_wickets", 0),
                runs=adata.get("runs", 0), active=adata.get("active", True),
                injured_until_round=adata.get("injured_until_round", 0),
                debuff_until_round=adata.get("debuff_until_round", 0),
            )
        state.players[pid] = player
    state.order = data.get("order", [])
    return state
