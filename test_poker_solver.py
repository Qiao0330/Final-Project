from card import parse_card, parse_hole_cards
from common import Action, PlayerAction, Position
from poker_eval import HandCategory, compare_hand_values, evaluate_7cards
from range_model import (
    estimate_open_fold_probability,
    get_hand_class,
    is_hand_in_open_range,
    players_behind_count,
)
from solver import SolverInput, solve_preflop_decision


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
        )
    )
    assert folded_to_button.opponent_count == 2

    facing_cutoff_raise = solve_preflop_decision(
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
        )
    )
    assert facing_cutoff_raise.opponent_count == 3


if __name__ == "__main__":
    test_card_parsing()
    test_hand_evaluator()
    test_hand_evaluator_edge_cases()
    test_range_model()
    test_solver_counts_position_order_context()
    print("All Python tests passed.")
