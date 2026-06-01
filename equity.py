from __future__ import annotations

from dataclasses import dataclass
from random import sample

from common import Card, HoleCards, Rank, Suit
from poker_eval import compare_hand_values, evaluate_7cards

DECK_SIZE = 52
BOARD_SIZE = 5
MAX_OPPONENTS = 5
FULL_DECK = tuple(
    Card(rank=Rank(rank), suit=Suit(suit))
    for suit in range(int(Suit.CLUBS), int(Suit.SPADES) + 1)
    for rank in range(int(Rank.TWO), int(Rank.ACE) + 1)
)


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


def _available_deck(hero_hand: HoleCards) -> tuple[Card, ...]:
    known_cards = {hero_hand.card1, hero_hand.card2}
    return tuple(card for card in FULL_DECK if card not in known_cards)


def _make_player_value(card1: Card, card2: Card, board: tuple[Card, ...]) -> object:
    return evaluate_7cards((card1, card2, *board))


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
    hero_card1 = equity_input.hero_hand.card1
    hero_card2 = equity_input.hero_hand.card2
    available_deck = _available_deck(equity_input.hero_hand)
    cards_needed = opponent_count * 2 + BOARD_SIZE

    for _ in range(simulations):
        dealt = sample(available_deck, cards_needed)
        board = tuple(dealt[opponent_count * 2:opponent_count * 2 + BOARD_SIZE])
        hero_value = _make_player_value(hero_card1, hero_card2, board)

        has_better_opponent = False
        has_equal_opponent = False

        for opponent_index in range(opponent_count):
            first = opponent_index * 2
            opponent_value = _make_player_value(dealt[first], dealt[first + 1], board)
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
