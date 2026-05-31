from card import parse_card, parse_hole_cards
from common import Position
from poker_eval import compare_hand_values, evaluate_7cards
from range_model import (
    estimate_open_fold_probability,
    get_hand_class,
    is_hand_in_open_range,
    players_behind_count,
)


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


if __name__ == "__main__":
    test_card_parsing()
    test_hand_evaluator()
    test_range_model()
    print("All Python tests passed.")
