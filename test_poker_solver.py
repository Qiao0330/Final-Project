from card import parse_card, parse_hole_cards
from betting_state import derive_preflop_state
from common import Action, PlayerAction, Position
from poker_eval import HandCategory, compare_hand_values, evaluate_7cards
from range_model import (
    all_preflop_hand_classes,
    estimate_open_fold_probability,
    get_hand_class,
    get_preflop_frequency,
    is_hand_in_open_range,
    players_behind_count,
)
from solver import SolverInput, solve_preflop_decision
from strategy_profile import normalize_strategy_profile
from adapter_utils import mixed_frequencies_from_named_evs, parse_board_text
from equity import EquityInput, estimate_preflop_equity
from range_equity import OpponentRange, RangeCandidate, estimate_equity_against_ranges
from study_adapter import get_study_view_data
from trainer_adapter import get_trainer_question, grade_trainer_answer
from trainer import generate_random_scenario


def _must_parse(text):
    card = parse_card(text)
    assert card is not None, f"could not parse {text}"
    return card


def test_card_parsing():
    assert parse_card("Ah") is not None
    assert parse_card("Th") is not None
    assert parse_card("10h") is None
    assert parse_card("Kx") is None
    assert parse_hole_cards("Ah", "Ah") is None


def test_board_parsing_and_equity():
    hand = parse_hole_cards("Ah", "As")
    assert hand is not None
    board = parse_board_text("Kd Qs Jh", hand)
    assert len(board) == 3

    equity = estimate_preflop_equity(
        EquityInput(
            hero_hand=hand,
            opponent_count=1,
            simulations=10,
            board_cards=board,
        )
    )
    assert equity.simulations == 10
    assert 0.0 <= equity.equity <= 1.0

    try:
        parse_board_text("AhKdQs", hand)
    except ValueError as exc:
        assert "overlap" in str(exc)
    else:
        assert False, "expected overlapping board card to fail"


def test_multiway_tie_equity_uses_split_pot_share():
    hand = parse_hole_cards("2c", "3d")
    opponent_one = parse_hole_cards("4c", "5d")
    opponent_two = parse_hole_cards("6c", "7d")
    assert hand is not None and opponent_one is not None and opponent_two is not None
    board = tuple(_must_parse(card) for card in ("Ah", "Kh", "Qh", "Jh", "Th"))

    random_result = estimate_preflop_equity(
        EquityInput(hand, opponent_count=2, simulations=10, board_cards=board)
    )
    assert abs(random_result.equity - (1.0 / 3.0)) < 1e-9

    ranges = (
        OpponentRange(Position.UTG, (RangeCandidate(opponent_one, 1.0, 1.0),), 1.0, "test", "test", 1.0),
        OpponentRange(Position.HJ, (RangeCandidate(opponent_two, 1.0, 1.0),), 1.0, "test", "test", 1.0),
    )
    range_equity = estimate_equity_against_ranges(hand, ranges, 10, board)
    assert abs(range_equity - (1.0 / 3.0)) < 1e-9


def test_hand_evaluator():
    straight_flush = [
        _must_parse("Ah"), _must_parse("Kh"), _must_parse("Qh"),
        _must_parse("Jh"), _must_parse("Th"), _must_parse("2c"), _must_parse("3d"),
    ]
    four_kind = [
        _must_parse("As"), _must_parse("Ad"), _must_parse("Ac"),
        _must_parse("Ah"), _must_parse("Ks"), _must_parse("2c"), _must_parse("3d"),
    ]
    full_house = [
        _must_parse("Ks"), _must_parse("Kd"), _must_parse("Kc"),
        _must_parse("2h"), _must_parse("2s"), _must_parse("9c"), _must_parse("4d"),
    ]
    flush = [
        _must_parse("Ah"), _must_parse("Kh"), _must_parse("9h"),
        _must_parse("7h"), _must_parse("3h"), _must_parse("2c"), _must_parse("4d"),
    ]
    two_pair = [
        _must_parse("As"), _must_parse("Ad"), _must_parse("Kc"),
        _must_parse("Kh"), _must_parse("9s"), _must_parse("3c"), _must_parse("2d"),
    ]
    one_pair = [
        _must_parse("Qs"), _must_parse("Qd"), _must_parse("Jc"),
        _must_parse("9h"), _must_parse("7s"), _must_parse("4c"), _must_parse("2d"),
    ]
    ace_kicker = [
        _must_parse("As"), _must_parse("Kd"), _must_parse("Qc"),
        _must_parse("9h"), _must_parse("7s"), _must_parse("4c"), _must_parse("2d"),
    ]
    king_kicker = [
        _must_parse("Ks"), _must_parse("Qd"), _must_parse("Jc"),
        _must_parse("9h"), _must_parse("7s"), _must_parse("4c"), _must_parse("2d"),
    ]

    assert compare_hand_values(evaluate_7cards(straight_flush), evaluate_7cards(four_kind)) > 0
    assert compare_hand_values(evaluate_7cards(full_house), evaluate_7cards(flush)) > 0
    assert compare_hand_values(evaluate_7cards(two_pair), evaluate_7cards(one_pair)) > 0
    assert compare_hand_values(evaluate_7cards(ace_kicker), evaluate_7cards(king_kicker)) > 0


def test_hand_evaluator_edge_cases():
    wheel_straight = [
        _must_parse("Ah"), _must_parse("5d"), _must_parse("4c"),
        _must_parse("3s"), _must_parse("2h"), _must_parse("Kd"), _must_parse("9c"),
    ]
    two_trips_full_house = [
        _must_parse("Ah"), _must_parse("Ad"), _must_parse("Ac"),
        _must_parse("Kh"), _must_parse("Kd"), _must_parse("Kc"), _must_parse("2s"),
    ]
    three_pairs = [
        _must_parse("Ah"), _must_parse("Ad"), _must_parse("Kh"),
        _must_parse("Kd"), _must_parse("Qh"), _must_parse("Qd"), _must_parse("2s"),
    ]
    seven_card_flush = [
        _must_parse("Ah"), _must_parse("Kh"), _must_parse("Qh"),
        _must_parse("9h"), _must_parse("6h"), _must_parse("3h"), _must_parse("2h"),
    ]

    wheel_value = evaluate_7cards(wheel_straight)
    assert wheel_value.category == HandCategory.STRAIGHT
    assert wheel_value.tie_breakers == (5,)

    full_house_value = evaluate_7cards(two_trips_full_house)
    assert full_house_value.category == HandCategory.FULL_HOUSE
    assert full_house_value.tie_breakers == (14, 13)

    two_pair_value = evaluate_7cards(three_pairs)
    assert two_pair_value.category == HandCategory.TWO_PAIR
    assert two_pair_value.tie_breakers == (14, 13, 12)

    flush_value = evaluate_7cards(seven_card_flush)
    assert flush_value.category == HandCategory.FLUSH
    assert flush_value.tie_breakers == (14, 13, 12, 9, 6)


def test_range_model():
    hand = parse_hole_cards("Ah", "Kh")
    assert hand is not None
    hand_class = get_hand_class(hand)
    assert hand_class.name == "AKs"
    assert is_hand_in_open_range(Position.UTG, hand_class)

    hand = parse_hole_cards("As", "Kd")
    assert hand is not None
    assert get_hand_class(hand).name == "AKo"

    hand = parse_hole_cards("7c", "7d")
    assert hand is not None
    assert get_hand_class(hand).name == "77"

    hand = parse_hole_cards("7c", "2d")
    assert hand is not None
    assert not is_hand_in_open_range(Position.UTG, get_hand_class(hand))

    assert players_behind_count(Position.BTN) == 2
    assert players_behind_count(Position.UTG) == 5

    hand = parse_hole_cards("Ah", "As")
    assert hand is not None
    fold_probability = estimate_open_fold_probability(Position.BTN, hand, 1.5, 2.5)
    assert 0.0 <= fold_probability <= 1.0


def test_button_rfi_matches_reference_shape():
    expected_raise = {
        "AA", "AKs", "AQs", "AJs", "ATs", "A9s", "A2s",
        "KQo", "Q3s", "J5s", "T6s", "76s", "65s", "54s", "22",
    }
    expected_fold = {"K7o", "Q8o", "A2o", "T5s", "64s", "32s"}

    classes = {hand_class.name: hand_class for hand_class in all_preflop_hand_classes()}
    for hand_name in expected_raise:
        frequency = get_preflop_frequency(Position.BTN, classes[hand_name])
        assert frequency.raise_frequency == 1.0
        assert frequency.call_frequency == 0.0
    for hand_name in expected_fold:
        frequency = get_preflop_frequency(Position.BTN, classes[hand_name])
        assert frequency.raise_frequency == 0.0
        assert frequency.call_frequency == 0.0

    total_combos = 0
    raise_combos = 0
    for hand_class in classes.values():
        combos = 6 if hand_class.pair else 4 if hand_class.suited else 12
        total_combos += combos
        raise_combos += combos * get_preflop_frequency(Position.BTN, hand_class).raise_frequency
    assert round(raise_combos / total_combos * 100, 1) == 40.6


def test_preflop_betting_state_derivation():
    state = derive_preflop_state(
        Position.BB,
        (
            PlayerAction(Position.UTG, Action.RAISE, 2.5),
            PlayerAction(Position.HJ, Action.FOLD, 0.0),
            PlayerAction(Position.CO, Action.FOLD, 0.0),
            PlayerAction(Position.BTN, Action.FOLD, 0.0),
            PlayerAction(Position.SB, Action.FOLD, 0.0),
        ),
    )
    assert state.pot_size == 4.0
    assert state.current_bet == 2.5
    assert state.call_amount == 1.5
    assert state.active_opponent_count == 1
    assert state.next_to_act == Position.BB
    assert not state.is_closed
    assert state.legal_actions == (Action.FOLD, Action.CALL, Action.RAISE)
    assert state.min_raise_total == 4.0
    assert state.max_raise_total == 100.0

    invalid_raise = derive_preflop_state(
        Position.BB,
        (
            PlayerAction(Position.UTG, Action.RAISE, 2.5),
            PlayerAction(Position.HJ, Action.RAISE, 3.0),
        ),
    )
    assert invalid_raise.current_bet == 2.5
    assert invalid_raise.validation_errors

    all_in = derive_preflop_state(
        Position.BB,
        (
            PlayerAction(Position.UTG, Action.RAISE, 150.0),
        ),
    )
    assert all_in.current_bet == 100.0
    assert all_in.contributions[Position.UTG] == 100.0

    closed = derive_preflop_state(
        Position.BB,
        (
            PlayerAction(Position.UTG, Action.RAISE, 2.5),
            PlayerAction(Position.HJ, Action.FOLD, 0.0),
            PlayerAction(Position.CO, Action.FOLD, 0.0),
            PlayerAction(Position.BTN, Action.FOLD, 0.0),
            PlayerAction(Position.SB, Action.FOLD, 0.0),
            PlayerAction(Position.BB, Action.CALL, 1.5),
        ),
    )
    assert closed.is_closed
    assert closed.next_to_act is None
    assert closed.legal_actions == ()

    out_of_turn = derive_preflop_state(
        Position.BB,
        (PlayerAction(Position.BTN, Action.FOLD, 0.0),),
    )
    assert out_of_turn.validation_errors
    assert out_of_turn.next_to_act == Position.UTG

    short_call = derive_preflop_state(
        Position.BB,
        (
            PlayerAction(Position.UTG, Action.RAISE, 3.0),
            PlayerAction(Position.HJ, Action.CALL, 1.0),
        ),
    )
    assert short_call.validation_errors
    assert short_call.contributions[Position.HJ] == 0.0

    facing_all_in = derive_preflop_state(
        Position.BB,
        (PlayerAction(Position.UTG, Action.RAISE, 100.0),),
    )
    assert facing_all_in.legal_actions == (Action.FOLD, Action.CALL)


def test_solver_counts_position_order_context():
    hand = parse_hole_cards("Ah", "As")
    assert hand is not None

    folded_to_button = solve_preflop_decision(
        SolverInput(
            hero_position=Position.BTN,
            hero_hand=hand,
            pot_size=1.5,
            call_amount=0.0,
            raise_amount=2.5,
            simulations=10,
            prior_actions=(
                PlayerAction(Position.UTG, Action.FOLD, 0.0),
                PlayerAction(Position.HJ, Action.FOLD, 0.0),
                PlayerAction(Position.CO, Action.FOLD, 0.0),
            ),
            table_actions=(
                PlayerAction(Position.UTG, Action.FOLD, 0.0),
                PlayerAction(Position.HJ, Action.FOLD, 0.0),
                PlayerAction(Position.CO, Action.FOLD, 0.0),
                PlayerAction(Position.BTN, Action.RAISE, 2.5),
                PlayerAction(Position.SB, Action.FOLD, 0.0),
                PlayerAction(Position.BB, Action.FOLD, 0.0),
            ),
        )
    )
    assert folded_to_button.opponent_count == 0
    assert folded_to_button.fold_probability == 1.0

    small_blind_calls = solve_preflop_decision(
        SolverInput(
            hero_position=Position.BTN,
            hero_hand=hand,
            pot_size=1.5,
            call_amount=0.0,
            raise_amount=2.5,
            simulations=10,
            prior_actions=(
                PlayerAction(Position.UTG, Action.FOLD, 0.0),
                PlayerAction(Position.HJ, Action.FOLD, 0.0),
                PlayerAction(Position.CO, Action.FOLD, 0.0),
            ),
            table_actions=(
                PlayerAction(Position.UTG, Action.FOLD, 0.0),
                PlayerAction(Position.HJ, Action.FOLD, 0.0),
                PlayerAction(Position.CO, Action.FOLD, 0.0),
                PlayerAction(Position.BTN, Action.RAISE, 2.5),
                PlayerAction(Position.SB, Action.CALL, 2.5),
                PlayerAction(Position.BB, Action.FOLD, 0.0),
            ),
            future_contribution=2.5,
        )
    )
    assert small_blind_calls.opponent_count == 1
    assert small_blind_calls.fold_probability == 0.0

    facing_cutoff_raise_and_small_blind_call = solve_preflop_decision(
        SolverInput(
            hero_position=Position.BTN,
            hero_hand=hand,
            pot_size=4.0,
            call_amount=2.5,
            raise_amount=8.0,
            simulations=10,
            prior_actions=(
                PlayerAction(Position.UTG, Action.FOLD, 0.0),
                PlayerAction(Position.HJ, Action.FOLD, 0.0),
                PlayerAction(Position.CO, Action.RAISE, 2.5),
            ),
            table_actions=(
                PlayerAction(Position.UTG, Action.FOLD, 0.0),
                PlayerAction(Position.HJ, Action.FOLD, 0.0),
                PlayerAction(Position.CO, Action.RAISE, 2.5),
                PlayerAction(Position.BTN, Action.RAISE, 5.5),
                PlayerAction(Position.SB, Action.CALL, 8.0),
                PlayerAction(Position.BB, Action.FOLD, 0.0),
            ),
            future_contribution=8.0,
        )
    )
    assert facing_cutoff_raise_and_small_blind_call.opponent_count == 2

    repeated_opponent_action = solve_preflop_decision(
        SolverInput(
            hero_position=Position.BTN,
            hero_hand=hand,
            pot_size=12.0,
            call_amount=0.0,
            raise_amount=20.0,
            simulations=10,
            table_actions=(
                PlayerAction(Position.UTG, Action.RAISE, 2.5),
                PlayerAction(Position.BTN, Action.RAISE, 8.0),
                PlayerAction(Position.UTG, Action.CALL, 5.5),
            ),
        )
    )
    assert repeated_opponent_action.opponent_count == 1


def test_solver_check_and_raise_sizes():
    hand = parse_hole_cards("Ah", "As")
    assert hand is not None

    check_spot = solve_preflop_decision(
        SolverInput(
            hero_position=Position.BB,
            hero_hand=hand,
            pot_size=3.0,
            call_amount=0.0,
            raise_amount=0.0,
            candidate_raise_amounts=(),
            simulations=10,
            active_opponent_count=1,
        )
    )
    assert check_spot.recommendation == Action.CHECK
    assert any(action_ev.action == Action.CHECK for action_ev in check_spot.action_evs)

    multi_raise_spot = solve_preflop_decision(
        SolverInput(
            hero_position=Position.BTN,
            hero_hand=hand,
            pot_size=1.5,
            call_amount=0.0,
            raise_amount=2.5,
            candidate_raise_amounts=(2.5, 6.0),
            simulations=10,
            active_opponent_count=2,
        )
    )
    assert len([action_ev for action_ev in multi_raise_spot.action_evs if action_ev.action == Action.RAISE]) == 2
    assert multi_raise_spot.best_raise_amount in (2.5, 6.0)
    raise_evs = [action_ev for action_ev in multi_raise_spot.action_evs if action_ev.action == Action.RAISE]
    assert raise_evs[0].fold_probability != raise_evs[1].fold_probability


def test_mixed_frequencies_from_evs():
    frequencies = mixed_frequencies_from_named_evs(
        {
            "Fold": 0.0,
            "Call": 0.20,
            "Raise": 0.24,
        }
    )
    assert abs(sum(frequencies.values()) - 100.0) < 0.0001
    assert frequencies["Raise"] > frequencies["Call"] > frequencies["Fold"]

    pure = mixed_frequencies_from_named_evs(
        {
            "Fold": 0.0,
            "Call": -1.0,
            "Raise": -2.0,
        }
    )
    assert pure["Fold"] == 100.0


def test_calibrated_rfi_frequencies_match_reference_targets():
    targets = {
        "UTG": {"Raise": 17.5, "Fold": 82.5},
        "HJ": {"Raise": 21.7, "Fold": 78.3},
        "CO": {"Raise": 27.9, "Fold": 72.1},
        "BTN": {"Raise": 40.6, "Fold": 59.4},
        "SB": {"Raise": 34.4, "Call": 13.7, "Fold": 51.9},
    }
    for position, expected in targets.items():
        data = get_study_view_data(
            {
                "hero_position": position,
                "hero_hand": "AhAs",
                "raise_amount_bb": 0.0,
                "candidate_raise_amounts": [],
                "simulations": 5,
                "range_simulations": 1,
                "action_history": [],
                "auto_state": True,
            }
        )
        weighted = {"Fold": 0.0, "Call": 0.0, "Raise": 0.0}
        combo_total = 0
        for item in data["range_grid"]:
            combos = 6 if item["pair"] else (4 if item["suited"] else 12)
            combo_total += combos
            for action in weighted:
                weighted[action] += item["actions"].get(action, 0.0) * combos
        actual = {
            action: round(total / combo_total, 1)
            for action, total in weighted.items()
            if total > 0.0
        }
        assert actual == expected


def test_single_open_context_model_matches_reference_targets_and_shapes():
    spots = {
        ("HJ", "UTG"): {"Raise": 7.1, "Call": 1.4, "Fold": 91.5},
        ("CO", "HJ"): {"Raise": 8.3, "Call": 2.0, "Fold": 89.7},
        ("SB", "CO"): {"Raise": 9.6, "Call": 3.2, "Fold": 87.2},
        ("BB", "UTG"): {"Raise": 5.1, "Call": 17.5, "Fold": 77.4},
    }
    results = {}
    for (hero_position, opener_position), expected in spots.items():
        position_order = ("UTG", "HJ", "CO", "BTN", "SB", "BB")
        action_history = [
            {
                "position": position,
                "action": "raise" if position == opener_position else "fold",
                "amount": 2.5 if position == opener_position else 0.0,
            }
            for position in position_order[:position_order.index(hero_position)]
        ]
        data = get_study_view_data(
            {
                "hero_position": hero_position,
                "hero_hand": "AhAs",
                "simulations": 5,
                "range_simulations": 1,
                "action_history": action_history,
                "auto_state": True,
            }
        )
        weighted = {"Fold": 0.0, "Call": 0.0, "Raise": 0.0}
        combo_total = 0
        for item in data["range_grid"]:
            combos = 6 if item["pair"] else (4 if item["suited"] else 12)
            combo_total += combos
            for action in weighted:
                weighted[action] += item["actions"].get(action, 0.0) * combos
        actual = {
            action: round(total / combo_total, 1)
            for action, total in weighted.items()
        }
        assert actual == expected
        results[(hero_position, opener_position)] = {
            item["hand"]: item
            for item in data["range_grid"]
        }

    bb_vs_utg = results[("BB", "UTG")]
    assert bb_vs_utg["AA"]["recommended"] == "Raise"
    assert bb_vs_utg["A5s"]["recommended"] == "Raise"
    assert bb_vs_utg["KQs"]["recommended"] == "Call"
    assert bb_vs_utg["76s"]["recommended"] == "Call"
    assert bb_vs_utg["22"]["recommended"] == "Call"
    assert bb_vs_utg["72o"]["recommended"] == "Fold"

    hj_vs_utg = results[("HJ", "UTG")]
    assert hj_vs_utg["AA"]["recommended"] == "Raise"
    assert hj_vs_utg["99"]["recommended"] == "Call"
    assert hj_vs_utg["76s"]["recommended"] == "Fold"


def test_study_adapter_output_shape():
    data = get_study_view_data(
        {
            "hero_position": "BB",
            "hero_hand": "AhAs",
            "street": "preflop",
            "board_cards": "",
            "pot_bb": 4.0,
            "call_amount_bb": 2.0,
            "raise_amount_bb": 8.0,
            "simulations": 10,
            "action_history": [
                {"position": "UTG", "action": "raise", "amount": 2.5},
                {"position": "HJ", "action": "fold", "amount": 0.0},
            ],
            "active_opponent_count": 1,
            "auto_state": True,
            "range_simulations": 5,
        }
    )
    assert data["mode"] == "study"
    assert data["street"] == "preflop"
    assert data["hero_position"] == "BB"
    assert data["hero_hand"] == "AhAs"
    assert data["board_cards"] == ""
    assert data["pot_bb"] == 4.0
    assert data["call_amount_bb"] == 1.5
    assert data["betting_state"]["next_to_act"] == "CO"
    assert data["betting_state"]["seats"]["CO"]["can_act"]
    assert data["betting_state"]["seats"]["CO"]["available_actions"] == ["fold", "call", "raise"]
    assert not data["betting_state"]["seats"]["BB"]["can_act"]
    assert data["betting_state"]["min_raise_total_bb"] == 4.0
    assert data["betting_state"]["max_raise_total_bb"] == 100.0
    assert data["actions"]
    assert abs(sum(action["frequency"] for action in data["actions"]) - 100.0) < 0.0001

    closed_data = get_study_view_data(
        {
            "hero_position": "BB",
            "hero_hand": "AhAs",
            "raise_amount_bb": 8.0,
            "simulations": 10,
            "action_history": [
                {"position": "UTG", "action": "raise", "amount": 2.5},
                {"position": "HJ", "action": "fold", "amount": 0.0},
                {"position": "CO", "action": "fold", "amount": 0.0},
                {"position": "BTN", "action": "fold", "amount": 0.0},
                {"position": "SB", "action": "fold", "amount": 0.0},
                {"position": "BB", "action": "call", "amount": 1.5},
            ],
            "auto_state": True,
        }
    )
    assert closed_data["betting_state"]["is_closed"]
    assert closed_data["betting_state"]["next_to_act"] is None
    assert closed_data["betting_state"]["legal_actions"] == []
    assert closed_data["selected_hand"]["recommended"]
    assert len(closed_data["range_grid"]) == 169
    assert "metrics" in data
    assert data["metrics"]["equity"] == data["selected_hand"]["equity"]
    assert data["selected_hand"]["recommended"].lower() in data["explanation"].lower()
    assert data["range_simulations"] == 20
    assert data["opponent_ranges"]
    assert data["opponent_ranges"][0]["position"] == "UTG"
    assert data["opponent_ranges"][0]["source"] == "raise range"
    assert data["opponent_ranges"][0]["profile_key"] == "raise"
    assert data["opponent_ranges"][0]["continue_fraction"] == 0.48
    assert "hand_cards" in data
    assert len(data["range_grid"]) == 169
    assert len(data["hand_cards"]) == 169
    assert all(abs(sum(item["actions"].values()) - 100.0) < 0.0001 for item in data["range_grid"])
    assert any(item["hand"] == "AA" and item["representative_hand"] == "AsAh" for item in data["range_grid"])
    assert any(item["hand"] == "AKs" and item["representative_hand"] == "AsKs" for item in data["range_grid"])
    aa = next(item for item in data["range_grid"] if item["hand"] == "AA")
    seven_deuce = next(item for item in data["range_grid"] if item["hand"] == "72o")
    assert aa["recommended"] == "Raise"
    assert aa["actions"]["Raise"] >= 75.0
    assert seven_deuce["recommended"] == "Fold"
    assert seven_deuce["actions"]["Fold"] == 100.0

    auto_size_data = get_study_view_data(
        {
            "hero_position": "BB",
            "hero_hand": "AhAs",
            "raise_amount_bb": 0.0,
            "candidate_raise_amounts": [],
            "simulations": 10,
            "range_simulations": 5,
            "action_history": [
                {"position": "UTG", "action": "raise", "amount": 2.5},
                {"position": "HJ", "action": "fold", "amount": 0.0},
            ],
            "auto_state": True,
        }
    )
    assert auto_size_data["candidate_raise_amounts"]
    assert all(action["name"].startswith("Raise ") for action in auto_size_data["actions"] if "Raise" in action["name"])

    multi_size_data = get_study_view_data(
        {
            "hero_position": "BB",
            "hero_hand": "AhAs",
            "pot_bb": 4.0,
            "call_amount_bb": 1.5,
            "raise_amount_bb": 8.0,
            "candidate_raise_amounts": [4.0, 8.0, 12.0],
            "simulations": 10,
            "range_simulations": 5,
            "action_history": [
                {"position": "UTG", "action": "raise", "amount": 2.5},
                {"position": "HJ", "action": "fold", "amount": 0.0},
            ],
            "active_opponent_count": 1,
        }
    )
    raise_actions = [action for action in multi_size_data["actions"] if action["name"].startswith("Raise ")]
    aa_multi = multi_size_data["range_grid"][0]
    assert multi_size_data["candidate_raise_amounts"] == [4.0, 8.0, 12.0]
    assert len(raise_actions) == 3
    assert all("ev" in action and "frequency" in action for action in raise_actions)
    assert len(aa_multi["raise_options"]) == 3
    assert all("ev" in option and "frequency" in option for option in aa_multi["raise_options"])
    assert abs(sum(option["frequency"] for option in aa_multi["raise_options"]) - aa_multi["actions"]["Raise"]) < 0.0001

    flop_data = get_study_view_data(
        {
            "hero_position": "BTN",
            "hero_hand": "KdKh",
            "street": "flop",
            "board_cards": "AsQhJs",
            "pot_bb": 6.0,
            "call_amount_bb": 0.0,
            "raise_amount_bb": 4.0,
            "simulations": 10,
            "range_simulations": 5,
            "action_history": [],
            "active_opponent_count": 1,
            "auto_state": True,
        }
    )
    assert flop_data["street"] == "flop"
    assert flop_data["board_cards"] == "AsQhJs"
    assert not flop_data["auto_state"]
    assert flop_data["pot_bb"] == 6.0
    assert any(item["hand"] == "AA" and item["representative_hand"] != "AsAh" for item in flop_data["range_grid"])


def test_strategy_profile_normalization():
    profile = normalize_strategy_profile(
        {
            "default": {"raise": 2.0, "call": -1.0},
            "positions": {"UTG": {"raise": 0.33}},
            "raise_size_thresholds": {
                "large_raise_total_bb": 150.0,
                "all_in_total_bb": 40.0,
            },
        }
    )
    assert profile["default"]["raise"] == 1.0
    assert profile["default"]["call"] == 0.01
    assert profile["positions"]["UTG"]["raise"] == 0.33
    assert profile["positions"]["BB"]["unacted"] == 1.0
    assert profile["raise_size_thresholds"]["large_raise_total_bb"] == 100.0
    assert profile["raise_size_thresholds"]["all_in_total_bb"] == 100.0


def test_trainer_adapter_question_and_grade():
    question = get_trainer_question({"simulations": 10})
    assert question["question_id"]
    assert question["mode"] == "trainer"
    assert question["available_actions"]

    result = grade_trainer_answer(question["question_id"], question["available_actions"][0])
    assert result["question_id"] == question["question_id"]
    assert result["correct_action"] in question["available_actions"]
    assert 0 <= result["score"] <= 100
    assert result["actions"]

    for _ in range(20):
        assert generate_random_scenario("open_first").scenario_type == "open_first"

    for mode in ("open_first", "facing_open", "facing_3bet", "facing_4bet"):
        scenario = generate_random_scenario(mode)
        state = derive_preflop_state(scenario.hero_position, scenario.table_actions)
        assert not state.validation_errors
        assert state.next_to_act == scenario.hero_position


if __name__ == "__main__":
    test_card_parsing()
    test_board_parsing_and_equity()
    test_multiway_tie_equity_uses_split_pot_share()
    test_hand_evaluator()
    test_hand_evaluator_edge_cases()
    test_range_model()
    test_preflop_betting_state_derivation()
    test_solver_counts_position_order_context()
    test_solver_check_and_raise_sizes()
    test_mixed_frequencies_from_evs()
    test_calibrated_rfi_frequencies_match_reference_targets()
    test_single_open_context_model_matches_reference_targets_and_shapes()
    test_study_adapter_output_shape()
    test_strategy_profile_normalization()
    test_trainer_adapter_question_and_grade()
    print("All Python tests passed.")
