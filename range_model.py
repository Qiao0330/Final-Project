from __future__ import annotations

from dataclasses import dataclass

from card import is_same_card
from common import Card, HoleCards, Position, Rank, Suit


@dataclass(frozen=True)
class HandClass:
    name: str
    high_rank: int
    low_rank: int
    suited: bool
    pair: bool


@dataclass(frozen=True)
class RangeActionFrequency:
    open_frequency: float
    call_frequency: float
    raise_frequency: float


def _rank_to_char(rank: int) -> str:
    return {
        int(Rank.TWO): "2",
        int(Rank.THREE): "3",
        int(Rank.FOUR): "4",
        int(Rank.FIVE): "5",
        int(Rank.SIX): "6",
        int(Rank.SEVEN): "7",
        int(Rank.EIGHT): "8",
        int(Rank.NINE): "9",
        int(Rank.TEN): "T",
        int(Rank.JACK): "J",
        int(Rank.QUEEN): "Q",
        int(Rank.KING): "K",
        int(Rank.ACE): "A",
    }.get(rank, "?")


def _position_open_threshold(pos: Position) -> int:
    return {
        Position.UTG: 58,
        Position.HJ: 52,
        Position.CO: 46,
        Position.BTN: 39,
        Position.SB: 42,
        Position.BB: 36,
    }.get(pos, 58)


def _position_aggression(pos: Position) -> float:
    return {
        Position.UTG: 0.72,
        Position.HJ: 0.78,
        Position.CO: 0.84,
        Position.BTN: 0.90,
        Position.SB: 0.82,
        Position.BB: 0.70,
    }.get(pos, 0.75)


def _hand_strength_score(hand_class: HandClass) -> int:
    if hand_class.pair:
        return 45 + hand_class.high_rank * 3

    gap = hand_class.high_rank - hand_class.low_rank - 1
    score = hand_class.high_rank * 3 + hand_class.low_rank * 2

    if hand_class.suited:
        score += 6

    if gap == 0:
        score += 5
    elif gap == 1:
        score += 3
    elif gap == 2:
        score += 1
    else:
        score -= gap * 2

    if hand_class.high_rank >= int(Rank.TEN) and hand_class.low_rank >= int(Rank.TEN):
        score += 4

    if hand_class.high_rank == int(Rank.ACE):
        score += 3

    return score


def _combination_count(hand_class: HandClass) -> int:
    if hand_class.pair:
        return 6
    return 4 if hand_class.suited else 12


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _make_hand_class(high: int, low: int, suited: bool) -> HandClass:
    pair = high == low
    name = f"{_rank_to_char(high)}{_rank_to_char(low)}" if pair else (
        f"{_rank_to_char(high)}{_rank_to_char(low)}{'s' if suited else 'o'}"
    )
    return HandClass(name=name, high_rank=high, low_rank=low, suited=suited, pair=pair)


def get_hand_class(hand: HoleCards) -> HandClass:
    first = int(hand.card1.rank)
    second = int(hand.card2.rank)
    high = max(first, second)
    low = min(first, second)
    suited = hand.card1.suit == hand.card2.suit
    return _make_hand_class(high, low, suited)


def get_preflop_frequency(pos: Position, hand_class: HandClass) -> RangeActionFrequency:
    score = _hand_strength_score(hand_class)
    threshold = _position_open_threshold(pos)

    if score >= threshold + 7:
        open_frequency = 1.0
    elif score >= threshold + 3:
        open_frequency = 0.75
    elif score >= threshold:
        open_frequency = 0.50
    elif score >= threshold - 3:
        open_frequency = 0.25
    else:
        open_frequency = 0.0

    raise_frequency = open_frequency * _position_aggression(pos)
    call_frequency = open_frequency - raise_frequency
    return RangeActionFrequency(
        open_frequency=open_frequency,
        call_frequency=call_frequency,
        raise_frequency=raise_frequency,
    )


def is_hand_in_open_range(pos: Position, hand_class: HandClass) -> bool:
    return get_preflop_frequency(pos, hand_class).open_frequency > 0.0


def players_behind_count(pos: Position) -> int:
    if pos < Position.UTG or pos > Position.BB:
        return 0
    return int(Position.BB) - int(pos)


def _average_open_range_score(pos: Position) -> float:
    weighted_score = 0.0
    total_weight = 0.0

    for high in range(int(Rank.ACE), int(Rank.TWO) - 1, -1):
        for low in range(high, int(Rank.TWO) - 1, -1):
            suited_options = (False,) if high == low else (True, False)
            for suited in suited_options:
                hand_class = _make_hand_class(high, low, suited)
                frequency = get_preflop_frequency(pos, hand_class)
                combos = _combination_count(hand_class)
                score = _hand_strength_score(hand_class)
                weighted_score += score * frequency.open_frequency * combos
                total_weight += frequency.open_frequency * combos

    if total_weight <= 0.0:
        return float(_position_open_threshold(pos))
    return weighted_score / total_weight


def _estimate_single_opponent_fold_probability(
    hero_position: Position,
    opponent_position: Position,
    hero_hand: HoleCards,
    pot_size: float,
    raise_amount: float,
) -> float:
    if raise_amount <= 0.0:
        return 0.0

    hero_range_score = _average_open_range_score(hero_position)
    position_penalty = 0.03 if opponent_position == Position.SB else 0.0
    final_pot = pot_size + raise_amount + raise_amount
    call_amount = raise_amount
    total = 0
    folds = 0

    cards = [
        Card(rank=Rank(rank), suit=Suit(suit))
        for rank in range(int(Rank.TWO), int(Rank.ACE) + 1)
        for suit in range(int(Suit.CLUBS), int(Suit.SPADES) + 1)
    ]

    for first_index, first in enumerate(cards):
        if is_same_card(first, hero_hand.card1) or is_same_card(first, hero_hand.card2):
            continue

        for second in cards[first_index + 1:]:
            if is_same_card(second, hero_hand.card1) or is_same_card(second, hero_hand.card2):
                continue

            opponent_class = get_hand_class(HoleCards(first, second))
            score = _hand_strength_score(opponent_class)
            equity_vs_open_range = 0.50 + (score - hero_range_score) / 100.0 - position_penalty
            equity_vs_open_range = _clamp(equity_vs_open_range, 0.05, 0.95)
            continue_ev = equity_vs_open_range * final_pot - call_amount

            total += 1
            if continue_ev <= 0.0:
                folds += 1

    if total == 0:
        return 1.0
    return folds / total


def estimate_open_fold_probability(
    hero_position: Position,
    hero_hand: HoleCards,
    pot_size: float,
    raise_amount: float,
) -> float:
    if players_behind_count(hero_position) == 0:
        return 1.0

    all_fold_probability = 1.0
    for raw_pos in range(int(hero_position) + 1, int(Position.BB) + 1):
        single_fold_probability = _estimate_single_opponent_fold_probability(
            hero_position=hero_position,
            opponent_position=Position(raw_pos),
            hero_hand=hero_hand,
            pot_size=pot_size,
            raise_amount=raise_amount,
        )
        all_fold_probability *= single_fold_probability

    return _clamp(all_fold_probability, 0.0, 1.0)


def position_to_string(pos: Position) -> str:
    return {
        Position.UTG: "UTG",
        Position.HJ: "HJ",
        Position.CO: "CO",
        Position.BTN: "BTN",
        Position.SB: "SB",
        Position.BB: "BB",
    }.get(pos, "Unknown")


def opening_range_summary(pos: Position) -> str:
    return {
        Position.UTG: "tight: strong pairs, strong broadways, premium suited aces",
        Position.HJ: "medium-tight: pairs, broadways, suited aces, selected suited connectors",
        Position.CO: "medium: most pairs, broadways, suited aces, suited connectors",
        Position.BTN: "wide: many suited hands, broadways, aces, pairs, connectors",
        Position.SB: "wide but cautious: many playable hands, adjusted for out-of-position risk",
        Position.BB: "widest defend/check range in this simplified model",
    }.get(pos, "no range")
