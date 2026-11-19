"""Deterministic engine tests for the Phase 7 gameplay overhaul."""

from __future__ import annotations

import time

import pytest

from app import config
from app.game.engine import GameEngine
from app.models import Batsman, GameState
from .conftest import ScriptedRng, give_property, make_engine


def set_turn(state: GameState, player_id: str) -> None:
    state.current_index = state.order.index(player_id)
    state.phase = "await_roll"
    state.pending = None
    state.market = None
    state.extra_turn = False
    state.dice = []
    state.players[player_id].debt = None


def travel(engine: GameEngine, state: GameState, player_id: str,
           target: int, total: int = 3, dice: list[int] | None = None) -> dict:
    """Place a player before the target and roll deterministic dice onto it."""
    state.players[player_id].position = (target - total) % 32
    set_turn(state, player_id)
    return engine.roll_dice(player_id)


def active(state: GameState, player_id: str) -> Batsman:
    return state.players[player_id].batsmen[state.players[player_id].active_batsman_id]


def kinds(engine: GameEngine) -> set[str]:
    return {e["type"] for e in engine.take_events()}


# ---------------------------------------------------------------------------
# Draft / roster setup
# ---------------------------------------------------------------------------
def test_every_player_starts_with_one_identical_famous_batsman():
    engine, state = make_engine(2)
    assert state.started and state.phase == "await_roll"
    identities = set()
    for player in state.players.values():
        assert len(player.batsmen) == 1
        batsman = next(iter(player.batsmen.values()))
        assert batsman.wickets == 3 and batsman.max_wickets == 3
        assert batsman.level == 1 and batsman.six_runs == 6
        assert player.active_batsman_id == batsman.id
        identities.add(batsman.identity_id)
    assert len(identities) == 2


def test_famous_selection_is_globally_unique_and_custom_is_allowed():
    engine, state = make_engine(2, started=False)
    p0, p1 = state.order if state.order else list(state.players)
    engine.select_batsman(p0, "virat_kohli")
    with pytest.raises(ValueError):
        engine.select_batsman(p1, "virat_kohli")
    engine.create_batsman(p1, {"name": "My Star", "jersey_number": 7,
                               "jersey_color": "#ff0000", "skin": "#f1c27d",
                               "hair": "spiky", "face": "grin", "country": "Custom"})
    assert state.players[p1].selection["is_custom"] is True
    engine.start()
    assert active(state, p1).name == "My Star"
    assert active(state, p1).level == 1 and active(state, p1).wickets == 3


def test_max_five_batsmen_and_switching_preserves_individual_state():
    engine, state = make_engine(2)
    pid = state.current_player_id
    player = state.players[pid]
    for identity in list(config.FAMOUS_BATSMEN)[3:8]:
        batsman = engine._create_batsman(player, identity)
        batsman.level = 2
    assert len(player.batsmen) == 6  # helper bypasses roster cap by design
    player.batsmen = dict(list(player.batsmen.items())[:5])
    first, second = list(player.batsmen.values())[:2]
    first.wickets = 1
    engine.switch_batsman(pid, second.id)
    assert player.active_batsman_id == second.id
    engine.switch_batsman(pid, first.id)
    assert active(state, pid).wickets == 1 and active(state, pid).level == 1
    assert second.wickets == 3 and second.level == 2


# ---------------------------------------------------------------------------
# Runs / sixes
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("target,expected", [(1, 1), (4, 2), (7, 4)])
def test_fixed_run_tiles_ignore_batting_level(target, expected):
    engine, state = make_engine(2, ScriptedRng(dice=[1, 2]))
    pid = state.current_player_id
    active(state, pid).level = 5
    player = state.players[pid]
    before = player.runs
    travel(engine, state, pid, target)
    assert player.runs - before == expected
    assert {"runs", "scoring"} <= kinds(engine)


@pytest.mark.parametrize("level,expected", [(1, 6), (2, 12), (3, 18), (4, 24), (5, 30)])
def test_six_tile_uses_only_active_batsman_level(level, expected):
    engine, state = make_engine(2, ScriptedRng(dice=[1, 2]))
    pid = state.current_player_id
    active(state, pid).level = level
    before = state.players[pid].runs
    travel(engine, state, pid, 10)
    assert state.players[pid].runs - before == expected
    assert state.players[pid].stats["six_runs"] == expected
    assert "six" in kinds(engine)


# ---------------------------------------------------------------------------
# No-ball
# ---------------------------------------------------------------------------
def test_no_ball_bonus_calculation_reset_and_extra_turn():
    engine, state = make_engine(2, ScriptedRng(dice=[1, 2]))
    pid = state.current_player_id
    player = state.players[pid]
    player.no_ball_turns = 5
    before = player.runs
    travel(engine, state, pid, 12)
    assert player.runs - before == 30
    assert player.no_ball_turns == 1          # landing turn counts forward
    assert player.no_ball_protection == 1
    assert player.stats["no_ball_bonus_runs"] == 30
    assert state.extra_turn is True and state.current_player_id == pid
    events = engine.take_events()
    no_ball = next(e for e in events if e["type"] == "no_ball")
    assert no_ball["payload"]["bonus"] == 30
    assert no_ball["payload"]["text"] == "5 turns × 6 = 30 bonus runs"


def test_no_ball_extra_turn_does_not_increment_counter():
    engine, state = make_engine(2, ScriptedRng(dice=[1, 2, 3, 4]))
    pid = state.current_player_id
    player = state.players[pid]
    travel(engine, state, pid, 12)
    assert player.no_ball_turns == 1
    state.extra_turn = True
    state.phase = "await_roll"
    engine.roll_dice(pid)   # extra turn, must not increment
    assert player.no_ball_turns == 1


def test_no_ball_protection_absorbs_wicket_but_not_fee():
    engine, state = make_engine(2, ScriptedRng(dice=[1, 2]))
    owner_id = state.current_player_id
    give_property(state, owner_id, 11)  # County Bowler, fee 200
    pid = next(p for p in state.order if p != owner_id)
    set_turn(state, pid)
    visitor = state.players[pid]
    visitor.no_ball_protection = 1
    batsman = active(state, pid)
    before_wickets = batsman.wickets
    before_money = visitor.money
    owner_money = state.players[owner_id].money
    travel(engine, state, pid, 11)
    assert batsman.wickets == before_wickets
    assert visitor.no_ball_protection == 0
    assert visitor.money == before_money - config.BOWLERS["tier2"]["fee"]
    assert state.players[owner_id].money == owner_money + config.BOWLERS["tier2"]["fee"]
    events = kinds(engine)
    assert "wicket_protected" in events and "wicket" not in events


def test_protection_does_not_apply_to_fielder_and_does_not_stack():
    engine, state = make_engine(2, ScriptedRng(dice=[1, 2]))
    pid = state.current_player_id
    player = state.players[pid]
    player.no_ball_protection = 1
    travel(engine, state, pid, 5)   # fielder
    assert player.no_ball_protection == 1
    player.no_ball_protection = 5
    player.no_ball_turns = 2
    engine.rng.dice = [1, 2]
    travel(engine, state, pid, 12)
    assert player.no_ball_protection == config.NO_BALL_MAX_PROTECTION


# ---------------------------------------------------------------------------
# Wickets / retirement
# ---------------------------------------------------------------------------
def test_bowler_fee_and_exactly_one_wicket_from_active_batsman():
    engine, state = make_engine(2, ScriptedRng(dice=[1, 2]))
    owner_id = state.current_player_id
    give_property(state, owner_id, 11)
    pid = next(p for p in state.order if p != owner_id)
    visitor = state.players[pid]
    set_turn(state, pid)
    engine._create_batsman(visitor, "ms_dhoni")
    batsman = active(state, pid)
    before = batsman.wickets
    before_money = visitor.money
    travel(engine, state, pid, 11)
    assert active(state, pid).wickets == before - 1
    assert sum(b.wickets for b in visitor.batsmen.values()) == 5  # only one lost
    assert visitor.money == before_money - config.BOWLERS["tier2"]["fee"]
    assert {"fee", "bowler_attack", "wicket"} <= kinds(engine)


def test_final_wicket_retires_batsman_and_auto_switches():
    engine, state = make_engine(2, ScriptedRng(dice=[1, 2]))
    owner_id = state.current_player_id
    give_property(state, owner_id, 11)
    pid = next(p for p in state.order if p != owner_id)
    visitor = state.players[pid]
    second = engine._create_batsman(visitor, "ms_dhoni")
    set_turn(state, pid)
    first = active(state, pid)
    first.wickets = 1
    travel(engine, state, pid, 11)
    assert first.retired is True and first.wickets == 0
    assert visitor.active_batsman_id == second.id
    assert {"batsman_retired", "wicket"} <= kinds(engine)
    assert visitor.eliminated is False


def test_last_batsman_retirement_eliminates_and_declares_winner():
    engine, state = make_engine(2)
    victim = state.players[state.current_player_id]
    give_property(state, victim.id, 5)
    victim.money = 0  # cannot afford recruitment
    engine._take_wicket(victim, 3, "test")
    assert victim.eliminated is True
    assert state.phase == "over"
    assert state.winner_id != victim.id


# ---------------------------------------------------------------------------
# Defensive properties
# ---------------------------------------------------------------------------
def test_fielder_charges_fee_only():
    engine, state = make_engine(2, ScriptedRng(dice=[1, 2]))
    owner_id = state.current_player_id
    give_property(state, owner_id, 5)   # tier1 fielder, fee 30
    pid = next(p for p in state.order if p != owner_id)
    set_turn(state, pid)
    visitor = state.players[pid]
    before_money, before_runs = visitor.money, visitor.runs
    before_wickets = active(state, pid).wickets
    travel(engine, state, pid, 5)
    assert visitor.money == before_money - config.FIELDERS["tier1"]["fee"]
    assert visitor.runs == before_runs
    assert active(state, pid).wickets == before_wickets
    assert state.players[owner_id].money == config.STARTING_MONEY + config.FIELDERS["tier1"]["fee"]


def test_keeper_charges_fee_and_caps_run_penalty_at_zero():
    engine, state = make_engine(2, ScriptedRng(dice=[1, 2]))
    owner_id = state.current_player_id
    give_property(state, owner_id, 8)   # tier1 keeper, fee 60, 2 runs
    pid = next(p for p in state.order if p != owner_id)
    set_turn(state, pid)
    visitor = state.players[pid]
    visitor.runs = 1
    before_money = visitor.money
    before_wickets = active(state, pid).wickets
    travel(engine, state, pid, 8)
    assert visitor.money == before_money - config.WICKET_KEEPERS["tier1"]["fee"]
    assert visitor.runs == 0
    assert active(state, pid).wickets == before_wickets
    assert "keeper_penalty" in kinds(engine)


def test_own_property_never_charges_and_lands_repeatedly():
    engine, state = make_engine(2, ScriptedRng(dice=[1, 2]))
    pid = state.current_player_id
    give_property(state, pid, 11)
    before = state.players[pid].money
    for _ in range(2):
        set_turn(state, pid)
        state.players[pid].position = 8
        engine.roll_dice(pid)
    assert state.players[pid].money == before
    assert active(state, pid).wickets == 3


def test_property_purchase_validation_and_duplicate_ownership():
    engine, state = make_engine(2, ScriptedRng(dice=[1, 2]))
    pid = state.current_player_id
    travel(engine, state, pid, 2)
    assert state.pending["type"] == "purchase"
    state.players[pid].money = 50
    with pytest.raises(ValueError):
        engine.buy_property(pid)
    state.players[pid].money = 2000
    engine.buy_property(pid)
    assert "space:2" in state.players[pid].assets
    assert state.owner_of(2).id == pid


# ---------------------------------------------------------------------------
# Upgrades / recruitment
# ---------------------------------------------------------------------------
def test_batsman_upgrade_costs_levels_and_max():
    engine, state = make_engine(2)
    pid = state.current_player_id
    player = state.players[pid]
    player.money = 5000
    batsman = active(state, pid)
    for level, cost in config.BATSMAN_UPGRADE_COSTS.items():
        assert batsman.six_runs == level * 6
        engine.upgrade_batsman(pid, batsman.id)
        assert batsman.level == level + 1
        assert player.money == 5000 - sum(list(config.BATSMAN_UPGRADE_COSTS.values())[:level])
    assert batsman.level == 5 and batsman.wickets == 3
    with pytest.raises(ValueError):
        engine.upgrade_batsman(pid, batsman.id)


def test_batsman_upgrade_is_selected_only():
    engine, state = make_engine(2)
    pid = state.current_player_id
    player = state.players[pid]
    player.money = 1000
    first = active(state, pid)
    second = engine._create_batsman(player, "ms_dhoni")
    engine.upgrade_batsman(pid, first.id)
    assert first.level == 2 and second.level == 1
    assert first.wickets == second.wickets == 3


def test_recruitment_market_buy_decline_and_cap():
    engine, state = make_engine(2, ScriptedRng(dice=[1, 2]))
    pid = state.current_player_id
    travel(engine, state, pid, 6)
    assert state.market and state.market["player_id"] == pid
    option = state.market["options"][0]["identity_id"]
    before = state.players[pid].money
    engine.recruit_batsman(pid, option)
    assert state.players[pid].money == before - config.RECRUITMENT_COST
    assert len(state.players[pid].batsmen) == 2
    assert state.pending["type"] == "recruit_activate"
    engine.activate_recruit(pid, True)
    assert active(state, pid).identity_id == option
    assert state.pending is None

    # Duplicate claiming is rejected even if a market somehow offers it again.
    state.market = {"player_id": pid, "price": 250,
                    "options": [{"identity_id": option}], "expires_at": time.time() + 10}
    with pytest.raises(ValueError):
        engine.recruit_batsman(pid, option)

    player = state.players[pid]
    for identity in list(config.FAMOUS_BATSMEN)[2:6]:
        engine._create_batsman(player, identity)
    player.batsmen = dict(list(player.batsmen.items())[:5])
    state.market = {"player_id": pid, "price": 250,
                    "options": [{"identity_id": "ben_stokes"}], "expires_at": time.time() + 10}
    with pytest.raises(ValueError):
        engine.recruit_batsman(pid, "ben_stokes")


def test_empty_market_when_all_identities_claimed():
    engine, state = make_engine(2, ScriptedRng(dice=[1, 2]))
    pid = state.current_player_id
    for identity in config.FAMOUS_BATSMEN:
        engine._create_batsman(state.players[pid], identity)
    travel(engine, state, pid, 6)
    assert state.market is None
    assert "market_empty" in kinds(engine)


def test_property_upgrade_increases_fee():
    engine, state = make_engine(2)
    pid = state.current_player_id
    asset = give_property(state, pid, 2)
    before = asset.to_dict()["effective_fee"]
    state.players[pid].money = 2000
    engine.upgrade_asset(pid, asset.id)
    assert asset.level == 1
    assert asset.to_dict()["effective_fee"] > before


# ---------------------------------------------------------------------------
# Debt / bankruptcy
# ---------------------------------------------------------------------------
def test_insufficient_fee_creates_debt_and_can_be_paid_after_selling():
    engine, state = make_engine(2, ScriptedRng(dice=[1, 2]))
    owner_id = state.current_player_id
    give_property(state, owner_id, 11)   # fee 200
    pid = next(p for p in state.order if p != owner_id)
    set_turn(state, pid)
    visitor = state.players[pid]
    asset = give_property(state, pid, 19)  # international bowler, resale value 400
    visitor.money = 50
    travel(engine, state, pid, 11)
    assert visitor.debt is not None
    assert visitor.debt["amount"] == 150
    assert state.pending["type"] == "debt"
    engine.sell_asset(pid, asset.id)
    assert visitor.money >= 50
    engine.pay_debt(pid)
    assert visitor.debt is None
    assert visitor.money >= 0


def test_bankruptcy_transfers_assets_and_eliminates():
    engine, state = make_engine(2, ScriptedRng(dice=[1, 2]))
    owner_id = state.current_player_id
    give_property(state, owner_id, 11)
    pid = next(p for p in state.order if p != owner_id)
    set_turn(state, pid)
    visitor = state.players[pid]
    asset = give_property(state, pid, 5)
    visitor.money = 0
    travel(engine, state, pid, 11)
    assert visitor.debt and visitor.debt["amount"] == 200
    engine.declare_bankruptcy(pid)
    assert visitor.eliminated is True
    assert asset.owner_id == owner_id
    assert asset.id in state.players[owner_id].assets
    assert state.phase == "over"


def test_debt_blocks_rolling_and_batsman_switching():
    engine, state = make_engine(2)
    pid = state.current_player_id
    player = state.players[pid]
    player.debt = {"amount": 100, "payer_id": pid, "receiver_id": None,
                   "reason": "test", "expires_at": time.time() + 30}
    engine._create_batsman(player, "ms_dhoni")
    second = list(player.batsmen.values())[-1]
    with pytest.raises(ValueError):
        engine.roll_dice(pid)
    with pytest.raises(ValueError):
        engine.switch_batsman(pid, second.id)


# ---------------------------------------------------------------------------
# Turn progression / victory
# ---------------------------------------------------------------------------
def test_turns_advance_and_eliminated_players_are_skipped():
    engine, state = make_engine(3)
    pid = state.current_player_id
    victim = next(p for p in state.order if p != pid)
    state.players[victim].eliminated = True
    state.phase = "resolving"
    engine._after_action(False)
    assert state.current_player_id != victim
    assert state.current_player_id in engine._alive_ids()


def test_turn_limit_victory_ranks_by_runs():
    engine, state = make_engine(3, started=False)
    p0, p1, p2 = list(state.players)
    engine.set_victory_mode(p0, "turn_limit", 3)
    engine.start()
    state.players[p0].runs = 10
    state.players[p1].runs = 50
    state.players[p2].runs = 30
    state.round = 4
    engine._check_victory()
    assert state.phase == "over"
    assert state.winner_id == p1
    assert state.ranking[0]["runs"] == 50


def test_victory_settings_are_host_only():
    engine, state = make_engine(2, started=False)
    p0, p1 = list(state.players)
    with pytest.raises(ValueError):
        engine.set_victory_mode(p1, "turn_limit", 5)
    engine.set_victory_mode(p0, "turn_limit", 5)
    assert state.victory_mode == "turn_limit" and state.turn_limit == 5


def test_auto_roll_for_afk_player():
    engine, state = make_engine(2, ScriptedRng(dice=[1, 2]))
    pid = state.current_player_id
    state.turn_deadline = 0
    engine.tick(5)
    assert state.players[pid].position == 3
    assert "auto_roll" in kinds(engine)
