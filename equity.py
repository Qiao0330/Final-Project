from __future__ import annotations

from dataclasses import dataclass
from random import shuffle

from card import is_same_card
from common import Card, HoleCards, Rank, Suit
from poker_eval import compare_hand_values, evaluate_7cards

DECK_SIZE = 52
BOARD_SIZE = 5
MAX_OPPONENTS = 5


@dataclass(frozen=True)
class EquityInput:
    hero_hand: HoleCards
    opponent_count: int
    simulations: int


@dataclass(frozen=True)
class EquityResult:
    simulations: int
    wins: int
    ties: int
    losses: int
    win_rate: float
    tie_rate: float
    loss_rate: float
    equity: float


def _build_deck() -> list[Card]:
    return [
        Card(rank=Rank(rank), suit=Suit(suit))
        for suit in range(int(Suit.CLUBS), int(Suit.SPADES) + 1)
        for rank in range(int(Rank.TWO), int(Rank.ACE) + 1)
    ]


def _remove_known_cards(deck: list[Card], hand: HoleCards) -> list[Card]:
    return [
        card for card in deck
        if not is_same_card(card, hand.card1) and not is_same_card(card, hand.card2)
    ]


def _make_player_value(hand: HoleCards, board: list[Card]) -> object:
    return evaluate_7cards([hand.card1, hand.card2, *board])


def estimate_preflop_equity(equity_input: EquityInput) -> EquityResult:
    opponent_count = max(0, min(MAX_OPPONENTS, equity_input.opponent_count))
    simulations = max(1, equity_input.simulations)

    if opponent_count == 0:
        return EquityResult(
            simulations=simulations,
            wins=simulations,
            ties=0,
            losses=0,
            win_rate=1.0,
            tie_rate=0.0,
            loss_rate=0.0,
            equity=1.0,
        )

    wins = 0
    ties = 0
    losses = 0

    for _ in range(simulations):
        deck = _remove_known_cards(_build_deck(), equity_input.hero_hand)
        shuffle(deck)

        index = 0
        opponents: list[HoleCards] = []
        for _ in range(opponent_count):
            opponents.append(HoleCards(deck[index], deck[index + 1]))
            index += 2

        board = deck[index:index + BOARD_SIZE]
        hero_value = _make_player_value(equity_input.hero_hand, board)

        has_better_opponent = False
        has_equal_opponent = False

        for opponent in opponents:
            opponent_value = _make_player_value(opponent, board)
            comparison = compare_hand_values(hero_value, opponent_value)

            if comparison < 0:
                has_better_opponent = True
                break
            if comparison == 0:
                has_equal_opponent = True

        if has_better_opponent:
            losses += 1
        elif has_equal_opponent:
            ties += 1
        else:
            wins += 1

    win_rate = wins / simulations
    tie_rate = ties / simulations
    loss_rate = losses / simulations
    equity = (wins + 0.5 * ties) / simulations

    return EquityResult(
        simulations=simulations,
        wins=wins,
        ties=ties,
        losses=losses,
        win_rate=win_rate,
        tie_rate=tie_rate,
        loss_rate=loss_rate,
        equity=equity,
    )
