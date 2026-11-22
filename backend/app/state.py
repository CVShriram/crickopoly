"""Authoritative Crickopoly game state.

A single dataclass holds every value the game needs. Nested values are plain
JSON-serialisable dicts/lists so persistence stays a simple JSON blob in
SQLite/Postgres, exactly like the previous implementation.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

from .game import data52


@dataclass
class GameState:
    room_id: str
    code: str
    mode: str = "standard"                 # standard | classic
    phase: str = "setup"                   # setup|season|league|playoffs|over
    season: int = 1
    round: int = 1
    turn_index: int = 0
    order: list[str] = field(default_factory=list)
    started: bool = False
    finished: bool = False
    winner_id: str | None = None
    pitch: str = "flat"
    settings: dict = field(default_factory=lambda: {
        "starting_credits": data52.RULES["starting_credits"],
        "max_players": 6,
        "mode": "standard",
        "season_rounds": 6,
        "ai_difficulty": "medium",
        "transfer_window_every": 3,
        "tactical_reveal": True,
    })
    franchises: dict[str, dict] = field(default_factory=dict)
    ownership: dict[str, str] = field(default_factory=dict)   # tile position -> franchise id
    auctions: dict[str, dict] = field(default_factory=dict)
    matches: list[dict] = field(default_factory=list)
    transactions: list[dict] = field(default_factory=list)
    log: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    pending: dict | None = None
    auction: dict | None = None
    turn_deadline: float = 0.0
    victory_mode: str = "last_standing"
    turn_limit: int = 0
    extra_turn: bool = False
    doubles_count: int = 0
    dice: list[int] = field(default_factory=list)
    market: dict | None = None
    playoff_bracket: dict | None = None
    # Franchise-specific additions: two-sided trades, concealed tactical plans
    # and host-editable roster/rule data (all persisted with the save).
    trades: dict[str, dict] = field(default_factory=dict)
    tactics_submissions: dict[str, dict] = field(default_factory=dict)
    data_overrides: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    @property
    def current_player_id(self) -> str | None:
        if not self.order:
            return None
        return self.order[self.turn_index % len(self.order)]

    def franchise(self, fid: str) -> dict | None:
        return self.franchises.get(fid)

    @property
    def active_auction(self) -> dict | None:
        """Current franchise auction, normalised against the auction registry.

        Franchise auctions are stored in ``auctions`` by id while ``auction``
        is a convenience pointer to the active lot. Snapshots must expose the
        registry copy so a resolved or advanced lot is never shown twice.
        Legacy arcade auctions only populate ``auction`` and are returned as-is.
        """
        auction = self.auction
        if isinstance(auction, dict) and auction.get("id") in self.auctions:
            return self.auctions[auction["id"]]
        return auction

    def to_dict(self, viewer_id: str | None = None) -> dict:
        """Serialise state. Viewer-specific derived values are added here so
        every client receives an authoritative, self-consistent snapshot."""
        data = deepcopy({
            "room_id": self.room_id, "code": self.code, "mode": self.mode,
            "phase": self.phase, "season": self.season, "round": self.round,
            "turn_index": self.turn_index, "order": self.order,
            "current_player_id": self.current_player_id,
            "started": self.started, "finished": self.finished,
            "winner_id": self.winner_id, "pitch": self.pitch,
            "settings": self.settings, "franchises": self.franchises,
            "ownership": self.ownership, "auctions": self.auctions,
            "matches": self.matches, "transactions": self.transactions,
            "log": self.log[-120:], "events": self.events[-60:],
            "pending": self.pending, "auction": self.active_auction,
            "turn_deadline": self.turn_deadline,
            "victory_mode": self.victory_mode, "turn_limit": self.turn_limit,
            "extra_turn": self.extra_turn, "doubles_count": self.doubles_count,
            "dice": self.dice, "market": self.market,
            "playoff_bracket": self.playoff_bracket,
            "trades": self.trades, "tactics_submissions": self.tactics_submissions,
            "data_overrides": self.data_overrides,
        })
        # Backwards-compatible alias used by older UI code / tests.
        data["players"] = list(self.franchises.values())
        data["board"] = data52.BOARD
        if viewer_id and viewer_id in self.franchises:
            data["you"] = viewer_id
        return data


def new_franchise(fid: str, name: str, avatar: str, color: str,
                  is_host: bool = False, is_bot: bool = False,
                  difficulty: str = "medium", starting_credits: int = 1500) -> dict:
    return {
        "id": fid,
        "name": name,
        "avatar": avatar,
        "color": color,
        "token": avatar,
        "is_host": is_host,
        "is_bot": is_bot,
        "difficulty": difficulty,
        "connected": not is_bot,
        "ready": True if is_bot else False,
        "balance": starting_credits,
        "reputation": 0,
        "pos": 0,
        "dice": [],
        "squad": {},                 # player_id -> {"price":int, "tier":str}
        "xi": [],                    # player ids (11)
        "captain": None,
        "vice": None,
        "markets": [],               # tile positions (int)
        "stadiums": {},              # tile position (str) -> list[str] upgrades
        "sponsors": [],              # sponsor ids
        "cards": [],                 # tactical card ids
        "conditions": {},            # player_id -> condition dict
        "record": {
            "played": 0, "wins": 0, "losses": 0, "ties": 0,
            "points": 0, "bonus": 0,
            "runs_for": 0, "runs_against": 0,
            "overs_for": 0.0, "overs_against": 0.0,
        },
        "fatigue": 0,
        "last_action": "",
    }


def fresh_condition(player: dict) -> dict:
    return {
        "fatigue": 0,
        "form": player.get("form", 50),
        "confidence": player.get("confidence", 50),
        "fitness": player.get("fitness", 80),
        "injury": None,              # {"type":..., "matches_left":int, "cost":int}
        "matches_played": 0,
        "training": [],
    }
