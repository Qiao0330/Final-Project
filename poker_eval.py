from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

from common import Card, Rank


class HandCategory(IntEnum):
    HIGH_CARD = 0
    ONE_PAIR = 1
    TWO_PAIR = 2
    THREE_OF_A_KIND = 3
    STRAIGHT = 4
    FLUSH = 5
    FULL_HOUSE = 6
    FOUR_OF_A_KIND = 7
    STRAIGHT_FLUSH = 8


@dataclass(frozen=True)
class HandValue:
    category: HandCategory
    tie_breakers: tuple[int, ...] = field(default_factory=tuple)


def _straight_high_card(rank_counts: list[int]) -> int:
    for high in range(int(Rank.ACE), int(Rank.SIX) - 1, -1):
        if (
            rank_counts[high] > 0
            and rank_counts[high - 1] > 0
            and rank_counts[high - 2] > 0
            and rank_counts[high - 3] > 0
            and rank_counts[high - 4] > 0
        ):
            return high

    if (
        rank_counts[int(Rank.ACE)] > 0
        and rank_counts[int(Rank.FIVE)] > 0
        and rank_counts[int(Rank.FOUR)] > 0
        and rank_counts[int(Rank.THREE)] > 0
        and rank_counts[int(Rank.TWO)] > 0
    ):
        return int(Rank.FIVE)

    return 0


def _top_ranks(rank_counts: list[int], count: int, exclude: tuple[int, ...] = ()) -> tuple[int, ...]:
    ranks: list[int] = []
    excluded = set(exclude)

    for rank in range(int(Rank.ACE), int(Rank.TWO) - 1, -1):
        if rank in excluded:
            continue
        if rank_counts[rank] > 0:
            ranks.append(rank)
            if len(ranks) == count:
                break

    return tuple(ranks)


def evaluate_7cards(cards: list[Card] | tuple[Card, ...]) -> HandValue:
    if len(cards) != 7:
        raise ValueError("evaluate_7cards expects exactly 7 cards")

    rank_counts = [0] * 15
    suited_ranks: list[list[int]] = [[], [], [], []]

    for card in cards:
        rank = int(card.rank)
        suit = int(card.suit)
        rank_counts[rank] += 1
        suited_ranks[suit].append(rank)

    # Straight flush
    for ranks in suited_ranks:
        if len(ranks) >= 5:
            suited_counts = [0] * 15
            for rank in ranks:
                suited_counts[rank] += 1
            straight_flush_high = _straight_high_card(suited_counts)
            if straight_flush_high:
                return HandValue(HandCategory.STRAIGHT_FLUSH, (straight_flush_high,))

    quads: list[int] = []
    trips: list[int] = []
    pairs: list[int] = []

    for rank in range(int(Rank.ACE), int(Rank.TWO) - 1, -1):
        count = rank_counts[rank]
        if count == 4:
            quads.append(rank)
        elif count == 3:
            trips.append(rank)
        elif count == 2:
            pairs.append(rank)

    # Four of a kind
    if quads:
        quad = quads[0]
        kicker = _top_ranks(rank_counts, 1, (quad,))[0]
        return HandValue(HandCategory.FOUR_OF_A_KIND, (quad, kicker))

    # Full house. If there are two trips, the lower trip can be used as the pair.
    if trips and (len(trips) >= 2 or pairs):
        trip = trips[0]
        pair = trips[1] if len(trips) >= 2 else pairs[0]
        return HandValue(HandCategory.FULL_HOUSE, (trip, pair))

    # Flush
    best_flush: tuple[int, ...] | None = None
    for ranks in suited_ranks:
        if len(ranks) >= 5:
            flush_ranks = tuple(sorted(ranks, reverse=True)[:5])
            if best_flush is None or flush_ranks > best_flush:
                best_flush = flush_ranks
    if best_flush is not None:
        return HandValue(HandCategory.FLUSH, best_flush)

    # Straight
    straight_high = _straight_high_card(rank_counts)
    if straight_high:
        return HandValue(HandCategory.STRAIGHT, (straight_high,))

    # Three of a kind
    if trips:
        trip = trips[0]
        kickers = _top_ranks(rank_counts, 2, (trip,))
        return HandValue(HandCategory.THREE_OF_A_KIND, (trip, *kickers))

    # Two pair
    if len(pairs) == 2:
        kicker = _top_ranks(rank_counts, 1, (pairs[0], pairs[1]))[0]
        return HandValue(HandCategory.TWO_PAIR, (pairs[0], pairs[1], kicker))

    if len(pairs) >= 3:
        kicker = _top_ranks(rank_counts, 1, (pairs[0], pairs[1]))[0]
        return HandValue(HandCategory.TWO_PAIR, (pairs[0], pairs[1], kicker))

    # One pair
    if len(pairs) == 1:
        pair = pairs[0]
        kickers = _top_ranks(rank_counts, 3, (pair,))
        return HandValue(HandCategory.ONE_PAIR, (pair, *kickers))

    return HandValue(HandCategory.HIGH_CARD, _top_ranks(rank_counts, 5))


def compare_hand_values(a: HandValue, b: HandValue) -> int:
    a_key = _hand_value_key(a)
    b_key = _hand_value_key(b)

    if a_key > b_key:
        return 1
    if a_key < b_key:
        return -1
    return 0


def _hand_value_key(value: HandValue) -> tuple[int, tuple[int, ...]]:
    return int(value.category), value.tie_breakers


def hand_category_to_string(category: HandCategory) -> str:
    names = {
        HandCategory.STRAIGHT_FLUSH: "Straight flush",
        HandCategory.FOUR_OF_A_KIND: "Four of a kind",
        HandCategory.FULL_HOUSE: "Full house",
        HandCategory.FLUSH: "Flush",
        HandCategory.STRAIGHT: "Straight",
        HandCategory.THREE_OF_A_KIND: "Three of a kind",
        HandCategory.TWO_PAIR: "Two pair",
        HandCategory.ONE_PAIR: "One pair",
        HandCategory.HIGH_CARD: "High card",
    }
    return names.get(category, "Unknown")
