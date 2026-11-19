"""Event card deck helpers."""

from __future__ import annotations

import random
from typing import Any

from .. import config


def build_deck(rng: random.Random) -> list[str]:
    cards = [card["id"] for card in config.EVENT_CARDS]
    rng.shuffle(cards)
    return cards


def draw_card(state, rng: random.Random) -> dict[str, Any]:
    if not state.deck:
        state.deck = build_deck(rng)
    card_id = state.deck.pop()
    card = next((c for c in config.EVENT_CARDS if c["id"] == card_id), None)
    if card is None:  # defensive fallback
        card = config.EVENT_CARDS[0]
    return dict(card)
