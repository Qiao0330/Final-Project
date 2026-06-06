from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from card import FULL_DECK, is_same_card
from common import Card, HoleCards, Position, Rank, Suit


RANKS_DESCENDING = (
    int(Rank.ACE),
    int(Rank.KING),
    int(Rank.QUEEN),
    int(Rank.JACK),
    int(Rank.TEN),
    int(Rank.NINE),
    int(Rank.EIGHT),
    int(Rank.SEVEN),
    int(Rank.SIX),
    int(Rank.FIVE),
    int(Rank.FOUR),
    int(Rank.THREE),
    int(Rank.TWO),
)

TOTAL_PREFLOP_COMBOS = 1326
RFI_RAISE_TARGETS = {
    Position.UTG: 0.175,
    Position.HJ: 0.217,
    Position.CO: 0.279,
    Position.BTN: 0.406,
    Position.SB: 0.344,
}
RFI_CALL_TARGETS = {
    Position.UTG: 0.0,
    Position.HJ: 0.0,
    Position.CO: 0.0,
    Position.BTN: 0.0,
    Position.SB: 0.137,
}
BTN_RFI_RAISE_HANDS = frozenset(
    """
    AA AKs AQs AJs ATs A9s A8s A7s A6s A5s A4s A3s A2s
    AKo KK KQs KJs KTs K9s K8s K7s K6s K5s K4s K3s K2s
    AQo KQo QQ QJs QTs Q9s Q8s Q7s Q6s Q5s Q4s Q3s
    AJo KJo QJo JJ JTs J9s J8s J7s J6s J5s
    ATo KTo QTo JTo TT T9s T8s T7s T6s
    A9o K9o Q9o J9o T9o 99 98s 97s
    A8o K8o 88 87s 86s
    A7o 77 76s
    A6o 66 65s
    A5o 55 54s
    A4o 44
    A3o 33
    22
    """.split()
)


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
        Position.UTG: 66,
        Position.HJ: 62,
        Position.CO: 56,
        Position.BTN: 45,
        Position.SB: 50,
        Position.BB: 62,
    }.get(pos, 66)


def _position_aggression(pos: Position) -> float:
    return {
        Position.UTG: 0.98,
        Position.HJ: 0.98,
        Position.CO: 0.98,
        Position.BTN: 0.96,
        Position.SB: 0.94,
        Position.BB: 0.90,
    }.get(pos, 0.96)


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
    raise_frequency, call_frequency = _calibrated_rfi_frequency(pos, hand_class)
    open_frequency = raise_frequency + call_frequency
    return RangeActionFrequency(
        open_frequency=open_frequency,
        call_frequency=call_frequency,
        raise_frequency=raise_frequency,
    )


def _calibrated_rfi_frequency(pos: Position, hand_class: HandClass) -> tuple[float, float]:
    if pos == Position.BTN:
        return (1.0 if hand_class.name in BTN_RFI_RAISE_HANDS else 0.0), 0.0

    raise_target = RFI_RAISE_TARGETS.get(pos)
    if raise_target is None:
        return _legacy_frequency(pos, hand_class)

    raise_map = _frequency_map_for_target(raise_target)
    call_map = _frequency_map_for_target(
        RFI_CALL_TARGETS.get(pos, 0.0),
        excluded=tuple(sorted(raise_map.items())),
    )
    return raise_map.get(hand_class.name, 0.0), call_map.get(hand_class.name, 0.0)


def _legacy_frequency(pos: Position, hand_class: HandClass) -> tuple[float, float]:
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
    return raise_frequency, open_frequency - raise_frequency


@lru_cache(maxsize=None)
def _frequency_map_for_target(
    target_fraction: float,
    excluded: tuple[tuple[str, float], ...] = (),
) -> dict[str, float]:
    excluded_map = dict(excluded)
    target_combos = TOTAL_PREFLOP_COMBOS * max(0.0, min(1.0, target_fraction))
    selected: dict[str, float] = {}
    used_combos = 0.0
    candidates = sorted(
        all_preflop_hand_classes(),
        key=lambda item: (_hand_strength_score(item), _combination_count(item)),
        reverse=True,
    )
    for candidate in candidates:
        if excluded_map.get(candidate.name, 0.0) >= 1.0:
            continue
        combos = _combination_count(candidate)
        available_frequency = 1.0 - excluded_map.get(candidate.name, 0.0)
        available_combos = combos * available_frequency
        remaining = target_combos - used_combos
        if remaining <= 0.0:
            break
        frequency = min(available_frequency, remaining / combos)
        if frequency > 0.0:
            selected[candidate.name] = frequency
            used_combos += combos * frequency
    return selected


def is_hand_in_open_range(pos: Position, hand_class: HandClass) -> bool:
    return get_preflop_frequency(pos, hand_class).open_frequency > 0.0


def hand_strength_score(hand_class: HandClass) -> int:
    return _hand_strength_score(hand_class)


def hand_combo_count(hand_class: HandClass) -> int:
    return _combination_count(hand_class)


def three_bet_response_targets(
    opener_position: Position,
    three_bettor_position: Position,
) -> tuple[float, float]:
    opener_late = opener_position in (Position.CO, Position.BTN, Position.SB)
    blind_three_bet = three_bettor_position in (Position.SB, Position.BB)

    call_target = {
        Position.UTG: 0.055,
        Position.HJ: 0.068,
        Position.CO: 0.088,
        Position.BTN: 0.128,
        Position.SB: 0.078,
    }.get(opener_position, 0.08)
    raise_target = {
        Position.UTG: 0.032,
        Position.HJ: 0.040,
        Position.CO: 0.052,
        Position.BTN: 0.072,
        Position.SB: 0.048,
    }.get(opener_position, 0.045)

    if blind_three_bet:
        call_target += 0.018 if opener_late else 0.010
        raise_target += 0.008
    if three_bettor_position == Position.BB and opener_position == Position.SB:
        call_target += 0.035
        raise_target += 0.012

    return _clamp(call_target, 0.035, 0.18), _clamp(raise_target, 0.025, 0.10)


def three_bet_call_suitability(
    hand_class: HandClass,
    opener_position: Position,
    three_bettor_position: Position,
) -> float:
    high = hand_class.high_rank
    low = hand_class.low_rank
    gap = max(0, high - low - 1)
    in_position = opener_position not in (Position.SB, Position.BB)
    blind_three_bet = three_bettor_position in (Position.SB, Position.BB)

    score = high * 1.35 + low * 1.35
    if hand_class.pair:
        score += 26.0 + high * 1.4
        if high <= int(Rank.FIVE):
            score -= 4.0
    if hand_class.suited:
        score += 16.0
    if gap == 0:
        score += 8.0
    elif gap == 1:
        score += 6.0
    elif gap == 2:
        score += 3.0
    elif gap >= 4:
        score -= gap * 2.6

    if high == int(Rank.ACE):
        score += 8.0 if hand_class.suited else 2.0
        if low <= int(Rank.FIVE) and hand_class.suited:
            score += 7.0
    elif high == int(Rank.KING) and hand_class.suited:
        score += 5.0
    if high >= int(Rank.TEN) and low >= int(Rank.TEN):
        score += 6.0
    if hand_class.suited and high <= int(Rank.JACK) and gap <= 1:
        score += 7.0
    if not hand_class.suited and not hand_class.pair and low < int(Rank.TEN):
        score -= 12.0
    if not hand_class.suited and high < int(Rank.ACE) and low < int(Rank.QUEEN):
        score -= 5.0

    if in_position:
        score += 4.0
    else:
        score -= 4.0
    if blind_three_bet:
        score += 2.5
    if opener_position in (Position.UTG, Position.HJ):
        score -= 3.0

    return score


def three_bet_raise_suitability(
    hand_class: HandClass,
    opener_position: Position,
    three_bettor_position: Position,
) -> float:
    high = hand_class.high_rank
    low = hand_class.low_rank
    gap = max(0, high - low - 1)
    value_score = high * 1.55 + low * 1.05

    if hand_class.pair:
        if high >= int(Rank.QUEEN):
            value_score += 34.0 + high * 2.2
        elif high >= int(Rank.TEN):
            value_score += 22.0 + high * 1.2
        else:
            value_score += 2.0
    if high >= int(Rank.TEN) and low >= int(Rank.TEN):
        value_score += 8.0

    bluff_score = 0.0
    if high == int(Rank.ACE):
        bluff_score += 18.0
        if hand_class.suited and low <= int(Rank.FIVE):
            bluff_score += 18.0
        elif hand_class.suited:
            bluff_score += 7.0
        elif low >= int(Rank.QUEEN):
            bluff_score += 5.0
    elif high == int(Rank.KING):
        bluff_score += 3.0
        if hand_class.suited:
            bluff_score += 2.0
        if hand_class.suited and low <= int(Rank.FIVE):
            bluff_score += 7.0
        if low >= int(Rank.QUEEN):
            bluff_score -= 8.0
    elif high == int(Rank.QUEEN) and hand_class.suited and low >= int(Rank.TEN):
        bluff_score += 5.0

    if hand_class.suited and gap <= 1 and high <= int(Rank.JACK):
        bluff_score += 8.0
    if hand_class.suited and gap <= 2:
        bluff_score += 3.0
    if not hand_class.suited and not hand_class.pair and low < int(Rank.QUEEN):
        bluff_score -= 14.0
    if hand_class.pair and high < int(Rank.TEN):
        bluff_score -= 10.0

    if opener_position in (Position.CO, Position.BTN, Position.SB):
        bluff_score += 4.0
    if three_bettor_position in (Position.SB, Position.BB):
        bluff_score += 2.0
    if opener_position in (Position.UTG, Position.HJ):
        bluff_score -= 4.0

    return value_score + bluff_score


def all_preflop_hand_classes() -> tuple[HandClass, ...]:
    classes: list[HandClass] = []
    for row_rank in RANKS_DESCENDING:
        for col_rank in RANKS_DESCENDING:
            if row_rank == col_rank:
                classes.append(_make_hand_class(row_rank, col_rank, False))
            elif row_rank > col_rank:
                classes.append(_make_hand_class(row_rank, col_rank, True))
            else:
                classes.append(_make_hand_class(col_rank, row_rank, False))
    return tuple(classes)


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

    for first_index, first in enumerate(FULL_DECK):
        if is_same_card(first, hero_hand.card1) or is_same_card(first, hero_hand.card2):
            continue

        for second in FULL_DECK[first_index + 1:]:
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
