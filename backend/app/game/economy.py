"""Money movement, transaction history and bankruptcy handling."""

from __future__ import annotations

from ..models import GameState, Player


def _record(state: GameState, **entry) -> None:
    entry["seq"] = len(state.transactions) + 1
    state.transactions.append(entry)
    if len(state.transactions) > 500:
        state.transactions = state.transactions[-500:]


def credit(state: GameState, player: Player, amount: int, reason: str,
           source_id: str | None = None) -> int:
    """Add money. Returns the amount actually credited."""
    if amount <= 0:
        return 0
    player.money += amount
    player.stats["money_earned"] += amount
    if source_id:
        player.stats["received_from_players"] += amount
    _record(state, type="credit", player_id=player.id, source_id=source_id,
            amount=amount, reason=reason, balance=player.money)
    return amount


def debit(state: GameState, player: Player, amount: int, reason: str,
          target_id: str | None = None, allow_debt: bool = False) -> bool:
    """Remove money. Returns False when the player cannot afford it."""
    if amount <= 0:
        return True
    if not allow_debt and player.money < amount:
        return False
    player.money -= amount
    player.stats["money_spent"] += amount
    if target_id:
        player.stats["paid_to_players"] += amount
    _record(state, type="debit", player_id=player.id, target_id=target_id,
            amount=amount, reason=reason, balance=player.money)
    return True


def transfer(state: GameState, payer: Player, receiver: Player, amount: int,
             reason: str) -> bool:
    """Atomic transfer between two players. Never leaves a negative balance."""
    if amount <= 0:
        return True
    if payer.money < amount:
        return False
    debit(state, payer, amount, reason, target_id=receiver.id)
    credit(state, receiver, amount, reason, source_id=payer.id)
    return True
