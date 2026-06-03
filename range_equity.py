from __future__ import annotations

from dataclasses import dataclass
from random import choices, sample

from card import BOARD_SIZE, FULL_DECK
from common import TABLE_POSITIONS, Action, Card, HoleCards, PlayerAction, Position
from poker_eval import compare_hand_values, evaluate_7cards
from range_model import get_hand_class, get_preflop_frequency, hand_strength_score, position_to_string
from strategy_profile import load_strategy_profile


POSITIONS = TABLE_POSITIONS


@dataclass(frozen=True)
class RangeCandidate:
    hand: HoleCards
    weight: float
    score: float


@dataclass(frozen=True)
class OpponentRange:
    position: Position
    candidates: tuple[RangeCandidate, ...]
    total_weight: float
    source: str
    profile_key: str
    continue_fraction: float


def infer_opponent_ranges(
    hero_position: Position,
    hero_hand: HoleCards,
    action_history: tuple[PlayerAction, ...],
) -> tuple[OpponentRange, ...]:
    folded = {
        record.position
        for record in action_history
        if record.action == Action.FOLD
    }
    active_positions = [
        position for position in POSITIONS
        if position != hero_position and position not in folded
    ]
    ranges: list[OpponentRange] = []
    for position in active_positions:
        source, profile_key, continue_fraction = _range_profile(position, action_history)
        candidates = _range_candidates(position, hero_hand, continue_fraction)
        ranges.append(
            OpponentRange(
                position=position,
                candidates=tuple(candidates),
                total_weight=sum(candidate.weight for candidate in candidates),
                source=source,
                profile_key=profile_key,
                continue_fraction=continue_fraction,
            )
        )
    return tuple(ranges)


def estimate_equity_against_ranges(
    hero_hand: HoleCards,
    opponent_ranges: tuple[OpponentRange, ...],
    simulations: int,
    board_cards: tuple[Card, ...] = (),
) -> float:
    if not opponent_ranges:
        return 1.0

    wins = 0
    ties = 0
    simulation_count = max(1, simulations)
    hero_cards = {hero_hand.card1, hero_hand.card2}
    known_board = tuple(board_cards[:BOARD_SIZE])

    for _ in range(simulation_count):
        opponent_hands: list[HoleCards] = []
        known_cards = {*hero_cards, *known_board}
        for opponent_range in opponent_ranges:
            candidate = _draw_candidate(opponent_range, known_cards)
            if candidate is None:
                continue
            opponent_hands.append(candidate.hand)
            known_cards.add(candidate.hand.card1)
            known_cards.add(candidate.hand.card2)

        deck = [card for card in FULL_DECK if card not in known_cards]
        board = (*known_board, *sample(deck, max(0, BOARD_SIZE - len(known_board))))
        hero_value = evaluate_7cards((hero_hand.card1, hero_hand.card2, *board))
        better = False
        equal = False

        for opponent_hand in opponent_hands:
            opponent_value = evaluate_7cards((opponent_hand.card1, opponent_hand.card2, *board))
            comparison = compare_hand_values(hero_value, opponent_value)
            if comparison < 0:
                better = True
                break
            if comparison == 0:
                equal = True

        if better:
            continue
        if equal:
            ties += 1
        else:
            wins += 1

    return (wins + 0.5 * ties) / simulation_count


def range_summary_to_dict(opponent_ranges: tuple[OpponentRange, ...]) -> list[dict]:
    return [
        {
            "position": position_to_string(opponent_range.position),
            "candidate_count": len(opponent_range.candidates),
            "total_weight": opponent_range.total_weight,
            "source": opponent_range.source,
            "profile_key": opponent_range.profile_key,
            "continue_fraction": opponent_range.continue_fraction,
        }
        for opponent_range in opponent_ranges
    ]


def _range_profile(position: Position, action_history: tuple[PlayerAction, ...]) -> tuple[str, str, float]:
    strategy = load_strategy_profile()
    position_actions = [
        record for record in action_history
        if record.position == position
    ]
    if not position_actions:
        return "unacted open range", "unacted", _strategy_fraction(strategy, position, "unacted")
    last_action = position_actions[-1]
    if last_action.action == Action.RAISE:
        thresholds = strategy.get("raise_size_thresholds", {})
        if last_action.amount >= float(thresholds.get("all_in_total_bb", 99.0)):
            return "all-in range", "all_in", _strategy_fraction(strategy, position, "all_in")
        if last_action.amount >= float(thresholds.get("large_raise_total_bb", 12.0)):
            return "large raise range", "large_raise", _strategy_fraction(strategy, position, "large_raise")
        return "raise range", "raise", _strategy_fraction(strategy, position, "raise")
    if last_action.action == Action.CALL:
        return "calling range", "call", _strategy_fraction(strategy, position, "call")
    if last_action.action == Action.CHECK:
        return "checking range", "check", _strategy_fraction(strategy, position, "check")
    return "active range", "unacted", _strategy_fraction(strategy, position, "unacted")

def _strategy_fraction(strategy: dict, position: Position, key: str) -> float:
    position_name = position_to_string(position)
    value = (
        strategy.get("positions", {})
        .get(position_name, {})
        .get(key, strategy.get("default", {}).get(key, 1.0))
    )
    return max(0.01, min(1.0, float(value)))


def _range_candidates(
    position: Position,
    hero_hand: HoleCards,
    continue_fraction: float,
) -> list[RangeCandidate]:
    candidates: list[RangeCandidate] = []
    hero_cards = {hero_hand.card1, hero_hand.card2}
    for first_index, first in enumerate(FULL_DECK):
        if first in hero_cards:
            continue
        for second in FULL_DECK[first_index + 1:]:
            if second in hero_cards:
                continue
            opponent_hand = HoleCards(first, second)
            hand_class = get_hand_class(opponent_hand)
            frequency = get_preflop_frequency(position, hand_class).open_frequency
            if frequency <= 0.0:
                continue
            candidates.append(
                RangeCandidate(
                    hand=opponent_hand,
                    weight=frequency,
                    score=hand_strength_score(hand_class),
                )
            )
    return _top_weighted_candidates(candidates, continue_fraction)


def _top_weighted_candidates(candidates: list[RangeCandidate], continue_fraction: float) -> list[RangeCandidate]:
    if not candidates:
        return []
    target_weight = sum(candidate.weight for candidate in candidates) * max(0.01, min(1.0, continue_fraction))
    selected: list[RangeCandidate] = []
    running_weight = 0.0
    for candidate in sorted(candidates, key=lambda item: item.score, reverse=True):
        selected.append(candidate)
        running_weight += candidate.weight
        if running_weight >= target_weight:
            break
    return selected or candidates[:1]


def _draw_candidate(opponent_range: OpponentRange, known_cards: set[Card]) -> RangeCandidate | None:
    available = [
        candidate for candidate in opponent_range.candidates
        if candidate.hand.card1 not in known_cards and candidate.hand.card2 not in known_cards
    ]
    if not available:
        return None
    return choices(available, weights=[candidate.weight for candidate in available], k=1)[0]
