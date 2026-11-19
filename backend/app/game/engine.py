"""Server-authoritative game engine.

The engine is intentionally free of FastAPI/WebSocket concerns so it can be
unit-tested deterministically with an injected random number generator. Every
public mutating method validates the acting player, the current turn and the
current phase before changing any state.

Phase 7 adds a dedicated batsman roster, a pre-match draft, tiered defensive
properties, No-ball mechanics, recruitment, debt recovery and selectable
victory modes. Coins and runs are separate currencies throughout.
"""

from __future__ import annotations

import random
import time
from typing import Any

from .. import config
from ..models import Asset, Batsman, GameState, Player, make_event
from .board import BOARD_SIZE, get_space
from .economy import credit, debit, transfer
from .events import draw_card


class GameEngine:
    def __init__(self, state: GameState, rng: random.Random | None = None):
        self.state = state
        self.rng = rng or random.Random()
        self.events: list[dict] = []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _emit(self, kind: str, **payload: Any) -> None:
        event = make_event(kind, **payload)
        self.events.append(event)
        self.state.log.append({"round": self.state.round, **event})
        if len(self.state.log) > 300:
            self.state.log = self.state.log[-300:]

    def take_events(self) -> list[dict]:
        events = list(self.events)
        self.events.clear()
        return events

    def _player(self, player_id: str) -> Player | None:
        return self.state.players.get(player_id)

    def _is_turn(self, player_id: str) -> bool:
        return self.state.current_player_id == player_id and self.state.phase == "await_roll"

    def _alive_ids(self) -> list[str]:
        return [pid for pid in self.state.order if not self.state.players[pid].eliminated]

    def _award(self, player: Player, key: str) -> None:
        if key not in player.achievements and key in config.ACHIEVEMENTS:
            player.achievements.append(key)
            self._emit("achievement", player_id=player.id, key=key,
                       text=config.ACHIEVEMENTS[key])

    def _stadium_bonus(self, player: Player) -> float:
        bonus = 0.0
        for asset in player.assets.values():
            if asset.kind == "stadium" and asset.active:
                bonus += asset.config.get("income_bonus", 0) * (1 + config.LEVEL_INCOME_MULTIPLIER * asset.level)
        return min(bonus, config.MAX_STADIUM_BONUS)

    def _sponsorship(self, player: Player) -> int:
        return int(sum(a.config.get("sponsorship", 0) for a in player.assets.values()
                       if a.kind == "stadium" and a.active))

    # ------------------------------------------------------------------
    # Batsman roster helpers
    # ------------------------------------------------------------------
    def _batsmen(self, player: Player) -> list[Any]:
        """Return every batsman on a roster, with legacy snapshot support."""
        if player.batsmen:
            return list(player.batsmen.values())
        return [a for a in player.assets.values() if a.kind == "batsman"]

    @staticmethod
    def _usable(batsman: Any) -> bool:
        return bool(getattr(batsman, "active", True)) and batsman.wickets > 0 and not getattr(batsman, "retired", False)

    def _usable_batsmen(self, player: Player) -> list[Any]:
        return [b for b in self._batsmen(player) if self._usable(b)]

    def active_batsman(self, player: Player) -> Any | None:
        preferred = next((b for b in self._batsmen(player)
                          if b.id == player.active_batsman_id and self._usable(b)), None)
        if preferred:
            return preferred
        return next(iter(self._usable_batsmen(player)), None)

    def _claimed_identities(self) -> set[str]:
        claimed: set[str] = set()
        for player in self.state.players.values():
            if player.selection.get("identity_id"):
                claimed.add(player.selection["identity_id"])
            for batsman in player.batsmen.values():
                if batsman.identity_id:
                    claimed.add(batsman.identity_id)
        return claimed

    def _available_identities(self) -> list[str]:
        claimed = self._claimed_identities()
        return [key for key in config.FAMOUS_BATSMEN if key not in claimed]

    def _can_recruit(self, player: Player) -> bool:
        return (len(self._batsmen(player)) < config.MAX_BATSMEN_PER_PLAYER
                and player.money >= config.RECRUITMENT_COST
                and bool(self._available_identities()))

    def _create_batsman(self, player: Player, identity_id: str | None,
                        custom: dict[str, Any] | None = None) -> Batsman:
        info = dict(config.FAMOUS_BATSMEN.get(identity_id or "", {}))
        if custom:
            info.update(custom)
        defaults = config.CUSTOM_IDENTITY_DEFAULTS
        batsman = Batsman(
            id=f"{player.id}:bat:{len(player.batsmen) + 1}:{int(time.time() * 1000)}",
            owner_id=player.id,
            name=str(info.get("name") or defaults["name"])[:24],
            identity_id=identity_id,
            country=str(info.get("country") or defaults["country"])[:24],
            avatar=str(info.get("avatar") or defaults["avatar"])[:8],
            jersey_color=str(info.get("jersey_color") or defaults["jersey_color"])[:20],
            jersey_number=int(info.get("jersey_number") or defaults["jersey_number"]),
            skin=str(info.get("skin") or defaults["skin"])[:20],
            hair=str(info.get("hair") or defaults["hair"])[:20],
            face=str(info.get("face") or defaults["face"])[:20],
            hair_color=str(info.get("hair_color") or defaults["hair_color"])[:20],
            is_custom=identity_id is None,
            level=1,
            wickets=config.BATSMAN_STARTING_WICKETS,
            max_wickets=config.BATSMAN_STARTING_WICKETS,
        )
        player.batsmen[batsman.id] = batsman
        player.active_batsman_id = player.active_batsman_id or batsman.id
        return batsman

    # ------------------------------------------------------------------
    # Runs / wickets / elimination
    # ------------------------------------------------------------------
    def _add_runs(self, player: Player, amount: int, reason: str,
                  batsman: Any | None = None) -> None:
        before = player.runs
        player.runs = max(0, player.runs + amount)
        actual = player.runs - before
        if batsman is not None:
            batsman.runs += actual
            if getattr(batsman, "is_custom", True) or isinstance(batsman, Batsman):
                player.stats["runs_from_batsmen"] += actual
        player.stats["highest_score"] = max(player.stats["highest_score"], player.runs)
        self._emit("runs", player_id=player.id, amount=actual, total=player.runs,
                   reason=reason, asset_id=batsman.id if batsman else None)
        milestones = player.effects.setdefault("milestones", [])
        for threshold, reward in config.RUN_MILESTONES.items():
            if player.runs >= threshold and threshold not in milestones:
                milestones.append(threshold)
                credit(self.state, player, reward, f"Run milestone {threshold}")
                self._emit("milestone", player_id=player.id, threshold=threshold,
                           reward=reward)
                if threshold >= 100:
                    self._award(player, "century")

    def _pick_target(self, defender: Player) -> Any | None:
        targets = self._usable_batsmen(defender)
        if not targets:
            return None
        rule = config.BATSMAN_TARGETING
        if rule == "weakest":
            return min(targets, key=lambda b: b.wickets)
        if rule == "strongest":
            return max(targets, key=lambda b: b.wickets)
        return self.rng.choice(targets)

    def _take_wicket(self, defender: Player, count: int, reason: str,
                     attacker_id: str | None = None,
                     specific_batsman: Any | None = None) -> list[dict]:
        results: list[dict] = []
        if not self._usable_batsmen(defender):
            return results
        if defender.effects.get("free_hit", 0) > 0:
            defender.effects["free_hit"] -= 1
            defender.stats["wickets_saved"] += 1
            self._emit("wicket_blocked", player_id=defender.id, reason="free_hit",
                       text="Free Hit! The attack is nullified.")
            return results

        for _ in range(count):
            target = specific_batsman if specific_batsman and self._usable(specific_batsman) else self._pick_target(defender)
            if target is None:
                break
            before = target.wickets
            target.wickets -= 1
            actual = before - target.wickets
            defender.stats["wickets_lost"] += actual
            if attacker_id and attacker_id in self.state.players:
                attacker = self.state.players[attacker_id]
                attacker.stats["wickets_taken"] += actual
                if attacker.stats["wickets_taken"] >= 5:
                    self._award(attacker, "five_wickets")
            out = target.wickets <= 0
            if out:
                target.retired = True if isinstance(target, Batsman) else False
                target.active = False
            defender.effects["score_streak"] = 0
            result = {"asset_id": target.id, "name": target.name,
                      "wickets": target.wickets, "max_wickets": target.max_wickets,
                      "out": out}
            results.append(result)
            self._emit("wicket", player_id=defender.id, attacker_id=attacker_id,
                       reason=reason, **result)
            if out:
                self._emit("batsman_retired", player_id=defender.id,
                           batsman_id=target.id, name=target.name)
        self._ensure_active_batsman(defender)
        self._check_elimination(defender)
        return results

    def _ensure_active_batsman(self, player: Player) -> None:
        """Keep the selection pointer valid when the active batsman is out."""
        selected = next((b for b in self._batsmen(player)
                         if b.id == player.active_batsman_id), None)
        if selected and self._usable(selected):
            return
        replacement = next(iter(self._usable_batsmen(player)), None)
        if replacement:
            player.active_batsman_id = replacement.id
            self._emit("batsman_auto_switched", player_id=player.id,
                       batsman_id=replacement.id, name=replacement.name)

    def _eliminate(self, player: Player, reason: str,
                   creditor: Player | None = None) -> None:
        if player.eliminated:
            return
        player.eliminated = True
        for batsman in self._batsmen(player):
            batsman.wickets = 0
            batsman.retired = True if isinstance(batsman, Batsman) else False
            batsman.active = False
        released: list[str] = []
        for asset in list(player.assets.values()):
            if asset.space_id is not None:
                released.append(asset.id)
                if creditor and not creditor.eliminated and creditor.id != player.id:
                    asset.owner_id = creditor.id
                    creditor.assets[asset.id] = asset
        player.assets = {aid: a for aid, a in player.assets.items() if a.space_id is None}
        player.debt = None
        if self.state.pending and self.state.pending.get("player_id") == player.id:
            self.state.pending = None
        if self.state.market and self.state.market.get("player_id") == player.id:
            self.state.market = None
        self._emit("eliminated", player_id=player.id, reason=reason,
                   released_assets=released, creditor_id=creditor.id if creditor else None)
        self._check_victory()

    def _check_elimination(self, player: Player) -> None:
        if player.eliminated or not self.state.started or not self.state.order:
            return
        if not self._usable_batsmen(player):
            if self._can_recruit(player):
                self._emit("recruit_required", player_id=player.id,
                           text="No batsmen left — recruit one before rolling.")
                return
            self._eliminate(player, "All batsmen retired")
            return
        if player.money < 0:
            self._eliminate(player, "Bankrupt")

    def _ranking(self) -> list[dict[str, Any]]:
        rows = []
        for player in self.state.players.values():
            usable = self._usable_batsmen(player)
            wickets = sum(b.wickets for b in usable)
            properties = [a for a in player.assets.values() if a.space_id is not None]
            score = sum(a.level for a in properties)
            rows.append({
                "player_id": player.id, "name": player.name, "avatar": player.avatar,
                "runs": player.runs, "money": player.money,
                "batsmen": len(usable), "wickets": wickets,
                "properties": len(properties), "upgrades": score,
                "eliminated": player.eliminated,
            })
        rows.sort(key=lambda r: (not r["eliminated"], r["runs"], r["wickets"],
                                 r["batsmen"], r["money"], r["properties"] + r["upgrades"]),
                  reverse=True)
        return rows

    def _finish(self, reason: str) -> None:
        if self.state.phase == "over":
            return
        ranking = self._ranking()
        self.state.ranking = ranking
        self.state.phase = "over"
        self.state.winner_id = ranking[0]["player_id"] if ranking else None
        self.state.finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._emit("victory", winner_id=self.state.winner_id, reason=reason,
                   ranking=ranking)

    def _check_victory(self) -> None:
        if not self.state.started or self.state.phase == "over":
            return
        alive = self._alive_ids()
        if len(alive) <= 1:
            self._finish("Last manager standing")
        elif (self.state.victory_mode == "turn_limit"
              and self.state.turn_limit > 0
              and self.state.round > self.state.turn_limit):
            self._finish(f"Turn limit ({self.state.turn_limit} rounds)")

    # ------------------------------------------------------------------
    # Pre-match draft / victory settings
    # ------------------------------------------------------------------
    def set_victory_mode(self, player_id: str, mode: str,
                         turn_limit: int = config.DEFAULT_TURN_LIMIT) -> None:
        player = self._player(player_id)
        if not player or not player.is_host:
            raise ValueError("Only the host can change victory settings")
        if self.state.started:
            raise ValueError("Victory settings are locked after the match starts")
        if mode not in config.VICTORY_MODES:
            raise ValueError("Unknown victory mode")
        self.state.victory_mode = mode
        self.state.turn_limit = max(1, int(turn_limit)) if mode == "turn_limit" else 0
        self._emit("victory_settings", mode=mode, turn_limit=self.state.turn_limit)

    def select_batsman(self, player_id: str, identity_id: str) -> None:
        player = self._player(player_id)
        if not player:
            raise ValueError("Player not found")
        if self.state.started:
            raise ValueError("Draft is closed")
        if identity_id not in config.FAMOUS_BATSMEN:
            raise ValueError("Unknown cricketer")
        claimed = self._claimed_identities()
        claimed.discard(player.selection.get("identity_id", ""))
        if identity_id in claimed:
            raise ValueError("That cricketer has already been selected")
        info = config.FAMOUS_BATSMEN[identity_id]
        player.selection = {"identity_id": identity_id, "is_custom": False, **info}
        player.ready = True
        self._emit("batsman_selected", player_id=player_id, selection=dict(player.selection))

    def create_batsman(self, player_id: str, custom: dict[str, Any]) -> None:
        player = self._player(player_id)
        if not player:
            raise ValueError("Player not found")
        if self.state.started:
            raise ValueError("Draft is closed")
        if not isinstance(custom, dict):
            raise ValueError("Invalid custom batsman")
        name = str(custom.get("name", "")).strip()
        if not name or len(name) > 24:
            raise ValueError("Name must be 1-24 characters")
        selection = dict(config.CUSTOM_IDENTITY_DEFAULTS)
        selection.update({k: v for k, v in custom.items() if k in selection})
        selection["name"] = name
        selection["identity_id"] = None
        selection["is_custom"] = True
        try:
            selection["jersey_number"] = int(selection["jersey_number"])
        except (TypeError, ValueError):
            raise ValueError("Jersey number must be a number")
        player.selection = selection
        player.ready = True
        self._emit("batsman_selected", player_id=player_id, selection=dict(selection))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self.state.started:
            raise ValueError("Game already started")
        if len(self.state.players) < config.MIN_PLAYERS:
            raise ValueError("At least two players are required")
        if self.state.victory_mode not in config.VICTORY_MODES:
            self.state.victory_mode = config.DEFAULT_VICTORY_MODE

        for player in self.state.players.values():
            if not player.selection:
                available = self._available_identities()
                identity = available[0] if available else None
                if identity:
                    self.select_batsman(player.id, identity)
            player.batsmen = {}
            player.active_batsman_id = None
            player.assets = {}
            batsman = self._create_batsman(player, player.selection.get("identity_id"),
                                           player.selection if player.selection.get("is_custom") else None)
            batsman.name = player.selection.get("name", batsman.name)
            player.money = config.STARTING_MONEY
            player.runs = 0
            player.position = 0
            player.eliminated = False
            player.debt = None
            player.no_ball_turns = 0
            player.no_ball_protection = 0
            player.gift_round = 0
            player.effects = {
                "free_hit": 0, "powerplay_rounds": 0, "poor_form_rounds": 0,
                "score_streak": 0, "injury_rounds": 0, "milestones": [],
            }
            player.active_batsman_id = batsman.id

        self.state.order = list(self.state.players.keys())
        self.rng.shuffle(self.state.order)
        self.state.current_index = 0
        self.state.round = 1
        self.state.phase = "await_roll"
        self.state.started = True
        self.state.extra_turn = False
        self.state.market = None
        self.state.ranking = []
        self.state.started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.state.deck = []
        self.state.dice = []
        self.state.doubles_count = 0
        self.state.turn_deadline = time.time() + config.DECISION_TIMEOUT_SECONDS * 2
        self._emit("game_started", order=self.state.order,
                   current_player_id=self.state.current_player_id)
        self._emit("turn_start", player_id=self.state.current_player_id,
                   round=self.state.round)

    # ------------------------------------------------------------------
    # Turn actions
    # ------------------------------------------------------------------
    def switch_batsman(self, player_id: str, batsman_id: str) -> None:
        player = self._player(player_id)
        if not player or not self._is_turn(player_id) or player.debt:
            raise ValueError("Cannot switch batsman now")
        if self.state.pending or self.state.market or self.state.auction:
            raise ValueError("Finish the current decision first")
        batsman = player.batsmen.get(batsman_id)
        if not batsman or not self._usable(batsman):
            raise ValueError("Batsman is not available")
        player.active_batsman_id = batsman.id
        self._emit("batsman_switched", player_id=player_id, batsman_id=batsman.id,
                   name=batsman.name, level=batsman.level, wickets=batsman.wickets)

    def gift_coins(self, player_id: str, to_player_id: str, amount: Any) -> None:
        """Send a bounded coin gift to another active manager.

        Gifts use the same atomic transfer helper as fees and trades. The
        sender must be on their own turn with no decision pending, may send
        only once per round, and must keep the configured reserve so gifting
        cannot be used to hide assets or force bankruptcy.
        """
        sender = self._player(player_id)
        receiver = self._player(to_player_id)
        if not sender or not receiver:
            raise ValueError("Player not found")
        if not self._is_turn(player_id) or self.state.phase == "over":
            raise ValueError("Gifts are only allowed on your own turn")
        if self.state.pending or self.state.market or self.state.auction:
            raise ValueError("Finish the current decision first")
        if sender.eliminated or receiver.eliminated or sender.debt or receiver.debt:
            raise ValueError("Both managers must be active and debt-free")
        if receiver.id == sender.id:
            raise ValueError("Choose another manager")
        if sender.gift_round == self.state.round:
            raise ValueError("You can send coins only once per round")

        try:
            value = int(amount)
        except (TypeError, ValueError):
            raise ValueError("Gift amount must be a number")
        if value < config.GIFT_MIN_COINS or value > config.GIFT_MAX_COINS:
            raise ValueError(
                f"Gift must be between {config.GIFT_MIN_COINS} and {config.GIFT_MAX_COINS} coins"
            )
        if sender.money - value < config.GIFT_RESERVE_COINS:
            raise ValueError(f"Keep at least {config.GIFT_RESERVE_COINS} coins in reserve")
        if not transfer(self.state, sender, receiver, value, "Manager gift"):
            raise ValueError("Insufficient funds")

        sender.gift_round = self.state.round
        sender.stats["coins_gifted"] += value
        receiver.stats["coins_received"] += value
        self._emit("coins_gifted", player_id=sender.id, to_player_id=receiver.id,
                   sender_name=sender.name, to_name=receiver.name, amount=value,
                   sender_balance=sender.money, receiver_balance=receiver.money)

    def roll_dice(self, player_id: str) -> dict:
        if not self._is_turn(player_id):
            raise ValueError("It is not this player's turn")
        player = self._player(player_id)
        assert player is not None
        if player.debt:
            raise ValueError("Settle your outstanding debt first")
        batsman = self.active_batsman(player)
        if batsman is None:
            if self._can_recruit(player):
                raise ValueError("Recruit a batsman before rolling")
            raise ValueError("No usable batsman")

        dice = [self.rng.randint(1, config.DICE_SIDES) for _ in range(config.DICE_COUNT)]
        total = sum(dice)
        is_double = len(set(dice)) == 1
        self.state.dice = dice
        self.state.doubles_count = self.state.doubles_count + 1 if is_double else 0
        self.state.phase = "moving"
        self._emit("dice", player_id=player_id, dice=dice, total=total,
                   is_double=is_double)

        old_pos = player.position
        new_pos = (old_pos + total) % BOARD_SIZE
        path = [(old_pos + step) % BOARD_SIZE for step in range(1, total + 1)]
        player.position = new_pos
        # The landing turn on No-ball is paid out first, then counted toward
        # the next cycle; ordinary landings count as normal turns.
        if not self.state.extra_turn and get_space(new_pos).type != "no_ball":
            player.no_ball_turns += 1
        self._emit("move", player_id=player_id, from_pos=old_pos, to_pos=new_pos,
                    path=path, batsman_id=batsman.id)

        passed_start = old_pos + total >= BOARD_SIZE
        if passed_start or new_pos == 0:
            salary = config.SALARY + self._sponsorship(player)
            credit(self.state, player, salary, "Salary / sponsorship")
            self._emit("salary", player_id=player_id, amount=salary)

        self.state.phase = "resolving"
        self._resolve_space(player, extra_roll=is_double)

        if self.state.phase == "resolving" and not self.state.pending and not self.state.auction:
            if not self.state.market and not player.debt:
                self._after_action(
                    (is_double and self.state.doubles_count < config.MAX_CONSECUTIVE_DOUBLES)
                    or self.state.extra_turn
                )
        self.state.turn_deadline = time.time() + config.DECISION_TIMEOUT_SECONDS * 2
        return {"dice": dice, "total": total, "position": new_pos}

    def _after_action(self, extra_roll: bool) -> None:
        if self.state.phase == "over":
            return
        player = self.state.current_player()
        if player and player.eliminated:
            self._advance_turn()
            return
        if extra_roll and self.state.doubles_count < config.MAX_CONSECUTIVE_DOUBLES:
            self.state.extra_turn = True
            self.state.phase = "await_roll"
            self._emit("extra_roll", player_id=self.state.current_player_id,
                       text="Extra turn!")
            return
        self._advance_turn()

    def _advance_turn(self) -> None:
        if self.state.phase == "over":
            return
        self.state.pending = None
        self.state.extra_turn = False
        self.state.doubles_count = 0
        self.state.dice = []
        self.state.market = None
        self._check_victory()
        if self.state.phase == "over":
            return
        alive = self._alive_ids()
        if not alive:
            self._finish("No managers remaining")
            return
        current = self.state.current_player_id
        idx = alive.index(current) if current in alive else -1
        next_idx = (idx + 1) % len(alive)
        if next_idx == 0 and idx >= 0:
            self.state.round += 1
        next_id = alive[next_idx]
        self.state.current_index = self.state.order.index(next_id)
        self.state.phase = "await_roll"
        self.state.turn_deadline = time.time() + config.DECISION_TIMEOUT_SECONDS * 2
        for player in self.state.players.values():
            for key in ("powerplay_rounds", "poor_form_rounds", "injury_rounds"):
                if player.effects.get(key, 0) > 0:
                    player.effects[key] -= 1
            for asset in player.assets.values():
                if asset.injured_until_round and asset.injured_until_round <= self.state.round:
                    asset.injured_until_round = 0
                if asset.debuff_until_round and asset.debuff_until_round <= self.state.round:
                    asset.debuff_until_round = 0
        next_player = self.state.players[next_id]
        next_player.stats["turns"] += 1
        if self.state.round >= 5:
            self._award(next_player, "survivor")
        if not self.active_batsman(next_player):
            recruitable = self._can_recruit(next_player)
            self._emit("turn_wait" if not next_player.connected else "recruit_required",
                       player_id=next_id, round=self.state.round,
                       can_recruit=recruitable)
        elif next_player.connected:
            self._emit("turn_start", player_id=next_id, round=self.state.round)
        else:
            self._emit("turn_wait", player_id=next_id, round=self.state.round)
        self._check_victory()

    # ------------------------------------------------------------------
    # Space resolution
    # ------------------------------------------------------------------
    def _resolve_space(self, player: Player, extra_roll: bool = False) -> None:
        space = get_space(player.position)
        batsman = self.active_batsman(player)
        if space.type == "start":
            return
        if space.type in ("property", "stadium"):
            owner = self.state.owner_of(player.position)
            if owner is None:
                self.state.pending = {
                    "type": "purchase", "player_id": player.id,
                    "space_id": player.position, "extra_roll": extra_roll,
                    "expires_at": time.time() + config.DECISION_TIMEOUT_SECONDS,
                }
                self._emit("purchase_offer", player_id=player.id,
                           space_id=player.position, space=space.to_dict(),
                           price=space.price)
            elif owner.id == player.id:
                self._emit("own_property", player_id=player.id, space_id=space.id)
            else:
                self._apply_property(player, owner)
            return
        if space.type == "event":
            self._draw_event(player)
            return
        if space.type in ("run_1", "run_2", "run_4"):
            amount = int(space.type.split("_")[1])
            self._add_runs(player, amount, f"{amount} RUN{'S' if amount > 1 else ''}", batsman)
            self._emit("scoring", player_id=player.id, label=space.name,
                       runs=amount, money=0)
            return
        if space.type == "run_6":
            level = batsman.level if batsman else 1
            amount = config.SIX_RUNS_PER_LEVEL * level
            player.stats["six_runs"] += amount
            self._add_runs(player, amount, "SIX", batsman)
            self._emit("six", player_id=player.id, level=level,
                       multiplier=config.SIX_RUNS_PER_LEVEL, runs=amount,
                       batsman_id=batsman.id if batsman else None)
            return
        if space.type == "no_ball":
            turns = player.no_ball_turns
            bonus = turns * config.NO_BALL_RUNS_PER_TURN
            # Reset after paying out, then count the landing turn toward the
            # next cycle (extra turns never increment this counter).
            player.no_ball_turns = 1
            player.no_ball_protection = min(config.NO_BALL_MAX_PROTECTION,
                                            player.no_ball_protection + 1)
            player.stats["no_ball_bonus_runs"] += bonus
            self._add_runs(player, bonus, "No-ball bonus", batsman)
            self._emit("no_ball", player_id=player.id, turns=turns,
                       per_turn=config.NO_BALL_RUNS_PER_TURN, bonus=bonus,
                       protection=player.no_ball_protection,
                       text=f"{turns} turns × {config.NO_BALL_RUNS_PER_TURN} = {bonus} bonus runs")
            self.state.extra_turn = True
            self._after_action(True)
            return
        if space.type == "recruit":
            self._open_market(player)
            return
        if space.type == "free_hit":
            player.effects["free_hit"] = player.effects.get("free_hit", 0) + config.FREE_HIT_BLOCKS
            self._emit("free_hit", player_id=player.id,
                       charges=player.effects["free_hit"])
            return
        if space.type == "rest":
            self._emit("rest", player_id=player.id)
            return
        if space.type == "auction":
            self._start_auction(player.id, None, extra_roll)
            return
        if space.type == "injury":
            target = batsman or (self.rng.choice(self._usable_batsmen(player)) if self._usable_batsmen(player) else None)
            if target:
                target.injured_until_round = self.state.round + config.INJURY_ROUNDS
            self._emit("injury", player_id=player.id,
                       batsman_id=target.id if target else None,
                       name=target.name if target else None, rounds=config.INJURY_ROUNDS)
            return
        if space.type == "challenge":
            self._challenge(player)
            return
        if space.type == "out":
            self._take_wicket(player, config.OUT_SPACE_WICKETS, "Out space",
                              specific_batsman=batsman)
            return

    def _open_market(self, player: Player) -> None:
        available = self._available_identities()
        if not available or len(self._batsmen(player)) >= config.MAX_BATSMEN_PER_PLAYER:
            self._emit("market_empty", player_id=player.id,
                       text="No batsmen available for recruitment.")
            return
        options = []
        for key in available[:6]:
            info = config.FAMOUS_BATSMEN[key]
            options.append({"identity_id": key, "name": info["name"],
                            "country": info["country"], "avatar": info["avatar"],
                            "jersey_color": info["jersey_color"],
                            "jersey_number": info["jersey_number"],
                            "price": config.RECRUITMENT_COST,
                            "wickets": config.BATSMAN_STARTING_WICKETS,
                            "level": 1, "available": True})
        self.state.market = {
            "player_id": player.id, "price": config.RECRUITMENT_COST,
            "options": options,
            "expires_at": time.time() + config.DECISION_TIMEOUT_SECONDS * 2,
        }
        self._emit("market_offer", player_id=player.id, options=options,
                   price=config.RECRUITMENT_COST)

    def _draw_event(self, player: Player) -> None:
        card = draw_card(self.state, self.rng)
        if card["kind"] == "bad" and self.rng.random() < self._event_guard_chance(player):
            self._emit("event_guarded", player_id=player.id, card=card,
                       text="Your keeper guarded the bad card!")
            return
        self._emit("event_card", player_id=player.id, card=card)
        self._apply_effect(player, card["effect"], card["name"])

    def _challenge(self, player: Player) -> None:
        challenge = self.rng.choice(config.CHALLENGES)
        success = self.rng.random() < challenge["success"]
        self._emit("challenge", player_id=player.id, challenge=challenge, success=success)
        self._apply_effect(player, challenge["reward"] if success else challenge["fail"],
                           challenge["name"])

    def _apply_effect(self, player: Player, effect: dict, reason: str) -> None:
        batsman = self.active_batsman(player)
        if effect.get("runs"):
            self._add_runs(player, effect["runs"], reason, batsman)
        if effect.get("money"):
            amount = effect["money"]
            if amount > 0:
                credit(self.state, player, amount, reason)
            else:
                self._charge_or_debt(player, None, -amount, reason)
        if effect.get("free_hit"):
            player.effects["free_hit"] = player.effects.get("free_hit", 0) + effect["free_hit"]
        if effect.get("powerplay"):
            player.effects["powerplay_rounds"] = max(player.effects.get("powerplay_rounds", 0),
                                                     effect["powerplay"])
        if effect.get("poor_form"):
            player.effects["poor_form_rounds"] = max(player.effects.get("poor_form_rounds", 0),
                                                     effect["poor_form"])
        if effect.get("wicket"):
            self._take_wicket(player, effect["wicket"], reason)
        self._check_elimination(player)

    def _event_guard_chance(self, player: Player) -> float:
        chance = max((a.config.get("event_guard", 0) + 0.05 * a.level
                      for a in player.assets.values() if a.kind == "keeper" and a.active),
                     default=0.0)
        return min(chance, 0.5)

    def _income_reduction(self, player: Player) -> float:
        return min(max((a.config.get("income_reduction", 0) + 0.05 * a.level
                        for a in player.assets.values() if a.kind == "fielder" and a.active),
                       default=0.0), 0.5)

    def _reward_reduction(self, player: Player) -> float:
        return min(max((a.config.get("reward_reduction", 0) + 0.04 * a.level
                        for a in player.assets.values() if a.kind == "fielder" and a.active),
                       default=0.0), 0.4)

    # ------------------------------------------------------------------
    # Property interactions / debt
    # ------------------------------------------------------------------
    def _charge_or_debt(self, payer: Player, receiver: Player | None,
                        amount: int, reason: str) -> bool:
        """Charge a payment. On shortfall, open a recoverable debt decision."""
        amount = int(amount)
        if amount <= 0:
            return True
        if payer.money >= amount:
            if receiver:
                transfer(self.state, payer, receiver, amount, reason)
            else:
                debit(self.state, payer, amount, reason)
            return True
        partial = max(0, payer.money)
        if partial:
            debit(self.state, payer, partial, reason,
                  target_id=receiver.id if receiver else None)
            if receiver:
                credit(self.state, receiver, partial, reason, source_id=payer.id)
        remainder = amount - partial
        debt = {
            "payer_id": payer.id, "receiver_id": receiver.id if receiver else None,
            "amount": remainder, "reason": reason,
            "paid": partial, "original": amount,
            "expires_at": time.time() + config.DECISION_TIMEOUT_SECONDS * 2,
        }
        payer.debt = debt
        self.state.pending = {"type": "debt", "player_id": payer.id,
                              "expires_at": debt["expires_at"]}
        self._emit("debt_incurred", player_id=payer.id,
                   receiver_id=receiver.id if receiver else None,
                   amount=remainder, reason=reason, paid=partial)
        return False

    def _apply_property(self, visitor: Player, owner: Player) -> None:
        if owner.eliminated:
            self._emit("inactive_property", player_id=visitor.id, owner_id=owner.id)
            return
        asset = self.state.asset_at(visitor.position)
        if asset is None:
            return
        if owner.id == visitor.id:
            self._emit("own_property", player_id=visitor.id, space_id=asset.space_id,
                       name=asset.name)
            return
        values = asset.to_dict()
        fee = int(values.get("effective_fee", 0))
        paid = self._charge_or_debt(visitor, owner, fee, f"Fee at {asset.name}")
        self._emit("fee", player_id=visitor.id, owner_id=owner.id, asset_id=asset.id,
                   amount=fee, paid=fee if paid else values.get("effective_fee", 0) - (visitor.debt or {}).get("amount", 0),
                   property_kind=asset.kind, name=asset.name)
        if not paid:
            return

        if asset.kind == "bowler":
            active = self.active_batsman(visitor)
            if visitor.no_ball_protection > 0:
                visitor.no_ball_protection -= 1
                visitor.stats["wickets_saved"] += 1
                self._emit("wicket_protected", player_id=visitor.id,
                           owner_id=owner.id, asset_id=asset.id,
                           text="No-ball protection absorbed the wicket — fee still paid.")
                return
            results = self._take_wicket(visitor, 1, f"Bowler {asset.name}",
                                        attacker_id=owner.id, specific_batsman=active)
            self._emit("bowler_attack", player_id=visitor.id, owner_id=owner.id,
                       asset_id=asset.id, name=asset.name, fee=fee, wickets=results)
            return
        if asset.kind == "keeper":
            penalty = int(values.get("run_penalty", 0))
            deducted = min(visitor.runs, penalty)
            if deducted:
                self._add_runs(visitor, -deducted, f"Wicketkeeper {asset.name}")
            self._emit("keeper_penalty", player_id=visitor.id, owner_id=owner.id,
                       asset_id=asset.id, fee=fee, runs_lost=deducted)
        # Fielders charge only the landing fee.

    def pay_debt(self, player_id: str) -> None:
        player = self._player(player_id)
        if not player or not player.debt:
            raise ValueError("No outstanding debt")
        debt = player.debt
        if player.money < debt["amount"]:
            raise ValueError("Insufficient funds")
        receiver = self._player(debt["receiver_id"]) if debt.get("receiver_id") else None
        if receiver:
            transfer(self.state, player, receiver, debt["amount"],
                     f"Debt settlement: {debt['reason']}")
        else:
            debit(self.state, player, debt["amount"], f"Debt settlement: {debt['reason']}")
        player.debt = None
        self.state.pending = None
        self._emit("debt_paid", player_id=player_id, amount=debt["amount"],
                   reason=debt["reason"])
        self._check_elimination(player)
        self._after_action(False)

    def declare_bankruptcy(self, player_id: str) -> None:
        player = self._player(player_id)
        if not player or not player.debt:
            raise ValueError("No outstanding debt")
        debt = player.debt
        receiver = self._player(debt["receiver_id"]) if debt.get("receiver_id") else None
        if receiver:
            amount = max(0, player.money)
            if amount:
                debit(self.state, player, amount, "Bankruptcy settlement")
                credit(self.state, receiver, amount, "Bankruptcy settlement",
                       source_id=player.id)
        self._emit("bankrupt", player_id=player_id,
                   receiver_id=receiver.id if receiver else None,
                   reason=debt["reason"])
        self._eliminate(player, "Bankrupt", receiver)
        self._after_action(False)

    # ------------------------------------------------------------------
    # Purchase decisions
    # ------------------------------------------------------------------
    def _require_pending(self, player_id: str, kind: str) -> dict:
        pending = self.state.pending
        if not pending or pending.get("type") != kind or pending.get("player_id") != player_id:
            raise ValueError("No matching pending decision")
        return pending

    def _create_asset(self, player: Player, space_id: int) -> Asset:
        space = get_space(space_id)
        assert space.kind and space.category
        table = {
            "bowler": config.BOWLERS, "keeper": config.WICKET_KEEPERS,
            "fielder": config.FIELDERS, "stadium": config.STADIUMS,
            "batsman": config.BATSMEN,
        }
        info = table.get(space.kind, {}).get(space.category, {})
        wickets = int(info.get("wickets", 0))
        return Asset(
            id=f"space:{space_id}", owner_id=player.id, space_id=space_id,
            kind=space.kind, category=space.category, name=space.name,
            wickets=wickets, max_wickets=wickets, active=True,
        )

    def buy_property(self, player_id: str) -> None:
        pending = self._require_pending(player_id, "purchase")
        player = self._player(player_id)
        assert player is not None
        space_id = pending["space_id"]
        price = get_space(space_id).price
        if player.money < price:
            raise ValueError("Insufficient funds")
        if self.state.owner_of(space_id) is not None:
            raise ValueError("Property already owned")
        debit(self.state, player, price, f"Purchased space {space_id}")
        asset = self._create_asset(player, space_id)
        player.assets[asset.id] = asset
        player.stats["properties_bought"] += 1
        self.state.pending = None
        self._emit("purchase", player_id=player_id, asset=asset.to_dict(), price=price)
        self._award(player, "first_purchase")
        if asset.kind == "stadium":
            self._award(player, "stadium_owner")
        self._after_action(bool(pending.get("extra_roll")))

    def skip_property(self, player_id: str) -> None:
        pending = self._require_pending(player_id, "purchase")
        self.state.pending = None
        self._emit("skip", player_id=player_id, space_id=pending["space_id"])
        self._after_action(bool(pending.get("extra_roll")))

    def auction_property(self, player_id: str) -> None:
        pending = self._require_pending(player_id, "purchase")
        space_id = pending["space_id"]
        extra = bool(pending.get("extra_roll"))
        self.state.pending = None
        self._start_auction(player_id, space_id, extra)

    # ------------------------------------------------------------------
    # Recruitment
    # ------------------------------------------------------------------
    def recruit_batsman(self, player_id: str, identity_id: str) -> None:
        market = self.state.market
        if not market or market.get("player_id") != player_id:
            raise ValueError("No recruitment market for this player")
        player = self._player(player_id)
        if not player:
            raise ValueError("Player not found")
        if len(self._batsmen(player)) >= config.MAX_BATSMEN_PER_PLAYER:
            raise ValueError("Roster is full")
        price = int(market["price"])
        if player.money < price:
            raise ValueError("Insufficient funds")
        if identity_id not in [o["identity_id"] for o in market["options"]]:
            raise ValueError("Batsman not available in this market")
        if identity_id in self._claimed_identities():
            raise ValueError("Batsman already claimed")
        if not debit(self.state, player, price, "Batsman recruitment"):
            raise ValueError("Insufficient funds")
        batsman = self._create_batsman(player, identity_id)
        player.stats["batsmen_recruited"] += 1
        self.state.market = None
        self._emit("batsman_recruited", player_id=player_id,
                   batsman=batsman.to_dict(), price=price)
        self.state.pending = {
            "type": "recruit_activate", "player_id": player_id,
            "batsman_id": batsman.id,
            "expires_at": time.time() + config.DECISION_TIMEOUT_SECONDS,
        }

    def decline_recruit(self, player_id: str) -> None:
        market = self.state.market
        if not market or market.get("player_id") != player_id:
            raise ValueError("No recruitment market for this player")
        self.state.market = None
        self._emit("recruit_declined", player_id=player_id)
        self._check_elimination(self._player(player_id))  # type: ignore[arg-type]
        self._after_action(False)

    def activate_recruit(self, player_id: str, activate: bool) -> None:
        pending = self._require_pending(player_id, "recruit_activate")
        player = self._player(player_id)
        assert player is not None
        batsman_id = pending["batsman_id"]
        if activate:
            batsman = player.batsmen.get(batsman_id)
            if not batsman or not self._usable(batsman):
                raise ValueError("Batsman is not available")
            player.active_batsman_id = batsman_id
            self._emit("batsman_activated", player_id=player_id, batsman_id=batsman_id,
                       name=batsman.name)
        else:
            self._emit("recruit_kept_in_reserve", player_id=player_id,
                       batsman_id=batsman_id)
        if not self.active_batsman(player):
            first = next(iter(self._usable_batsmen(player)), None)
            if first:
                player.active_batsman_id = first.id
        self.state.pending = None
        self._check_elimination(player)
        self._after_action(False)

    # ------------------------------------------------------------------
    # Auctions
    # ------------------------------------------------------------------
    def _start_auction(self, initiator_id: str, space_id: int | None, extra_roll: bool) -> None:
        if space_id is None:
            candidates = [s.id for s in
                          [get_space(i) for i in range(BOARD_SIZE)]
                          if s.price > 0 and self.state.owner_of(s.id) is None]
            if not candidates:
                self._emit("auction_skipped", player_id=initiator_id,
                           text="No properties available for auction.")
                self._after_action(extra_roll)
                return
            space_id = self.rng.choice(candidates)
        self.state.auction = {
            "space_id": space_id, "space": get_space(space_id).to_dict(),
            "started_by": initiator_id,
            "ends_at": time.time() + config.AUCTION_DURATION_SECONDS,
            "highest_bid": 0, "highest_bidder": None, "bids": [],
            "extra_roll": extra_roll,
        }
        self._emit("auction_start", player_id=initiator_id,
                   space_id=space_id, space=self.state.auction["space"],
                   duration=config.AUCTION_DURATION_SECONDS)

    def place_bid(self, player_id: str, amount: int) -> None:
        auction = self.state.auction
        if not auction:
            raise ValueError("No active auction")
        player = self._player(player_id)
        if not player or player.eliminated or player.debt:
            raise ValueError("Player cannot bid")
        amount = int(amount)
        if amount <= auction["highest_bid"]:
            raise ValueError("Bid must exceed the current bid")
        if amount > player.money:
            raise ValueError("Insufficient funds")
        auction["highest_bid"] = amount
        auction["highest_bidder"] = player_id
        auction["bids"].append({"player_id": player_id, "amount": amount})
        self._emit("auction_bid", player_id=player_id, amount=amount)

    def _resolve_auction(self) -> None:
        auction = self.state.auction
        if not auction:
            return
        self.state.auction = None
        space_id = auction["space_id"]
        winner_id = auction["highest_bidder"]
        if winner_id and self.state.owner_of(space_id) is None:
            player = self._player(winner_id)
            if player and player.money >= auction["highest_bid"]:
                debit(self.state, player, auction["highest_bid"],
                      f"Auction won for space {space_id}")
                asset = self._create_asset(player, space_id)
                player.assets[asset.id] = asset
                player.stats["properties_bought"] += 1
                self._emit("auction_won", player_id=winner_id, asset=asset.to_dict(),
                           price=auction["highest_bid"])
                self._award(player, "first_purchase")
            else:
                self._emit("auction_failed", player_id=winner_id)
        else:
            self._emit("auction_unsold", space_id=space_id)
        self._after_action(bool(auction.get("extra_roll")))

    # ------------------------------------------------------------------
    # Batsman upgrades / property upgrades & selling
    # ------------------------------------------------------------------
    def upgrade_batsman(self, player_id: str, batsman_id: str) -> None:
        if not self.state.started or self.state.phase == "over":
            raise ValueError("Game is not active")
        player = self._player(player_id)
        if not player or player.eliminated:
            raise ValueError("Invalid player")
        if player.debt:
            raise ValueError("Settle your debt before upgrading")
        batsman = player.batsmen.get(batsman_id)
        if not batsman or batsman.retired:
            raise ValueError("Batsman not found")
        if batsman.level >= config.MAX_BATSMAN_LEVEL:
            raise ValueError("Batsman is already at maximum level")
        cost = config.BATSMAN_UPGRADE_COSTS.get(batsman.level)
        if cost is None or not debit(self.state, player, cost, f"Upgraded {batsman.name}"):
            raise ValueError("Insufficient funds")
        before = batsman.six_runs
        batsman.level += 1
        player.stats["batsman_upgrades"] += 1
        self._emit("batsman_upgraded", player_id=player_id, batsman_id=batsman_id,
                   level=batsman.level, cost=cost,
                   six_runs_before=before, six_runs_after=batsman.six_runs)

    def upgrade_asset(self, player_id: str, asset_id: str) -> None:
        if not self.state.started or self.state.phase == "over":
            raise ValueError("Game is not active")
        player = self._player(player_id)
        if not player or player.eliminated or player.debt:
            raise ValueError("Invalid player")
        asset = player.assets.get(asset_id)
        if not asset or asset.space_id is None:
            raise ValueError("Asset not found")
        if asset.level >= config.MAX_LEVEL:
            raise ValueError("Asset is already at maximum level")
        cost = int(asset.to_dict()["upgrade_cost"])
        if not debit(self.state, player, cost, f"Upgraded {asset.name}"):
            raise ValueError("Insufficient funds")
        asset.level += 1
        self._emit("upgrade", player_id=player_id, asset_id=asset_id,
                   level=asset.level, cost=cost,
                   fee=asset.to_dict()["effective_fee"])

    def downgrade_asset(self, player_id: str, asset_id: str) -> None:
        """Raise cash during debt recovery by surrendering one property level."""
        player = self._player(player_id)
        if not player or not player.debt:
            raise ValueError("Downgrades are only allowed while in debt")
        asset = player.assets.get(asset_id)
        if not asset or asset.space_id is None or asset.level <= 0:
            raise ValueError("Asset cannot be downgraded")
        base = int(asset.config.get("upgrade_cost", 0))
        refund = int(base * (1 + config.PROPERTY_LEVEL_INCOME_MULTIPLIER * (asset.level - 1)) * 0.6)
        asset.level -= 1
        credit(self.state, player, refund, f"Downgraded {asset.name}")
        self._emit("downgrade", player_id=player_id, asset_id=asset_id,
                   level=asset.level, refund=refund)

    def sell_asset(self, player_id: str, asset_id: str) -> None:
        if not self.state.started or self.state.phase == "over":
            raise ValueError("Game is not active")
        player = self._player(player_id)
        if not player or player.eliminated:
            raise ValueError("Invalid player")
        asset = player.assets.get(asset_id)
        if not asset or asset.space_id is None:
            raise ValueError("Asset not found")
        refund = int(asset.to_dict()["sale_value"])
        credit(self.state, player, refund, f"Sold {asset.name}")
        del player.assets[asset_id]
        self._emit("sold", player_id=player_id, asset_id=asset_id, refund=refund)

    # ------------------------------------------------------------------
    # Trading
    # ------------------------------------------------------------------
    def propose_trade(self, from_id: str, to_id: str, give_assets: list[str],
                      give_money: int, want_assets: list[str], want_money: int) -> str:
        if not self.state.started or self.state.phase == "over":
            raise ValueError("Game is not active")
        sender, receiver = self._player(from_id), self._player(to_id)
        if not sender or not receiver or sender.eliminated or receiver.eliminated:
            raise ValueError("Invalid player")
        if sender.debt or receiver.debt:
            raise ValueError("Cannot trade while a debt is outstanding")
        if from_id == to_id:
            raise ValueError("Cannot trade with yourself")
        give_money, want_money = int(give_money), int(want_money)
        if give_money < 0 or want_money < 0:
            raise ValueError("Money amounts must be positive")
        if give_money > sender.money:
            raise ValueError("Insufficient funds")
        if want_money > receiver.money:
            raise ValueError("Counterparty lacks funds")
        for aid in give_assets:
            a = sender.assets.get(aid)
            if not a or a.space_id is None:
                raise ValueError("Invalid offered asset")
        for aid in want_assets:
            a = receiver.assets.get(aid)
            if not a or a.space_id is None:
                raise ValueError("Invalid requested asset")
        trade_id = f"trade:{len(self.state.trades) + 1}:{int(time.time() * 1000)}"
        self.state.trades[trade_id] = {
            "id": trade_id, "from": from_id, "to": to_id,
            "give_assets": list(give_assets), "give_money": give_money,
            "want_assets": list(want_assets), "want_money": want_money,
            "status": "pending",
        }
        self._emit("trade_proposed", trade_id=trade_id, **self.state.trades[trade_id])
        return trade_id

    def respond_trade(self, trade_id: str, player_id: str, accept: bool) -> None:
        trade = self.state.trades.get(trade_id)
        if not trade or trade["status"] != "pending":
            raise ValueError("Trade not found")
        if trade["to"] != player_id:
            raise ValueError("Only the recipient can respond")
        sender, receiver = self._player(trade["from"]), self._player(trade["to"])
        if not sender or not receiver:
            raise ValueError("Invalid player")
        self.state.trades.pop(trade_id, None)
        if not accept:
            self._emit("trade_declined", trade_id=trade_id, player_id=player_id)
            return
        if not self._trade_valid(trade, sender, receiver):
            self._emit("trade_failed", trade_id=trade_id,
                       text="Trade could not be completed because assets or funds changed.")
            return
        for aid in trade["give_assets"]:
            asset = sender.assets.pop(aid)
            asset.owner_id = receiver.id
            receiver.assets[aid] = asset
        for aid in trade["want_assets"]:
            asset = receiver.assets.pop(aid)
            asset.owner_id = sender.id
            sender.assets[aid] = asset
        if trade["give_money"]:
            transfer(self.state, sender, receiver, trade["give_money"], "Trade settlement")
        if trade["want_money"]:
            transfer(self.state, receiver, sender, trade["want_money"], "Trade settlement")
        self._emit("trade_completed", trade_id=trade_id, **trade)

    def _trade_valid(self, trade: dict, sender: Player, receiver: Player) -> bool:
        if sender.money < trade["give_money"] or receiver.money < trade["want_money"]:
            return False
        return (all(a in sender.assets and sender.assets[a].space_id is not None
                    for a in trade["give_assets"]) and
                all(a in receiver.assets and receiver.assets[a].space_id is not None
                    for a in trade["want_assets"]))

    # ------------------------------------------------------------------
    # Connection & timing
    # ------------------------------------------------------------------
    def set_connected(self, player_id: str, connected: bool) -> None:
        player = self._player(player_id)
        if player:
            player.connected = connected
            self._emit("presence", player_id=player_id, connected=connected)

    def tick(self, now: float | None = None) -> None:
        """Resolve timers: auctions, decisions, debts and AFK turns."""
        now = now if now is not None else time.time()
        if self.state.auction and now >= self.state.auction["ends_at"]:
            self._resolve_auction()

        pending = self.state.pending
        if pending and now >= pending.get("expires_at", now + 1):
            self.state.pending = None
            pid = pending.get("player_id")
            kind = pending["type"]
            self._emit("decision_timeout", player_id=pid, type=kind)
            player = self._player(pid) if pid else None
            if kind == "purchase":
                self._after_action(bool(pending.get("extra_roll")))
            elif kind == "recruit_activate" and player:
                if not self.active_batsman(player):
                    first = next(iter(self._usable_batsmen(player)), None)
                    if first:
                        player.active_batsman_id = first.id
                self._check_elimination(player)  # type: ignore[arg-type]
                self._after_action(False)

        if self.state.market and now >= self.state.market.get("expires_at", now + 1):
            pid = self.state.market.get("player_id")
            self.state.market = None
            self._emit("market_closed", player_id=pid)
            self._after_action(False)

        for player in list(self.state.players.values()):
            if player.debt and now >= player.debt.get("expires_at", now + 1):
                self._emit("debt_timeout", player_id=player.id)
                self.declare_bankruptcy(player.id)

        if (self.state.started and self.state.phase == "await_roll"
                and not self.state.auction and not self.state.pending
                and not self.state.market
                and now >= self.state.turn_deadline):
            pid = self.state.current_player_id
            player = self._player(pid) if pid else None
            if player and not player.eliminated and not player.debt:
                batsman = self.active_batsman(player)
                if batsman is None and self._can_recruit(player):
                    options = self._available_identities()
                    if options:
                        self.state.market = {
                            "player_id": player.id, "price": config.RECRUITMENT_COST,
                            "options": [{"identity_id": k, "name": config.FAMOUS_BATSMEN[k]["name"],
                                         "country": config.FAMOUS_BATSMEN[k]["country"],
                                         "avatar": config.FAMOUS_BATSMEN[k]["avatar"],
                                         "jersey_color": config.FAMOUS_BATSMEN[k]["jersey_color"],
                                         "jersey_number": config.FAMOUS_BATSMEN[k]["jersey_number"],
                                         "price": config.RECRUITMENT_COST, "wickets": 3,
                                         "level": 1, "available": True}
                                        for k in options[:6]],
                            "expires_at": now + config.DECISION_TIMEOUT_SECONDS * 2,
                        }
                elif batsman:
                    self._emit("auto_roll", player_id=pid)
                    self.roll_dice(pid)

    def public_state(self, viewer_id: str | None = None) -> dict:
        return self.state.to_dict(viewer_id)
