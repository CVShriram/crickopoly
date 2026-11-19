"""Server-side AI managers.

Bots are ordinary players in the authoritative game state. They never connect
over a WebSocket; instead the hub's tick loop asks :class:`BotDriver` to make
one legal decision at a time using the same engine methods a human client uses.
This keeps bots honest: every roll, purchase, bid and trade is still validated
by the engine.
"""

from __future__ import annotations

import random
from typing import Any

from . import config
from .game.board import get_space
from .rooms import Room

BOT_NAMES = ["Victory", "Willow", "Bouncer", "Sixer", "Dravid", "Kohli", "Warne", "Malinga"]
BOT_AVATARS = ["🤖", "🦁", "🦅", "🐯", "🦊", "🐺", "⚡", "🔥"]
BOT_COLORS = ["#a78bfa", "#f472b6", "#38bdf8", "#fb923c", "#34d399", "#facc15", "#f87171", "#60a5fa"]

SPACE_TABLE = {
    "batsman": config.BATSMEN,
    "bowler": config.BOWLERS,
    "keeper": config.WICKET_KEEPERS,
    "fielder": config.FIELDERS,
    "stadium": config.STADIUMS,
}
RUN_TILE_RUNS = {
    "run_1": 1, "run_2": 2, "run_4": 4,
    "run_6": config.SIX_RUNS_PER_LEVEL,
}


class BotDriver:
    """Makes one bot decision per call so gameplay stays watchable."""

    def __init__(self) -> None:
        self._rng = random.Random()
        self._seen_bids: set[tuple[str, str, int, float]] = set()
        self._last_upgrade_round: dict[tuple[str, str], int] = {}

    # -- public -----------------------------------------------------------
    def step(self, room: Room) -> list[dict]:
        engine = room.engine
        state = room.state
        if not state.started or state.phase == "over":
            return []

        # Purchase offers addressed to a bot.
        pending = state.pending
        if pending and pending.get("type") == "purchase":
            bot = state.players.get(pending.get("player_id", ""))
            if bot and bot.is_bot and not bot.eliminated:
                self._decide_purchase(engine, state, bot, pending)
                return engine.take_events()

        # Debt recovery is mandatory and takes priority over all other decisions.
        for bot in state.players.values():
            if bot.is_bot and bot.debt and not bot.eliminated:
                self._handle_debt(engine, bot)
                return engine.take_events()

        # Recruitment market / activation decision.
        market = state.market
        if market:
            bot = state.players.get(market.get("player_id", ""))
            if bot and bot.is_bot:
                options = market.get("options", [])
                choice = options[0] if options else None
                price = int(market.get("price", 9999))
                reserve = self._cash_reserve(bot, state)
                want_depth = len(self._usable_batsmen(bot)) < 2 or len(bot.batsmen) < 3
                can_sign = (choice and bot.money - price >= reserve
                            and len(bot.batsmen) < config.MAX_BATSMEN_PER_PLAYER
                            and (want_depth or bot.money >= price + reserve * 2))
                if can_sign:
                    self._safe(engine.recruit_batsman, bot.id, choice["identity_id"])
                else:
                    self._safe(engine.decline_recruit, bot.id)
                return engine.take_events()
        if pending and pending.get("type") == "recruit_activate":
            bot = state.players.get(pending.get("player_id", ""))
            if bot and bot.is_bot:
                usable = [b for b in bot.batsmen.values() if not b.retired and b.wickets > 0]
                use = bool(usable) and (bot.active_batsman_id not in [b.id for b in usable])
                self._safe(engine.activate_recruit, bot.id, use)
                return engine.take_events()

        # Trade offers addressed to a bot.
        for trade in list(state.trades.values()):
            if trade.get("status") != "pending":
                continue
            bot = state.players.get(trade.get("to", ""))
            if bot and bot.is_bot and not bot.eliminated:
                self._decide_trade(engine, state, bot, trade)
                return engine.take_events()

        # Auctions: each bot places at most one bid per auction.
        auction = state.auction
        if auction:
            for bot in state.players.values():
                if bot.is_bot and self._maybe_bid(room, bot, auction):
                    return engine.take_events()

        # Bot's own turn: optional training, then roll.
        pid = state.current_player_id
        player = state.players.get(pid) if pid else None
        if (player and player.is_bot and not player.eliminated
                and state.phase == "await_roll"
                and state.pending is None and state.auction is None):
            self._maybe_upgrade(room, player)
            self._safe(engine.roll_dice, pid)

        return engine.take_events()

    def forget_room(self, room_id: str) -> None:
        """Drop per-room bookkeeping when a match is removed."""
        self._seen_bids = {k for k in self._seen_bids if k[0] != room_id}
        self._last_upgrade_round = {k: v for k, v in self._last_upgrade_round.items() if k[0] != room_id}

    # -- decisions --------------------------------------------------------
    def _decide_purchase(self, engine: Any, state: Any, bot: Any, pending: dict) -> None:
        space = get_space(int(pending["space_id"]))
        price = space.price
        if bot.money < price:
            self._safe(engine.skip_property, bot.id)
            return
        if bot.bot_strategy == "random":
            action = "buy" if self._rng.random() < 0.6 else "skip"
        else:
            score = self._space_score(space, state, bot)
            ratio = score / max(1, price)
            paid = len([a for a in bot.assets.values() if a.space_id is not None])
            reserve = self._cash_reserve(bot, state)
            # Early scarcity is worth paying up for; late game only high-impact
            # assets justify spending the remaining reserve.
            threshold = 0.28 if paid < 2 else (0.34 if self._rounds_left(state) > 5 else 0.48)
            action = ("buy" if bot.money - price >= reserve and (ratio >= threshold or paid < 2)
                      else "skip")
        if action == "buy":
            self._safe(engine.buy_property, bot.id)
        elif (bot.bot_strategy == "smart" and price > bot.money * 0.6
              and bot.money > 250 and self._space_score(space, state, bot) / max(1, price) >= 0.25):
            # Denial value: a scarce high-impact asset going cheap to a rival is
            # worse than paying a premium at auction.
            self._safe(engine.auction_property, bot.id)
        else:
            self._safe(engine.skip_property, bot.id)

    def _handle_debt(self, engine: Any, bot: Any) -> None:
        debt = bot.debt
        if bot.money >= debt["amount"]:
            self._safe(engine.pay_debt, bot.id)
            return
        # Raise cash by selling the least valuable property first, then by
        # downgrading levels. Never leave a debt unresolved silently.
        upgrades = [a for a in bot.assets.values() if a.space_id is not None and a.level > 0]
        if upgrades:
            # Sell the weakest upgrade first, preserving high-yield levels.
            target = min(upgrades, key=lambda a: (
                a.to_dict().get("effective_fee", 0) or a.to_dict().get("effective_rent", 0),
                a.level,
            ))
            self._safe(engine.downgrade_asset, bot.id, target.id)
            return
        assets = [a for a in bot.assets.values() if a.space_id is not None]
        if assets:
            # Among equivalent refunds, give up the lowest-yield property.
            target = min(assets, key=lambda a: (
                a.to_dict()["sale_value"],
                a.to_dict().get("effective_fee", 0) or a.to_dict().get("effective_rent", 0),
            ))
            self._safe(engine.sell_asset, bot.id, target.id)
            return
        self._safe(engine.declare_bankruptcy, bot.id)

    def _decide_trade(self, engine: Any, state: Any, bot: Any, trade: dict) -> None:
        if bot.bot_strategy == "random":
            accept = self._rng.random() < 0.5
        else:
            # From the bot's point of view: it receives `give_*` and hands over
            # `want_*` (the names are from the proposer's perspective).
            received = trade.get("give_money", 0) + sum(
                self._asset_worth(asset)
                for asset_id in trade.get("give_assets", [])
                if (asset := self._find_asset(state, asset_id)) is not None
            )
            handed_over = trade.get("want_money", 0) + sum(
                self._asset_worth(asset)
                for asset_id in trade.get("want_assets", [])
                if (asset := self._find_asset(state, asset_id)) is not None
            )
            accept = received >= handed_over * 0.9
        self._safe(engine.respond_trade, trade["id"], bot.id, accept)

    def _maybe_bid(self, room: Room, bot: Any, auction: dict) -> bool:
        if bot.eliminated or auction.get("highest_bidder") == bot.id:
            return False
        key = (room.id, bot.id, int(auction["space_id"]), float(auction["ends_at"]))
        if key in self._seen_bids:
            return False
        space = get_space(int(auction["space_id"]))
        if bot.bot_strategy == "smart":
            value = self._space_score(space, room.state, bot)
            multiplier = min(1.0, value / max(1, space.price))
            reserve = self._cash_reserve(bot, room.state)
        else:
            multiplier = 0.35
            reserve = 150
        ceiling = min(int(space.price * multiplier), max(0, bot.money - reserve))
        bid = max(int(auction["highest_bid"]) + 10, int(space.price * 0.4))
        if bid > ceiling or bot.money < bid:
            return False
        self._seen_bids.add(key)
        return self._safe(room.engine.place_bid, bot.id, bid)

    def _maybe_upgrade(self, room: Room, bot: Any) -> None:
        state = room.state
        engine = room.engine
        # Health first, six reward second: switching is free and always legal
        # on the bot's own turn.
        usable = self._usable_batsmen(bot)
        if usable:
            healthiest = max(usable, key=lambda b: (b.wickets, b.level))
            if bot.active_batsman_id != healthiest.id:
                self._safe(engine.switch_batsman, bot.id, healthiest.id)

        key = (room.id, bot.id)
        if state.round < 2 or self._last_upgrade_round.get(key) == state.round:
            return
        reserve = self._cash_reserve(bot, state)
        rounds_left = self._rounds_left(state)

        # Upgrading the active batsman scales every six for the rest of the
        # match. Bots accept a slightly longer payback than a pure coin ROI
        # because runs decide most victories.
        active = bot.batsmen.get(bot.active_batsman_id)
        bat_cost = config.BATSMAN_UPGRADE_COSTS.get(active.level) if active else None
        if (active and active.level < config.MAX_BATSMAN_LEVEL and bat_cost
                and bot.money - bat_cost >= reserve
                and (rounds_left >= 4 or bat_cost <= bot.money * 0.2)):
            if self._safe(engine.upgrade_batsman, bot.id, active.id):
                self._last_upgrade_round[key] = state.round
                return

        candidates = [a for a in bot.assets.values()
                      if a.space_id is not None and a.level < config.MAX_LEVEL]
        if not candidates:
            return
        # Best payback per coin: one property level adds 50% of its base fee.
        scored = []
        for asset in candidates:
            info = asset.to_dict()
            cost = int(info.get("upgrade_cost", 9999))
            gain = int(info.get("effective_fee", 0) * 0.5) or int(
                info.get("effective_rent", 0) * 0.5)
            payback = cost / max(1, gain)
            scored.append((payback, cost, asset.id))
        scored.sort()
        payback, cost, asset_id = scored[0]
        if (bot.money - cost >= reserve and payback <= max(3, rounds_left)
                and cost <= bot.money * 0.45):
            if self._safe(engine.upgrade_asset, bot.id, asset_id):
                self._last_upgrade_round[key] = state.round

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def _usable_batsmen(bot: Any) -> list[Any]:
        return [b for b in bot.batsmen.values() if not b.retired and b.wickets > 0]

    @staticmethod
    def _rounds_left(state: Any) -> int:
        if state.victory_mode == "turn_limit" and state.turn_limit:
            return max(1, state.turn_limit - state.round + 1)
        return max(4, 14 - state.round)

    def _cash_reserve(self, bot: Any, state: Any) -> int:
        """Keep enough coins to absorb fees and a recruitment late in the game."""
        if bot.bot_strategy == "random":
            return 120
        rounds_left = self._rounds_left(state)
        return max(80, min(260, 50 + rounds_left * 16))

    @staticmethod
    def _safe(fn: Any, *args: Any) -> bool:
        try:
            fn(*args)
            return True
        except (ValueError, KeyError, AssertionError):
            return False

    def _space_score(self, space: Any, state: Any = None, bot: Any = None) -> float:
        info = SPACE_TABLE.get(space.kind, {}).get(space.category, {})
        fee = info.get("fee", info.get("reward", info.get("rent", 0)))
        run_tile_runs = RUN_TILE_RUNS.get(space.type, 0)
        if run_tile_runs and space.type == "run_6" and bot is not None:
            active = bot.batsmen.get(bot.active_batsman_id)
            run_tile_runs *= active.level if active else 1
        score = (
            fee * 2
            + (info.get("runs", 0) + run_tile_runs) * 3
            + info.get("wickets", 0) * 8 + info.get("reward", 0) * 2
            + info.get("income_reduction", 0) * 200
            + info.get("block_chance", 0) * 250
            + info.get("income_bonus", 0) * 150
        )
        if state is None or bot is None:
            return score

        rounds_left = self._rounds_left(state)
        owned = [a for a in bot.assets.values() if a.space_id is not None]
        # Runs decide turn-limit matches and break most ties, so they become
        # more valuable as the clock runs down.
        if run_tile_runs:
            score += run_tile_runs * (5 - min(4, rounds_left / 4))
        if space.kind == "bowler" and any(p.is_bot is False for p in state.players.values()):
            score += 35  # human opponents are the main wicket pressure
        if space.kind == "stadium" and not any(a.kind == "stadium" for a in owned):
            score += 80  # first stadium compounds all batsman income
        if len(owned) < 2:
            score += 60  # build a board presence before hoarding cash
        return score

    @staticmethod
    def _asset_worth(asset: Any) -> float:
        return asset.price * 0.6 + asset.level * 50

    @staticmethod
    def _find_asset(state: Any, asset_id: str) -> Any | None:
        for player in state.players.values():
            asset = player.assets.get(asset_id)
            if asset is not None:
                return asset
        return None


bot_driver = BotDriver()
