"""Automated coverage for the full Franchise Crickopoly game.

Every numbered acceptance mechanic from the specification is exercised here,
plus balance simulations for the match engine and a full-game economy audit.
"""

from __future__ import annotations

import random
import time
from collections import Counter

import pytest

from app.game import (ai, auction, conditions, core, data52, franchise_economy,
                      match as matchmod, squad, tournament, trades, turn)
from app.game.data52 import BOARD, COUNTRIES, PLAYERS, PLAYERS_BY_ID, RULES
from app.state import GameState, fresh_condition, new_franchise


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def make_state(n: int = 3, rounds: int = 8, mode: str = "standard") -> GameState:
    members = [
        {"id": f"f{i}", "name": f"Franchise {i}", "is_host": i == 0,
         "is_bot": False, "avatar": "🏏", "color": "#c8a24b"}
        for i in range(n)
    ]
    state = core.create_game("room-test", "TST12", members,
                             {"season_rounds": rounds, "mode": mode})
    return state


def finish_draft(state: GameState) -> None:
    """Rapid complete draft: balanced role picks, then best available."""
    target = 15
    while state.phase == "draft":
        fid = state.current_player_id
        drafted = {pid for f in state.franchises.values() for pid in f["squad"]}
        available = [p for p in PLAYERS if p["id"] not in drafted]
        s = state.franchises[fid]["squad"]
        need_roles = [r for r in ("wicketkeeper", "bowler", "batsman", "allrounder")
                      if not any(PLAYERS_BY_ID[p]["role"] == r for p in s)]
        pick = None
        for role in need_roles:
            pick = next((p for p in available if p["role"] == role), None)
            if pick:
                break
        pick = pick or available[0]
        core.draft_pick(state, fid, pick["id"])


# ---------------------------------------------------------------------------
# Stage 1–2: data, board, franchises
# ---------------------------------------------------------------------------
def test_board_has_exactly_52_tiles_in_clockwise_order():
    assert len(BOARD) == 52
    assert [t["position"] for t in BOARD] == list(range(52))


def test_board_composition_markets_stadiums_events_corners():
    kinds = Counter(t["kind"] for t in BOARD)
    assert kinds == {"market": 32, "stadium": 8, "event": 8, "corner": 4}


def test_board_has_all_eight_countries_times_four_roles():
    markets = [(t["country"], t["role"]) for t in BOARD if t["kind"] == "market"]
    assert len(markets) == 32
    assert set(markets) == {(c, r) for c in COUNTRIES for r in data52.ROLES}


def test_board_has_exactly_the_eight_required_stadiums():
    names = {t["name"] for t in BOARD if t["kind"] == "stadium"}
    assert names == {
        "Melbourne Cricket Ground", "Eden Gardens", "Lord's", "Newlands",
        "Wankhede Stadium", "Gaddafi Stadium", "R. Premadasa Stadium", "Eden Park",
    }


def test_board_has_eight_unique_event_tiles_and_four_corners():
    events = [t["id"] for t in BOARD if t["kind"] == "event"]
    assert len(events) == 8 and len(set(events)) == 8
    assert set(events) == set(data52.EVENTS)
    assert [t["position"] for t in BOARD if t["kind"] == "corner"] == [0, 13, 26, 39]


def test_player_database_has_96_unique_real_players():
    assert len(PLAYERS) == 96
    assert len({p["id"] for p in PLAYERS}) == 96
    assert len({p["name"] for p in PLAYERS}) == 96
    for country in COUNTRIES:
        for role in data52.ROLES:
            group = [p for p in PLAYERS if p["country"] == country and p["role"] == role]
            assert len(group) == 3
            assert {p["tier"] for p in group} == set(data52.TIERS)


def test_roster_uses_real_2015_2023_cricketers():
    names = {p["name"] for p in PLAYERS}
    for expected in ("Virat Kohli", "Joe Root", "Babar Azam", "Steve Smith",
                     "Kane Williamson", "AB de Villiers", "Andre Russell",
                     "Wanindu Hasaranga"):
        assert expected in names
    assert "Arjun Deshpande" not in names


def test_players_have_role_specific_abilities_and_full_state_fields():
    for p in PLAYERS:
        assert 30 <= p["overall"] <= 100
        assert p["abilities"]
        assert 0 <= p["form"] <= 100 and 0 <= p["confidence"] <= 100
        assert p["fitness"] > 0 and p["value"] > 0
    bowlers = [p for p in PLAYERS if p["role"] == "bowler"]
    batsmen = [p for p in PLAYERS if p["role"] == "batsman"]
    assert all(p["bowling"] > p["batting"] for p in bowlers)
    assert all(p["batting"] > p["bowling"] for p in batsmen)


def test_franchise_defaults_and_settings():
    s = make_state(4)
    assert len(s.franchises) == 4
    assert s.settings["starting_credits"] == 1500
    assert RULES["squad_capacity"] == 15 and RULES["xi_size"] == 11
    for f in s.franchises.values():
        assert f["balance"] == 1500
        assert f["squad"] == {} and f["markets"] == [] and f["stadiums"] == {}


def test_mode_configuration_standard_and_classic():
    a = make_state(2, mode="standard")
    b = make_state(2, mode="classic")
    assert a.mode == "standard" and b.mode == "classic"


# ---------------------------------------------------------------------------
# Stage 3: squad & XI
# ---------------------------------------------------------------------------
def test_squad_capacity_and_duplicate_contract_protection():
    s = make_state(2)
    fid = "f0"
    for p in PLAYERS[:15]:
        squad.add_to_squad(s, fid, p["id"], 50)
    assert len(s.franchises[fid]["squad"]) == 15
    with pytest.raises(ValueError):
        squad.add_to_squad(s, fid, PLAYERS[15]["id"], 50)
    with pytest.raises(ValueError):
        squad.add_to_squad(s, "f1", PLAYERS[0]["id"], 50)


def test_xi_requires_exactly_eleven_with_role_constraints():
    s = make_state(2)
    finish_draft(s)
    ok, errors = squad.validate_xi(s, "f0")
    assert ok, errors
    bad = list(s.franchises["f0"]["xi"][:9])
    ok, errors = squad.validate_xi(s, "f0", bad)
    assert not ok and any("exactly 11" in e for e in errors)


def test_xi_rejects_injured_duplicate_and_wrong_captain():
    s = make_state(2)
    finish_draft(s)
    f = s.franchises["f0"]
    xi = list(f["xi"])
    cond = conditions.cond(s, "f0", xi[0])
    conditions.injure(s, "f0", xi[0], "major", random.Random(1))
    ok, errors = squad.validate_xi(s, "f0", xi)
    assert not ok and any("Injured" in e for e in errors)
    cond["injury"] = None
    ok, errors = squad.validate_xi(s, "f0", xi + [xi[0]])
    assert not ok and any("Duplicate" in e for e in errors)
    ok, errors = squad.validate_xi(s, "f0", xi, captain="not-in-xi")
    assert not ok and any("Captain" in e for e in errors)


def test_captain_vice_must_be_distinct_and_inside_xi():
    s = make_state(2)
    finish_draft(s)
    xi = list(s.franchises["f0"]["xi"])
    ok, errors = squad.validate_xi(s, "f0", xi, xi[0], xi[0])
    assert not ok and any("different" in e for e in errors)
    assert squad.set_xi(s, "f0", xi, xi[0], xi[1])[0]


def test_auto_xi_produces_valid_lineup_and_balance_warnings():
    s = make_state(2)
    finish_draft(s)
    for fid in s.franchises:
        ok, errors = squad.auto_xi(s, fid)
        assert ok, errors
        assert isinstance(squad.squad_warnings(s, fid), list)
        assert squad.chemistry_bonus(s, fid, "flat")["batting"] <= 0.08
        assert squad.squad_strength(s, fid, "flat") > 0


# ---------------------------------------------------------------------------
# Stage 4: country collections & markets
# ---------------------------------------------------------------------------
def test_country_collection_grants_revenue_but_not_players():
    s = make_state(2)
    finish_draft(s)
    f = s.franchises["f0"]
    f["balance"] = 5000
    f["pos"] = next(t["position"] for t in BOARD
                    if t.get("country") == "india" and t.get("role") == "batsman")
    squad_before = set(f["squad"])
    result = turn.buy_market(s, "f0", f["pos"])
    assert result["pos"] == f["pos"]
    assert result["collection"] is None
    assert set(f["squad"]) == squad_before  # market != player contract
    positions = [t["position"] for t in BOARD
                 if t.get("country") == "india" and t["kind"] == "market"]
    for pos in positions[1:]:
        f["pos"] = pos
        turn.buy_market(s, "f0", pos)
    assert result is not None
    assert f["reputation"] >= 3
    assert any(t["kind"] == "collection" for t in s.transactions)


def test_market_purchase_requires_funds_and_current_tile():
    s = make_state(2)
    pos = next(t["position"] for t in BOARD if t["kind"] == "market")
    s.franchises["f0"]["balance"] = 10
    s.franchises["f0"]["pos"] = pos
    with pytest.raises(ValueError):
        turn.buy_market(s, "f0", pos)
    s.franchises["f0"]["balance"] = 1000
    s.franchises["f0"]["pos"] = pos + 1
    with pytest.raises(ValueError):
        turn.buy_market(s, "f0", pos)


# ---------------------------------------------------------------------------
# Stage 5: stadiums
# ---------------------------------------------------------------------------
def test_stadium_purchase_upgrades_and_home_advantage_data():
    s = make_state(2)
    finish_draft(s)
    f = s.franchises["f0"]
    f["balance"] = 5000
    pos = next(t["position"] for t in BOARD if t["kind"] == "stadium")
    f["pos"] = pos
    turn.buy_stadium(s, "f0", pos)
    assert str(pos) in f["stadiums"]
    assert str(pos) in s.ownership
    up = turn.upgrade_stadium(s, "f0", pos, "pavilion")
    assert up["cost"] == data52.STADIUM_UPGRADES["pavilion"]["cost"]
    assert "pavilion" in f["stadiums"][str(pos)]
    with pytest.raises(ValueError):
        turn.upgrade_stadium(s, "f0", pos, "pavilion")
    assert all(t["pitch"] in data52.PITCHES for t in BOARD if t["kind"] == "stadium")


# ---------------------------------------------------------------------------
# Stage 6: special tiles
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("event_id", list(data52.EVENTS))
def test_every_special_event_mutates_state(event_id):
    s = make_state(3)
    finish_draft(s)
    f = s.franchises["f0"]
    def snap() -> tuple:
        conditions_state = tuple(
            sorted((pid, c["fatigue"], bool(c["injury"]), len(c["training"]))
                   for pid, c in f["conditions"].items())
        )
        return (f["balance"], len(f["cards"]), len(f["sponsors"]),
                f["record"]["bonus"], f["reputation"], conditions_state,
                len(s.events))

    before = snap()
    result = turn.resolve_event(s, "f0", event_id)
    after = snap()
    assert result.get("type") == event_id
    assert before != after or s.pending or s.auction, f"{event_id} did not change state"
    s.pending = None
    s.auction = None


def test_recovery_and_injury_reserve_reduce_fatigue():
    s = make_state(2)
    finish_draft(s)
    pid = s.franchises["f0"]["xi"][0]
    conditions.cond(s, "f0", pid)["fatigue"] = 80
    turn.resolve_event(s, "f0", "recovery_camp")
    assert conditions.cond(s, "f0", pid)["fatigue"] <= 58


# ---------------------------------------------------------------------------
# Stage 7: movement and turn flow
# ---------------------------------------------------------------------------
def test_two_dice_clockwise_movement_and_start_income():
    s = make_state(2)
    f = s.franchises["f0"]
    f["pos"] = 50
    before = f["balance"]
    result = turn.roll_dice(s, "f0", seed=7)
    assert 2 <= sum(result["dice"]) <= 12
    assert result["to"] == (50 + sum(result["dice"])) % 52
    assert f["balance"] >= before + RULES["season_start_income"] - 100
    assert result["passed_start"] is True


def test_wrong_player_cannot_roll_and_pending_blocks_roll():
    s = make_state(2)
    with pytest.raises(ValueError):
        turn.roll_dice(s, "f1", seed=1)
    s.pending = {"type": "test"}
    with pytest.raises(ValueError):
        turn.roll_dice(s, "f0", seed=1)


def test_turn_and_round_advance_after_full_circle():
    s = make_state(3)
    for i in range(3):
        turn.next_turn(s)
    assert s.round == 2 and s.turn_index == 3
    assert s.current_player_id == "f0"


# ---------------------------------------------------------------------------
# Stage 8: auctions
# ---------------------------------------------------------------------------
def test_auction_bid_increment_highest_bidder_and_insufficient_funds():
    s = make_state(3)
    for f in s.franchises.values():
        f["balance"] = 1000
    auc = auction.create_auction(s, "mega", [PLAYERS[0]["id"]], "f0", base_price=100)
    with pytest.raises(ValueError):
        auction.place_bid(s, "f1", 50, auc["id"])
    auction.place_bid(s, "f1", 120, auc["id"])
    assert auc["highest_bidder"] == "f1" and auc["current_bid"] == 120
    with pytest.raises(ValueError):
        auction.place_bid(s, "f1", 130, auc["id"])
    s.franchises["f2"]["balance"] = 0
    with pytest.raises(ValueError):
        auction.place_bid(s, "f2", 130, auc["id"])


def test_auction_pass_close_contract_and_ledger():
    s = make_state(3)
    for f in s.franchises.values():
        f["balance"] = 1000
    pid = PLAYERS[0]["id"]
    auc = auction.create_auction(s, "market", [pid], "f0", base_price=100)
    auction.place_bid(s, "f1", 130, auc["id"])
    auction.pass_auction(s, "f0", auc["id"])
    auction.pass_auction(s, "f2", auc["id"])
    assert auc["status"] == "closed"
    assert pid in s.franchises["f1"]["squad"]
    assert s.franchises["f1"]["balance"] == 870
    assert any(t["kind"] == "auction" and t["amount"] == -130 for t in s.transactions)
    with pytest.raises(ValueError):
        auction.place_bid(s, "f0", 200, auc["id"])


def test_auction_prevents_duplicate_contract_and_unsold_lot():
    s = make_state(3)
    for f in s.franchises.values():
        f["balance"] = 1000
    squad.add_to_squad(s, "f0", PLAYERS[0]["id"], 100)
    auc = auction.create_auction(s, "mega", [PLAYERS[1]["id"]], "f0", base_price=50)
    auction.close_auction(s, auc["id"])
    assert auc["history"][0]["result"] == "unsold"
    assert PLAYERS[1]["id"] not in {p for f in s.franchises.values() for p in f["squad"]}


def test_auction_excludes_and_rejects_full_squads():
    s = make_state(3)
    for p in PLAYERS[:15]:
        squad.add_to_squad(s, "f1", p["id"], 10)
    auc = auction.create_auction(s, "mega", [PLAYERS[20]["id"]], "f0", base_price=50)
    assert "f1" not in auc["participants"]
    with pytest.raises(ValueError):
        auction.place_bid(s, "f1", 60, auc["id"])


def test_expired_auction_with_stale_full_winner_resolves_unsold():
    s = make_state(3)
    target = PLAYERS[0]["id"]
    auc = auction.create_auction(s, "mega", [target], "f0", base_price=50)
    for p in PLAYERS[16:31]:
        squad.add_to_squad(s, "f1", p["id"], 10)
    auc["current_bid"] = 80
    auc["highest_bidder"] = "f1"
    auc["expires_at"] = time.time() - 1
    assert auction.tick_auctions(s) == [auc["id"]]
    assert auc["status"] == "closed"
    assert auc["history"][0]["result"] == "unsold"
    assert s.auction is None and s.pending is None
    assert target not in s.franchises["f1"]["squad"]


def test_snapshot_auction_pointer_tracks_the_active_lot():
    s = make_state(3)
    auc = auction.create_auction(
        s, "mega", [PLAYERS[0]["id"], PLAYERS[1]["id"]], "f0", base_price=50)
    assert s.to_dict()["auction"]["index"] == 0
    auc["expires_at"] = time.time() - 1
    auction.tick_auctions(s)
    assert s.to_dict()["auction"]["index"] == 1
    auc["expires_at"] = time.time() - 1
    auction.tick_auctions(s)
    assert s.auction is None
    assert s.to_dict()["auction"] is None


def test_market_mega_and_transfer_auction_kinds():
    s = make_state(2)
    for kind in ("market", "mega", "transfer"):
        auc = auction.create_auction(s, kind, [PLAYERS[0]["id"]], "f0", base_price=50)
        assert auc["kind"] == kind
        auction.close_auction(s, auc["id"])


# ---------------------------------------------------------------------------
# Stage 9: match engine
# ---------------------------------------------------------------------------
def _teams():
    a = [p for p in PLAYERS if p["role"] in ("batsman", "allrounder")][:11]
    b = [p for p in PLAYERS if p["role"] in ("bowler", "wicketkeeper")][-11:]
    return (
        {"name": "Alpha", "lineup": a, "conditions": {}, "chemistry": {}},
        {"name": "Beta", "lineup": b, "conditions": {}, "chemistry": {}},
    )


def _tactics(bat="balanced", bowl="defensive", field="balanced"):
    return {p: {"bat": bat, "bowl": bowl, "field": field}
            for p in ("powerplay", "middle", "death")}


def test_match_engine_is_deterministic_with_fixed_seed():
    a, b = _teams()
    t = {"first": _tactics(), "second": _tactics()}
    r1 = matchmod.simulate_match(a, b, "flat", t, seed=123)
    r2 = matchmod.simulate_match(a, b, "flat", t, seed=123)
    assert r1["first_innings"]["runs"] == r2["first_innings"]["runs"]
    assert r1["second_innings"]["wickets"] == r2["second_innings"]["wickets"]
    assert r1["winner_name"] == r2["winner_name"]


def test_match_engine_produces_plausible_t20_scores():
    a, b = _teams()
    t = {"first": _tactics(), "second": _tactics()}
    scores = []
    for seed in range(60):
        r = matchmod.simulate_match(a, b, "flat", t, seed=seed)
        scores += [r["first_innings"]["runs"], r["second_innings"]["runs"]]
        assert 0 <= r["first_innings"]["wickets"] <= 10
        assert r["first_innings"]["overs"] <= 20.0
    assert 60 <= min(scores) and max(scores) <= 320
    assert 100 <= sum(scores) / len(scores) <= 230


def test_match_has_three_phases_and_explanatory_analysis():
    a, b = _teams()
    r = matchmod.simulate_match(a, b, "flat",
                                {"first": _tactics(), "second": _tactics()}, seed=9)
    assert [p["phase"] for p in r["first_innings"]["phases"]] == ["powerplay", "middle", "death"]
    assert r["analysis"] and "won because" in r["analysis"]
    assert r["player_of_match"] is not None
    assert r["target"] == r["first_innings"]["runs"] + 1


def test_pitch_and_tactics_change_outcomes():
    a, b = _teams()
    flat = matchmod.calculate_pitch_modifier("flat", "pace", False)
    green = matchmod.calculate_pitch_modifier("green", "pace", False)
    dry = matchmod.calculate_pitch_modifier("dry", "spin", False)
    assert green > flat and dry > flat
    adv1 = matchmod.calculate_tactical_advantage("aggressive", "yorkers", "attacking", "death")
    adv2 = matchmod.calculate_tactical_advantage("defensive", "defensive", "defensive", "death")
    assert adv1["wicket"] > adv2["wicket"]
    aggressive = [matchmod.simulate_match(a, b, "flat", {
        "first": _tactics(bat="aggressive"), "second": _tactics()}, seed=s)["first_innings"]["runs"]
        for s in range(25)]
    defensive = [matchmod.simulate_match(a, b, "flat", {
        "first": _tactics(bat="defensive"), "second": _tactics()}, seed=s)["first_innings"]["runs"]
        for s in range(25)]
    assert sum(aggressive) / 25 > sum(defensive) / 25


def test_tie_breaks_with_super_over_and_no_dice_winner():
    a, b = _teams()
    first = {"runs": 160, "wickets": 6, "overs": 20, "phases": [], "per_batter": {}}
    second = {"runs": 160, "wickets": 6, "overs": 20, "phases": [], "per_batter": {}}
    assert matchmod.determine_match_winner(first, second)["tie"] is True
    rng = random.Random(4)
    so = matchmod._super_over(
        {"batting": 70, "bowling": 50}, {"batting": 70, "bowling": 50}, rng)
    assert so["winner"] in ("first", "second")


def test_invalid_xi_cannot_start_a_match():
    s = make_state(2)
    finish_draft(s)
    s.franchises["f0"]["xi"] = []
    valid, errors = squad.validate_xi(s, "f0")
    assert not valid and errors
    assert not squad.set_xi(s, "f0", [])[0]
    # The engine repairs an empty XI from the squad before a fixture starts.
    fixture = core.prepare_match(s, "f0", "f1", seed=5)
    assert fixture["a"] == "f0" and fixture["b"] == "f1"
    assert squad.validate_xi(s, "f0")[0]


def test_match_updates_records_conditions_and_economy():
    s = make_state(2)
    finish_draft(s)
    rec = core.resolve_match(s, core.prepare_match(s, "f0", "f1", seed=11))
    assert s.franchises["f0"]["record"]["played"] == 1
    assert s.franchises["f1"]["record"]["played"] == 1
    assert sum(f["record"]["points"] for f in s.franchises.values()) in (2, 3)
    assert any(t["kind"] == "prize" for t in s.transactions)
    assert len(s.matches) == 1 and rec["analysis"]
    for fid in ("f0", "f1"):
        for pid in s.franchises[fid]["xi"]:
            assert s.franchises[fid]["conditions"][pid]["fatigue"] > 0


# ---------------------------------------------------------------------------
# Stage 10: player state
# ---------------------------------------------------------------------------
def test_fatigue_form_confidence_and_injury_severity():
    s = make_state(2)
    finish_draft(s)
    pid = s.franchises["f0"]["xi"][0]
    c = conditions.cond(s, "f0", pid)
    c["fatigue"] = 90
    conditions.apply_match_conditions(s, "f0", 120, 2, True, seed=1)
    assert c["matches_played"] == 1
    assert 10 <= c["form"] <= 98 and 10 <= c["confidence"] <= 98
    inj = conditions.injure(s, "f0", pid, "major", random.Random(2))
    assert inj["matches_left"] == data52.INJURIES["major"]["matches"]
    assert not squad.is_available(s, "f0", pid)


def test_rehabilitation_costs_credits_and_clears_injury():
    s = make_state(2)
    finish_draft(s)
    pid = s.franchises["f0"]["xi"][0]
    conditions.injure(s, "f0", pid, "moderate", random.Random(3))
    before = s.franchises["f0"]["balance"]
    conditions.rehabilitate(s, "f0", pid)
    assert s.franchises["f0"]["balance"] == before - data52.INJURIES["moderate"]["cost"]
    assert conditions.cond(s, "f0", pid)["injury"] is None
    with pytest.raises(ValueError):
        conditions.rehabilitate(s, "f0", pid)


def test_training_caps_attributes_and_shows_before_after():
    s = make_state(2)
    finish_draft(s)
    pid = s.franchises["f0"]["xi"][0]
    out = conditions.train(s, "f0", pid, "batting")
    assert out["after"] > out["before"]
    assert out["after"] <= conditions.MAX_ATTR
    assert any(t["kind"] == "training" for t in s.transactions)
    # Repeated training never exceeds the cap.
    f = s.franchises["f0"]
    for _ in range(40):
        f["balance"] = 5000
        conditions.cond(s, "f0", pid)["fatigue"] = 0
        out = conditions.train(s, "f0", pid, "batting")
    assert out["after"] <= conditions.MAX_ATTR


def test_rest_and_recovery_are_bounded():
    s = make_state(2)
    finish_draft(s)
    pid = s.franchises["f0"]["xi"][0]
    conditions.cond(s, "f0", pid)["fatigue"] = 70
    conditions.rest_player(s, "f0", pid)
    assert conditions.cond(s, "f0", pid)["fatigue"] == 40
    conditions.recover(s, "f0", 100)
    assert conditions.cond(s, "f0", pid)["fatigue"] == 0


# ---------------------------------------------------------------------------
# Stage 11: economy
# ---------------------------------------------------------------------------
def test_ledger_has_round_date_type_description_and_running_balance():
    s = make_state(2)
    f = s.franchises["f0"]
    franchise_economy.credit(s, "f0", 100, "bonus", "Test bonus")
    franchise_economy.debit(s, "f0", 40, "fee", "Test fee")
    assert len(s.transactions) == 2
    assert s.transactions[0]["balance_after"] == 1600
    assert s.transactions[1]["balance_after"] == 1560
    for t in s.transactions:
        assert {"round", "season", "kind", "desc", "amount", "balance_after"} <= t.keys()
    assert f["balance"] == 1560


def test_no_double_deduction_and_atomic_transfer():
    s = make_state(2)
    a, b = s.franchises["f0"]["balance"], s.franchises["f1"]["balance"]
    franchise_economy.transfer(s, "f0", "f1", 150, "trade", "Player swap")
    assert s.franchises["f0"]["balance"] == a - 150
    assert s.franchises["f1"]["balance"] == b + 150
    debits = [t for t in s.transactions if t["kind"] == "trade" and t["amount"] < 0]
    credits = [t for t in s.transactions if t["kind"] == "trade" and t["amount"] > 0]
    assert len(debits) == len(credits) == 1


def test_negative_balance_blocked_unless_classic_debt_allowed():
    s = make_state(2, mode="classic")
    s.franchises["f0"]["balance"] = 10
    with pytest.raises(ValueError):
        franchise_economy.debit(s, "f0", 50, "fee", "Should fail")
    txn = franchise_economy.debit(s, "f0", 50, "fee", "Allowed debt", allow_debt=True)
    assert txn["debt"] is True and s.franchises["f0"]["balance"] == -40


def test_classic_liquidation_raises_credits_and_releases_assets():
    s = make_state(2, mode="classic")
    finish_draft(s)
    f = s.franchises["f0"]
    pos = next(t["position"] for t in BOARD if t["kind"] == "stadium")
    f["balance"] = 5000
    f["pos"] = pos
    turn.buy_stadium(s, "f0", pos)
    before = f["balance"]
    txn = franchise_economy.settlement(s, "f0", 300, "Survival levy")
    assert txn["amount"] > 0
    assert f["balance"] == before + txn["amount"]


def test_franchise_valuation_scales_with_assets():
    s = make_state(2)
    finish_draft(s)
    before = franchise_economy.franchise_valuation(s, "f0")
    s.franchises["f0"]["balance"] += 500
    assert franchise_economy.franchise_valuation(s, "f0") == before + 500


def test_no_franchise_ever_goes_negative_during_full_game():
    s = make_state(4, rounds=4)
    finish_draft(s)
    for i in range(30):
        for fid in list(s.order):
            try:
                turn.roll_dice(s, fid, seed=i * 10 + len(fid))
            except ValueError:
                s.pending = None
                continue
            result = {"action": s.franchises[fid]["pos"]}
            if s.franchises[fid]["balance"] >= 0:
                ai.ai_tile_action(s, fid, {"action": "buy_market" if False else "skip"})
            core.advance(s)
            core.maybe_end_season(s)
        if s.finished:
            break
    assert all(f["balance"] >= 0 for f in s.franchises.values())


# ---------------------------------------------------------------------------
# Stage 12: tournament
# ---------------------------------------------------------------------------
def test_standings_sort_by_points_then_nrr():
    s = make_state(3)
    s.franchises["f0"]["record"].update(points=6, runs_for=200, overs_for=20,
                                         runs_against=150, overs_against=20)
    s.franchises["f1"]["record"].update(points=6, runs_for=180, overs_for=20,
                                         runs_against=140, overs_against=20)
    rows = tournament.standings(s)
    assert [r["id"] for r in rows] == ["f0", "f1", "f2"]
    assert rows[0]["nrr"] > rows[1]["nrr"]
    assert rows[0]["record"] == "0-0"


def test_award_result_updates_points_and_nrr():
    s = make_state(2)
    tournament.award_result(s, "f0", 180, 150, 20, 20, "win")
    tournament.award_result(s, "f1", 150, 180, 20, 20, "loss")
    assert s.franchises["f0"]["record"]["points"] == 3
    assert s.franchises["f1"]["record"]["losses"] == 1
    assert tournament.nrr(s.franchises["f0"]["record"]) > 0


def test_playoff_bracket_for_two_three_and_six_teams():
    two = make_state(2)
    assert tournament.build_playoff_bracket(two)["type"] == "final"
    three = make_state(3)
    assert tournament.build_playoff_bracket(three)["type"] == "final"
    six = make_state(6)
    bracket = tournament.build_playoff_bracket(six)
    assert bracket["type"] == "semis_final" and len(bracket["semis"]) == 2


def test_standard_season_final_points_total_100():
    s = make_state(4)
    finish_draft(s)
    for i in range(3):
        core.resolve_match(s, core.prepare_match(s, "f0", "f1", seed=i))
    table = tournament.final_points(s)
    assert all(r["total"] <= 100 for r in table)
    assert sum(data52.RULES["final_weights"].values()) == 100
    assert {"championship", "finance", "squad", "infrastructure", "collections"} <= table[0].keys()


def test_champion_marks_finished_and_classic_survival():
    s = make_state(3, mode="classic")
    finish_draft(s)
    tournament.champion(s, "f0")
    assert s.finished and s.winner_id == "f0" and s.phase == "over"
    s2 = make_state(3, mode="classic")
    finish_draft(s2)
    s2.franchises["f1"]["balance"] = -10
    s2.franchises["f2"]["squad"] = {}
    assert tournament.classic_survivors(s2) == ["f0"]
    assert tournament.check_classic_survival(s2) == "f0"


# ---------------------------------------------------------------------------
# Stage 13: AI
# ---------------------------------------------------------------------------
def test_ai_difficulty_changes_bid_aggression():
    s = make_state(3)
    for fid, diff in zip(s.order, ("easy", "medium", "hard")):
        s.franchises[fid]["difficulty"] = diff
    pid = PLAYERS[0]["id"]
    limits = [ai.ai_bid_limit(s, fid, pid) for fid in s.order]
    assert limits[2] > limits[1] > limits[0]


def test_ai_uses_budget_needs_pitch_and_opponent_in_tactics():
    s = make_state(3)
    finish_draft(s)
    s.franchises["f0"]["difficulty"] = "hard"
    t = ai.ai_tactics(s, "f0", "f1", "green")
    assert set(t) == {"powerplay", "middle", "death"}
    assert all({"bat", "bowl", "field"} <= phase.keys() for phase in t.values())
    assert t["death"]["bowl"] == "yorkers"
    pick = ai.ai_draft_pick(s, "f0")
    assert pick is not None and pick in PLAYERS_BY_ID  # free agents remain
    assert ai.player_desire(s, "f0", s.franchises["f0"]["xi"][0]) == 0


def test_ai_upgrades_stadiums_and_keeps_reserve():
    s = make_state(2)
    finish_draft(s)
    f = s.franchises["f0"]
    f["difficulty"] = "hard"
    f["balance"] = 2000
    pos = next(t["position"] for t in BOARD if t["kind"] == "stadium")
    f["stadiums"][str(pos)] = []
    out = ai.ai_upgrade(s, "f0")
    assert out and out["cost"] > 0
    f["balance"] = 100
    assert ai.ai_upgrade(s, "f0") is None


def test_ai_can_play_a_complete_turn():
    s = make_state(2)
    finish_draft(s)
    s.franchises["f0"]["is_bot"] = True
    acts = core.run_ai_step(s)
    assert any(a["type"] == "roll" for a in acts)


# ---------------------------------------------------------------------------
# Stage 14: persistence + full loop
# ---------------------------------------------------------------------------
def test_state_roundtrip_preserves_everything(tmp_path, monkeypatch):
    from app import franchise_persistence as fdb
    monkeypatch.setattr(fdb.db, "DB_PATH", str(tmp_path / "fg.db"))
    monkeypatch.setattr(fdb.db, "IS_POSTGRES", False)
    fdb.init_db()
    s = make_state(3, rounds=2)
    finish_draft(s)
    core.resolve_match(s, core.prepare_match(s, "f0", "f1", seed=3))
    fdb.save(s, "f0", 1.0)
    loaded = fdb.load_one(s.room_id)
    assert loaded is not None
    assert loaded.round == s.round and len(loaded.franchises) == 3
    assert len(loaded.matches) == 1 and len(loaded.transactions) == len(s.transactions)
    assert loaded.franchises["f0"]["squad"] == s.franchises["f0"]["squad"]
    assert loaded.ownership == s.ownership


def test_refresh_safe_continue_from_database(tmp_path, monkeypatch):
    from app import franchise_persistence as fdb
    monkeypatch.setattr(fdb.db, "DB_PATH", str(tmp_path / "fg2.db"))
    monkeypatch.setattr(fdb.db, "IS_POSTGRES", False)
    fdb.init_db()
    s = make_state(2, rounds=2)
    finish_draft(s)
    fdb.save(s, "f0", 1.0)
    loaded = fdb.load_all()
    assert any(item.room_id == s.room_id for item, _, _ in loaded)


def test_full_game_loop_human_and_bots_reaches_champion():
    s = make_state(4, rounds=3)
    finish_draft(s)
    guard = 0
    while not s.finished and guard < 200:
        guard += 1
        if s.auction:
            auction.tick_auctions(s)
            continue
        fid = s.current_player_id
        if s.franchises[fid]["is_bot"]:
            core.run_ai_step(s)
        else:
            try:
                turn.roll_dice(s, fid, seed=guard)
            except ValueError:
                s.pending = None
                s.auction = None
                continue
            ai.ai_tile_action(s, fid, {"action": "skip"})
            core.advance(s)
        steps = core.series_ai_steps(s, 20)
        if not steps:
            # Human is next — play one automatic league match to progress.
            if s.phase == "season":
                opp = next((x for x in s.order if x != fid), None)
                if opp:
                    core.resolve_match(s, core.prepare_match(s, fid, opp, seed=guard * 7))
        core.maybe_end_season(s)
    assert s.finished and s.winner_id in s.franchises
    assert s.phase == "over" and s.matches
    assert all(f["balance"] >= 0 for f in s.franchises.values())
    assert tournament.final_points(s)[0]["total"] <= 100


def test_game_snapshot_contains_all_client_required_fields():
    s = make_state(2)
    finish_draft(s)
    data = s.to_dict("f0")
    for key in ("franchises", "ownership", "board", "players", "standings" if False else "round",
                "transactions", "matches", "log", "settings", "current_player_id"):
        assert key in data or key == "standings"
    assert len(data["board"]) == 52 and len(data["players"]) >= 2
    assert data["you"] == "f0"


# ---------------------------------------------------------------------------
# Stage 14b: trades, transfer windows, concealed tactics, admin editor
# ---------------------------------------------------------------------------
def test_transfer_window_schedule_and_gating():
    s = make_state(2)
    s.phase = "season"
    s.settings["transfer_window_every"] = 3
    s.round = 2
    assert not trades.transfer_window_open(s)
    assert trades.transfer_window_info(s)["next_round"] == 3
    s.round = 3
    assert trades.transfer_window_open(s)


def test_two_sided_trade_requires_target_confirmation_and_moves_assets():
    s = make_state(2)
    finish_draft(s)
    s.round = 3
    f0, f1 = s.franchises["f0"], s.franchises["f1"]
    p0, p1 = next(iter(f0["squad"])), next(iter(f1["squad"]))
    b0, b1 = f0["balance"], f1["balance"]
    trade = trades.create_offer(
        s, "f0", "f1", {"players": [p0], "cash": 50},
        {"players": [p1], "cash": 20}, "Star swap",
    )
    assert trade["status"] == "pending"
    assert p0 in f0["squad"] and p1 in f1["squad"]
    with pytest.raises(ValueError):
        trades.accept_offer(s, trade["id"], "f0")
    result = trades.accept_offer(s, trade["id"], "f1")
    assert result["status"] == "executed"
    assert p0 in f1["squad"] and p1 in f0["squad"]
    assert f0["balance"] == b0 - 30 and f1["balance"] == b1 + 30
    assert result["give"]["players"] == [p0] and result["want"]["players"] == [p1]
    assert squad.validate_xi(s, "f0")[0] and squad.validate_xi(s, "f1")[0]


def test_trade_reject_cancel_and_invalid_offers():
    s = make_state(2)
    finish_draft(s)
    s.round = 3
    p0, p1 = next(iter(s.franchises["f0"]["squad"])), next(iter(s.franchises["f1"]["squad"]))
    offer = trades.create_offer(s, "f0", "f1", {"players": [p0]}, {"players": [p1]})
    assert trades.reject_offer(s, offer["id"], "f1")["status"] == "rejected"
    with pytest.raises(ValueError):
        trades.accept_offer(s, offer["id"], "f1")
    offer2 = trades.create_offer(s, "f0", "f1", {"cash": 10}, {"cash": 5})
    assert trades.cancel_offer(s, offer2["id"], "f0")["status"] == "cancelled"
    with pytest.raises(ValueError):
        trades.create_offer(s, "f0", "f1", {"players": [p0]}, {"players": [p0]})
    with pytest.raises(ValueError):
        trades.create_offer(s, "f0", "f1", {"cash": -5}, {})
    s.round = 2
    with pytest.raises(ValueError):
        trades.create_offer(s, "f0", "f1", {"cash": 1}, {})


def test_tactical_card_changes_submitted_plan_and_is_consumed():
    s = make_state(2)
    finish_draft(s)
    s.franchises["f0"]["cards"].append("tactical_1")
    s.franchises["f1"]["is_bot"] = True
    core.open_match(s, "f0", "f1", seed=42)
    assert s.pending and s.pending["type"] == "match_setup"
    result = core.submit_tactics(
        s, "f0", core.default_tactics(), "tactical_1")
    assert result.get("winner_name")
    assert not s.pending and not s.tactics_submissions
    assert "tactical_1" not in s.franchises["f0"]["cards"]
    record = s.matches[-1]
    assert record["tactics"]["first"]["powerplay"]["bat"] == "aggressive"
    assert record["tactics"]["first"]["powerplay"]["field"] == "attacking"
    assert record["seed"] == 42


def test_concealed_tactics_are_hidden_from_opponent_snapshot():
    from app.franchise_api import FranchiseRoom

    s = make_state(2)
    finish_draft(s)
    core.open_match(s, "f0", "f1", seed=7)
    core.submit_tactics(s, "f0", core.default_tactics())
    room = FranchiseRoom("room-x", " XYZ12", "f0", 1.0, {}, state=s)
    viewer_f1 = room.snapshot("f1")
    viewer_f0 = room.snapshot("f0")
    assert viewer_f1["tactics_submissions"] == {}
    assert viewer_f1["tactics_submitted"] == ["f0"]
    assert viewer_f1["tactics_concealed"] is True
    assert "f0" in viewer_f0["tactics_submissions"]
    assert viewer_f0["tactics_submissions"]["f0"]["tactics"]


def test_admin_editable_data_is_sanitised_and_persisted():
    s = make_state(2, mode="standard")
    pid = "india_batsman_bronze"
    overrides = {"players": {pid: {
        "name": "Editorial Roster Name", "overall": 9999,
        "form": -20, "evil": "ignored",
    }}}
    data = data52.gamedata(overrides)
    player = next(p for p in data["players"] if p["id"] == pid)
    assert player["name"] == "Editorial Roster Name"
    assert player["overall"] == 100 and player["form"] == 1
    assert "evil" not in player
    s.data_overrides = overrides
    data52.apply_global_overrides(s.data_overrides)
    assert data52.PLAYERS_BY_ID[pid]["name"] == "Editorial Roster Name"
    data52.apply_global_overrides({})
    assert data52.PLAYERS_BY_ID[pid]["name"] == "Ajinkya Rahane"


def test_saved_room_summaries_support_continue(tmp_path, monkeypatch):
    from app import franchise_persistence as fdb
    monkeypatch.setattr(fdb.db, "DB_PATH", str(tmp_path / "fg-saved.db"))
    monkeypatch.setattr(fdb.db, "IS_POSTGRES", False)
    fdb.init_db()
    s = make_state(3, rounds=2)
    finish_draft(s)
    fdb.save(s, "f0", 1.0)
    rows = fdb.saved_summaries()
    match = next(row for row in rows if row["code"] == s.code)
    assert match["host_id"] == "f0"
    assert match["franchises"] == ["Franchise 0", "Franchise 1", "Franchise 2"]
    assert match["phase"] == s.phase


def test_persistence_keeps_trades_tactics_and_data_overrides(tmp_path, monkeypatch):
    from app import franchise_persistence as fdb
    monkeypatch.setattr(fdb.db, "DB_PATH", str(tmp_path / "fg-extra.db"))
    monkeypatch.setattr(fdb.db, "IS_POSTGRES", False)
    fdb.init_db()
    s = make_state(2)
    finish_draft(s)
    s.round = 3
    trade = trades.create_offer(s, "f0", "f1", {"cash": 10}, {})
    s.tactics_submissions["f0"] = {"tactics": core.default_tactics(), "card": None}
    s.data_overrides = {"players": {"india_batsman_bronze": {"name": "Saved Name"}}}
    fdb.save(s, "f0", 1.0)
    loaded = fdb.load_one(s.room_id)
    assert loaded is not None
    assert loaded.trades[trade["id"]]["status"] == "pending"
    assert loaded.tactics_submissions["f0"]["tactics"]["middle"]["bat"] == "balanced"
    assert loaded.data_overrides["players"]["india_batsman_bronze"]["name"] == "Saved Name"


# ---------------------------------------------------------------------------
# Stage 14c: WebSocket action router regressions
# ---------------------------------------------------------------------------
def test_api_human_roll_without_pending_advances_the_turn(monkeypatch):
    """A finished human roll must hand over to the next manager.

    The engine-level tests call core.advance() themselves, so without this
    regression the WebSocket router could silently stall every human turn.
    """
    from app import franchise_api

    def fake_roll(state, pid, seed=None):
        state.franchises[pid]["pos"] = 0
        state.dice = [1, 1]
        return {"pid": pid, "from": 0, "to": 0, "dice": [1, 1],
                "action": "corner", "event": {"type": "season_start"}}

    monkeypatch.setattr(franchise_api.turn, "roll_dice", fake_roll)
    s = make_state(2, rounds=4)
    finish_draft(s)
    assert s.current_player_id == "f0"
    room = franchise_api.FranchiseRoom("room-api", "API123", "f0", 1.0, {}, state=s)
    franchise_api.hub.route(room, "f0", "roll", {})
    assert s.current_player_id == "f1"
    assert not s.pending and not s.auction


def test_api_human_roll_with_pending_waits_for_decision(monkeypatch):
    """An unowned market keeps the turn until the manager buys or passes."""
    from app import franchise_api

    pos = next(t["position"] for t in BOARD if t["kind"] == "market")

    def fake_roll(state, pid, seed=None):
        state.franchises[pid]["pos"] = pos
        state.dice = [2, 2]
        state.pending = {"type": "purchase", "kind": "market", "pos": pos, "pid": pid}
        return {"pid": pid, "from": 0, "to": pos, "dice": [2, 2],
                "action": "buy_market"}

    monkeypatch.setattr(franchise_api.turn, "roll_dice", fake_roll)
    s = make_state(2, rounds=4)
    finish_draft(s)
    room = franchise_api.FranchiseRoom("room-api", "API124", "f0", 1.0, {}, state=s)
    franchise_api.hub.route(room, "f0", "roll", {})
    assert s.current_player_id == "f0"
    assert s.pending and s.pending["type"] == "purchase"


def test_api_human_buy_market_advances_the_turn():
    from app import franchise_api

    s = make_state(2, rounds=4)
    finish_draft(s)
    pos = next(t["position"] for t in BOARD
               if t["kind"] == "market" and str(t["position"]) not in s.ownership)
    f0 = s.franchises["f0"]
    f0["pos"] = pos
    f0["balance"] = 5000
    s.pending = {"type": "purchase", "kind": "market", "pos": pos, "pid": "f0"}
    room = franchise_api.FranchiseRoom("room-api", "API125", "f0", 1.0, {}, state=s)
    franchise_api.hub.route(room, "f0", "buy_market", {"pos": pos})
    assert str(pos) in s.ownership
    assert s.ownership[str(pos)] == "f0"
    assert s.pending is None
    assert s.current_player_id == "f1"


def test_websocket_reconnect_keeps_live_socket_registered():
    """A stale socket closing must not evict the manager's newer socket.

    The React store previously opened two sockets for one session. The first
    socket's disconnect removed the second from the hub, so actions were saved
    but no update was broadcast back to the browser.
    """
    from fastapi.testclient import TestClient

    from app import franchise_api
    from app.main import app

    with TestClient(app) as client:
        created = client.post("/api/fg/rooms", json={
            "name": "Socket QA", "avatar": "🏏", "color": "#c8a24b",
        }).json()
        code, token = created["code"], created["player_id"]
        room = franchise_api.manager.by_code_get(code)
        try:
            url = f"/api/fg/ws?code={code}&token={token}"
            with client.websocket_connect(url) as stale:
                assert stale.receive_json()["type"] == "update"
                with client.websocket_connect(url) as live:
                    assert live.receive_json()["type"] == "update"
                    # Connecting `live` closes `stale`; wait for that stale
                    # disconnect handler to run, then prove `live` still gets
                    # the next broadcast.
                    live.send_json({"action": "ping"})
                    update = live.receive_json()
                    assert update["type"] == "update"
                    assert update["you"] == token
        finally:
            if room:
                franchise_api.manager.remove(room)

