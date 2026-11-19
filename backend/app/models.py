"""Domain models for Cricket Monopoly.

All state lives on the server. These dataclasses are serialized to JSON for the
WebSocket broadcast and to SQLite for persistence.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Asset:
    id: str
    owner_id: str
    space_id: int | None
    kind: str                 # batsman | bowler | keeper | fielder | stadium
    category: str             # config key, e.g. "star"
    name: str
    level: int = 0
    wickets: int = 0
    max_wickets: int = 0
    runs: int = 0
    active: bool = True
    injured_until_round: int = 0
    debuff_until_round: int = 0

    @property
    def config(self) -> dict:
        from . import config
        table = {
            "batsman": config.BATSMEN,
            "bowler": config.BOWLERS,
            "keeper": config.WICKET_KEEPERS,
            "fielder": config.FIELDERS,
            "stadium": config.STADIUMS,
        }
        if self.kind == "batsman" and self.category == "starter":
            return config.STARTER_BATSMAN
        return table.get(self.kind, {}).get(self.category, {})

    @property
    def price(self) -> int:
        return int(self.config.get("price", 0))

    def to_dict(self) -> dict:
        from . import config
        d = asdict(self)
        c = self.config
        d["config"] = {k: v for k, v in c.items() if k != "blurb"}
        d["is_out"] = self.kind == "batsman" and self.wickets <= 0
        # Pre-compute the effective values the engine actually uses so the UI
        # never has to duplicate balance formulas.
        from .config import PROPERTY_LEVEL_INCOME_MULTIPLIER
        scale = 1 + PROPERTY_LEVEL_INCOME_MULTIPLIER * self.level
        base_fee = int(c.get("fee", c.get("reward", c.get("rent", 0))))
        d["effective_fee"] = int(base_fee * scale) if self.kind in ("bowler", "keeper", "fielder") else 0
        d["effective_rent"] = int(c.get("rent", 0) * scale) if self.kind == "batsman" else d["effective_fee"]
        d["effective_reward"] = d["effective_fee"] if self.kind == "bowler" else 0
        d["effective_block"] = min(1.0, c.get("block_chance", 0) + 0.05 * self.level) if self.kind == "keeper" else 0
        d["effective_cut"] = min(0.5, c.get("income_reduction", 0) + 0.05 * self.level) if self.kind == "fielder" else 0
        d["effective_boost"] = c.get("income_bonus", 0) * (1 + config.LEVEL_INCOME_MULTIPLIER * self.level) if self.kind == "stadium" else 0
        d["run_penalty"] = int(c.get("run_penalty", 0) * scale) if self.kind == "keeper" else 0
        d["purchase_value"] = int(self.price * scale)
        d["upgrade_cost"] = int(c.get("upgrade_cost", 9999) * scale)
        d["sale_value"] = int(self.price * scale * config.SELL_REFUND_RATIO)
        return d


@dataclass
class Batsman:
    """A player-controlled cricketer.

    Famous cricketers and custom cricketers share exactly this schema and the
    same starting values — identity is cosmetic, progression is mechanical.
    """

    id: str
    owner_id: str
    name: str
    identity_id: str | None = None       # config.FAMOUS_BATSMEN key, None if custom
    country: str = "Custom"
    avatar: str = "🏏"
    jersey_color: str = "#22c55e"
    jersey_number: int = 18
    skin: str = "#f1c27d"
    hair: str = "short"
    face: str = "smile"
    hair_color: str = "#2d1b0e"
    is_custom: bool = False
    level: int = 1
    wickets: int = 3
    max_wickets: int = 3
    retired: bool = False
    runs: int = 0
    injured_until_round: int = 0

    @property
    def six_runs(self) -> int:
        from . import config
        return config.SIX_RUNS_PER_LEVEL * self.level

    @property
    def upgrade_cost(self) -> int | None:
        from . import config
        return config.BATSMAN_UPGRADE_COSTS.get(self.level)

    @property
    def usable(self) -> bool:
        return not self.retired and self.wickets > 0

    def to_dict(self) -> dict:
        return {
            "id": self.id, "owner_id": self.owner_id, "name": self.name,
            "identity_id": self.identity_id, "country": self.country,
            "avatar": self.avatar, "jersey_color": self.jersey_color,
            "jersey_number": self.jersey_number, "skin": self.skin,
            "hair": self.hair, "face": self.face, "hair_color": self.hair_color,
            "is_custom": self.is_custom, "level": self.level,
            "wickets": self.wickets, "max_wickets": self.max_wickets,
            "retired": self.retired, "runs": self.runs,
            "injured_until_round": self.injured_until_round,
            "six_runs": self.six_runs, "upgrade_cost": self.upgrade_cost,
            "usable": not self.retired and self.wickets > 0,
        }


@dataclass
class Player:
    id: str
    name: str
    avatar: str
    color: str
    money: int = 1000
    runs: int = 0
    position: int = 0
    connected: bool = True
    ready: bool = False
    is_host: bool = False
    is_bot: bool = False
    bot_strategy: str = "smart"
    eliminated: bool = False
    assets: dict[str, Asset] = field(default_factory=dict)
    # Phase 7 roster / draft fields
    batsmen: dict[str, Batsman] = field(default_factory=dict)
    active_batsman_id: str | None = None
    selection: dict[str, Any] = field(default_factory=dict)
    no_ball_turns: int = 0
    no_ball_protection: int = 0
    gift_round: int = 0
    debt: dict[str, Any] | None = None
    effects: dict[str, Any] = field(default_factory=lambda: {
        "free_hit": 0,
        "powerplay_rounds": 0,
        "poor_form_rounds": 0,
        "score_streak": 0,
        "injury_rounds": 0,
    })
    stats: dict[str, Any] = field(default_factory=lambda: {
        "money_earned": 0,
        "money_spent": 0,
        "paid_to_players": 0,
        "received_from_players": 0,
        "wickets_taken": 0,
        "wickets_lost": 0,
        "runs_from_batsmen": 0,
        "properties_bought": 0,
        "turns": 0,
        "highest_score": 0,
        "bowler_streak": 0,
        "no_ball_bonus_runs": 0,
        "six_runs": 0,
        "batsmen_recruited": 0,
        "batsman_upgrades": 0,
        "wickets_saved": 0,
        "coins_gifted": 0,
        "coins_received": 0,
    })
    achievements: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "avatar": self.avatar,
            "color": self.color,
            "money": self.money,
            "runs": self.runs,
            "position": self.position,
            "connected": self.connected,
            "ready": self.ready,
            "is_host": self.is_host,
            "is_bot": self.is_bot,
            "bot_strategy": self.bot_strategy,
            "eliminated": self.eliminated,
            "assets": [a.to_dict() for a in self.assets.values()],
            "batsmen": [b.to_dict() for b in self.batsmen.values()],
            "active_batsman_id": self.active_batsman_id,
            "selection": dict(self.selection),
            "no_ball_turns": self.no_ball_turns,
            "no_ball_protection": self.no_ball_protection,
            "gift_round": self.gift_round,
            "debt": dict(self.debt) if self.debt else None,
            "effects": dict(self.effects),
            "stats": dict(self.stats),
            "achievements": list(self.achievements),
            "property_count": len([a for a in self.assets.values() if a.space_id is not None]),
            "active_batsmen": (len([b for b in self.batsmen.values() if b.usable])
                               if self.batsmen else
                               len([a for a in self.assets.values()
                                    if a.kind == "batsman" and a.active and a.wickets > 0])),
        }


@dataclass
class GameState:
    room_id: str
    code: str
    players: dict[str, Player] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    current_index: int = 0
    round: int = 1
    phase: str = "lobby"          # lobby | await_roll | moving | resolving | over
    started: bool = False
    winner_id: str | None = None
    dice: list[int] = field(default_factory=list)
    doubles_count: int = 0
    log: list[dict] = field(default_factory=list)
    deck: list[str] = field(default_factory=list)
    auction: dict[str, Any] | None = None
    pending: dict[str, Any] | None = None
    trades: dict[str, dict] = field(default_factory=dict)
    transactions: list[dict] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    turn_deadline: float = 0.0
    # Phase 7 state
    victory_mode: str = "last_standing"
    turn_limit: int = 0
    extra_turn: bool = False
    market: dict[str, Any] | None = None
    ranking: list[dict[str, Any]] = field(default_factory=list)

    # ---- helpers -----------------------------------------------------------
    @property
    def current_player_id(self) -> str | None:
        if not self.order:
            return None
        return self.order[self.current_index % len(self.order)]

    def current_player(self) -> Player | None:
        pid = self.current_player_id
        return self.players.get(pid) if pid else None

    def owner_of(self, space_id: int) -> Player | None:
        for p in self.players.values():
            for a in p.assets.values():
                if a.space_id == space_id:
                    return p
        return None

    def asset_at(self, space_id: int) -> Asset | None:
        for p in self.players.values():
            for a in p.assets.values():
                if a.space_id == space_id:
                    return a
        return None

    def to_dict(self, viewer_id: str | None = None) -> dict:
        return {
            "room_id": self.room_id,
            "code": self.code,
            "players": [p.to_dict() for p in self.players.values()],
            "order": list(self.order),
            "current_player_id": self.current_player_id,
            "round": self.round,
            "phase": self.phase,
            "started": self.started,
            "winner_id": self.winner_id,
            "dice": list(self.dice),
            "doubles_count": self.doubles_count,
            "log": self.log[-60:],
            "auction": self.auction,
            "pending": self.pending,
            "trades": [t for t in self.trades.values()
                       if viewer_id is None or t["from"] == viewer_id or t["to"] == viewer_id],
            "transactions": self.transactions[-50:],
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "viewer_id": viewer_id,
            "victory_mode": self.victory_mode,
            "turn_limit": self.turn_limit,
            "extra_turn": self.extra_turn,
            "market": self.market,
            "ranking": self.ranking,
        }


def make_event(kind: str, **payload: Any) -> dict:
    return {"type": kind, "payload": payload}
