from __future__ import annotations

from dataclasses import dataclass
from random import Random

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


def engaged_opponent_ranges(
    opponent_ranges: tuple[OpponentRange, ...],
    action_history: tuple[PlayerAction, ...],
) -> tuple[OpponentRange, ...]:
    latest_actions: dict[Position, Action] = {}
    for record in action_history:
        latest_actions[record.position] = record.action
    return tuple(
        opponent_range
        for opponent_range in opponent_ranges
        if latest_actions.get(opponent_range.position) in (Action.CALL, Action.RAISE, Action.CHECK)
    )


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
    equity_sum = 0.0
    simulation_count = max(1, simulations)
    hero_cards = {hero_hand.card1, hero_hand.card2}
    known_board = tuple(board_cards[:BOARD_SIZE])
    rng = Random(_simulation_seed(hero_hand, opponent_ranges, known_board, simulation_count))

    for _ in range(simulation_count):
        opponent_hands: list[HoleCards] = []
        known_cards = {*hero_cards, *known_board}
        for opponent_range in opponent_ranges:
            candidate = _draw_candidate(opponent_range, known_cards, rng)
            if candidate is None:
                continue
            opponent_hands.append(candidate.hand)
            known_cards.add(candidate.hand.card1)
            known_cards.add(candidate.hand.card2)

        deck = [card for card in FULL_DECK if card not in known_cards]
        board = (*known_board, *rng.sample(deck, max(0, BOARD_SIZE - len(known_board))))
        hero_value = evaluate_7cards((hero_hand.card1, hero_hand.card2, *board))
        better = False
        equal_opponents = 0

        for opponent_hand in opponent_hands:
            opponent_value = evaluate_7cards((opponent_hand.card1, opponent_hand.card2, *board))
            comparison = compare_hand_values(hero_value, opponent_value)
            if comparison < 0:
                better = True
                break
            if comparison == 0:
                equal_opponents += 1

        if better:
            continue
        if equal_opponents:
            ties += 1
            equity_sum += 1.0 / (equal_opponents + 1)
        else:
            wins += 1
            equity_sum += 1.0

    return equity_sum / simulation_count


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


def continuing_ranges_for_raise(
    opponent_ranges: tuple[OpponentRange, ...],
    raise_total: float,
    current_bet: float,
) -> tuple[tuple[OpponentRange, ...], float]:
    if not opponent_ranges:
        return (), 1.0

    strategy = load_strategy_profile()
    thresholds = strategy.get("raise_size_thresholds", {})
    if raise_total >= float(thresholds.get("all_in_total_bb", 99.0)):
        profile_key = "all_in"
    elif raise_total >= float(thresholds.get("large_raise_total_bb", 12.0)) or (
        current_bet > 0.0 and raise_total / current_bet >= 4.0
    ):
        profile_key = "large_raise"
    else:
        profile_key = "raise"

    continuing: list[OpponentRange] = []
    all_fold_probability = 1.0
    for opponent_range in opponent_ranges:
        continue_fraction = _strategy_fraction(strategy, opponent_range.position, profile_key)
        candidates = _top_weighted_candidates(list(opponent_range.candidates), continue_fraction)
        continue_weight = sum(candidate.weight for candidate in candidates)
        fold_probability = (
            1.0 - continue_weight / opponent_range.total_weight
            if opponent_range.total_weight > 0.0
            else 1.0
        )
        all_fold_probability *= max(0.0, min(1.0, fold_probability))
        continuing.append(
            OpponentRange(
                position=opponent_range.position,
                candidates=tuple(candidates),
                total_weight=continue_weight,
                source=f"continue versus raise to {raise_total:.1f} BB",
                profile_key=profile_key,
                continue_fraction=continue_fraction,
            )
        )
    return tuple(continuing), all_fold_probability


def single_caller_range(
    opponent_ranges: tuple[OpponentRange, ...],
) -> tuple[OpponentRange, ...]:
    if not opponent_ranges:
        return ()
    candidates = tuple(
        candidate
        for opponent_range in opponent_ranges
        for candidate in opponent_range.candidates
    )
    return (
        OpponentRange(
            position=opponent_ranges[0].position,
            candidates=candidates,
            total_weight=sum(candidate.weight for candidate in candidates),
            source="combined conditional caller range",
            profile_key="combined",
            continue_fraction=1.0,
        ),
    )


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


def _simulation_seed(
    hero_hand: HoleCards,
    opponent_ranges: tuple[OpponentRange, ...],
    board_cards: tuple[Card, ...],
    simulations: int,
) -> int:
    values = [
        int(hero_hand.card1.rank), int(hero_hand.card1.suit),
        int(hero_hand.card2.rank), int(hero_hand.card2.suit),
        simulations,
    ]
    for card in board_cards:
        values.extend((int(card.rank), int(card.suit)))
    for opponent_range in opponent_ranges:
        values.extend((int(opponent_range.position), len(opponent_range.candidates)))

    seed = 0
    for value in values:
        seed = (seed * 131 + value) & 0xFFFFFFFF
    return seed


def _draw_candidate(
    opponent_range: OpponentRange,
    known_cards: set[Card],
    rng: Random,
) -> RangeCandidate | None:
    available = [
        candidate for candidate in opponent_range.candidates
        if candidate.hand.card1 not in known_cards and candidate.hand.card2 not in known_cards
    ]
    if not available:
        return None
    return rng.choices(available, weights=[candidate.weight for candidate in available], k=1)[0]
