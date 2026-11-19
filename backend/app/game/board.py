"""Board definition, derived entirely from config.BOARD_LAYOUT."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .. import config


@dataclass(frozen=True)
class BoardSpace:
    id: int
    name: str
    type: str
    category: str | None = None
    kind: str | None = None
    price: int = 0
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "category": self.category,
            "kind": self.kind,
            "price": self.price,
            "description": self.description,
        }


def _space_from_layout(index: int, layout: tuple[str, str, str | None]) -> BoardSpace:
    name, space_type, category = layout
    kind = None
    price = 0
    description = ""
    if category:
        kind, key = category.split(":", 1)
        table = {
            "batsman": config.BATSMEN,
            "bowler": config.BOWLERS,
            "keeper": config.WICKET_KEEPERS,
            "fielder": config.FIELDERS,
            "stadium": config.STADIUMS,
        }.get(kind, {})
        info = table.get(key, {})
        price = int(info.get("price", 0))
        description = info.get("blurb", "")
    else:
        descriptions = {
            "start": "Collect your salary when you pass or land here.",
            "event": "Draw a cricket event card.",
            "boundary": f"Gain {config.BOUNDARY_RUNS} runs and {config.BOUNDARY_MONEY} coins.",
            "sixer": f"Gain {config.SIXER_RUNS} runs and {config.SIXER_MONEY} coins.",
            "run_1": "Score exactly 1 run.",
            "run_2": "Score exactly 2 runs.",
            "run_4": "Score exactly 4 runs.",
            "run_6": f"Score {config.SIX_RUNS_PER_LEVEL} runs × your active batsman's level.",
            "free_hit": "Your next bowling attack is nullified.",
            "rest": "Catch your breath. Nothing happens.",
            "auction": "An unowned property goes under the hammer.",
            "injury": "Your active batsman is injured for 2 rounds.",
            "no_ball": f"Bonus = normal turns since last No-ball × {config.NO_BALL_RUNS_PER_TURN}. Extra turn + one wicket protection.",
            "recruit": f"Open the batsman market (recruitment {config.RECRUITMENT_COST} coins).",
            "challenge": "Face a cricket challenge.",
            "out": "Lose one wicket from an active batsman.",
        }
        description = descriptions.get(space_type, "")
    return BoardSpace(
        id=index, name=name, type=space_type,
        category=key if category else None,
        kind=kind, price=price, description=description,
    )


BOARD: list[BoardSpace] = [
    _space_from_layout(i, layout) for i, layout in enumerate(config.BOARD_LAYOUT)
]
BOARD_SIZE = len(BOARD)


def get_space(index: int) -> BoardSpace:
    return BOARD[index % BOARD_SIZE]


def serialize_board() -> list[dict]:
    return [space.to_dict() for space in BOARD]
