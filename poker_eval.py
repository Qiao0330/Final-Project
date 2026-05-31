from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import IntEnum
from itertools import combinations

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


def _straight_high_card(rank_counts: Counter[int]) -> int:
    for high in range(int(Rank.ACE), int(Rank.SIX) - 1, -1):
        if all(rank_counts[high - offset] > 0 for offset in range(5)):
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


def _evaluate_5cards(cards: tuple[Card, ...]) -> HandValue:
    rank_counts = Counter(int(card.rank) for card in cards)
    suit_counts = Counter(card.suit for card in cards)
    ranks_desc = sorted((int(card.rank) for card in cards), reverse=True)
    flush = max(suit_counts.values()) == 5
    straight_high = _straight_high_card(rank_counts)

    if flush and straight_high:
        return HandValue(HandCategory.STRAIGHT_FLUSH, (straight_high,))

    four = 0
    three = 0
    pairs: list[int] = []
    kickers: list[int] = []

    for rank in range(int(Rank.ACE), int(Rank.TWO) - 1, -1):
        count = rank_counts[rank]
        if count == 4:
            four = rank
        elif count == 3:
            three = rank
        elif count == 2:
            pairs.append(rank)
        elif count == 1:
            kickers.append(rank)

    if four:
        return HandValue(HandCategory.FOUR_OF_A_KIND, (four, kickers[0]))
    if three and pairs:
        return HandValue(HandCategory.FULL_HOUSE, (three, pairs[0]))
    if flush:
        return HandValue(HandCategory.FLUSH, tuple(ranks_desc))
    if straight_high:
        return HandValue(HandCategory.STRAIGHT, (straight_high,))
    if three:
        return HandValue(HandCategory.THREE_OF_A_KIND, (three, kickers[0], kickers[1]))
    if len(pairs) == 2:
        return HandValue(HandCategory.TWO_PAIR, (pairs[0], pairs[1], kickers[0]))
    if len(pairs) == 1:
        return HandValue(HandCategory.ONE_PAIR, (pairs[0], kickers[0], kickers[1], kickers[2]))
    return HandValue(HandCategory.HIGH_CARD, tuple(ranks_desc))


def evaluate_7cards(cards: list[Card] | tuple[Card, ...]) -> HandValue:
    if len(cards) != 7:
        raise ValueError("evaluate_7cards expects exactly 7 cards")

    return max((_evaluate_5cards(combo) for combo in combinations(cards, 5)), key=_hand_value_key)


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
