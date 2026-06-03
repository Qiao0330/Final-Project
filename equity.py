from __future__ import annotations

from dataclasses import dataclass
from random import sample

from card import BOARD_SIZE, FULL_DECK
from common import Card, HoleCards
from poker_eval import compare_hand_values, evaluate_7cards

MAX_OPPONENTS = 5


@dataclass(frozen=True)
class EquityInput:
    hero_hand: HoleCards
    opponent_count: int
    simulations: int
    board_cards: tuple[Card, ...] = ()


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


def _available_deck(hero_hand: HoleCards, board_cards: tuple[Card, ...]) -> tuple[Card, ...]:
    known_cards = {hero_hand.card1, hero_hand.card2, *board_cards}
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
    board_cards = tuple(equity_input.board_cards[:BOARD_SIZE])
    available_deck = _available_deck(equity_input.hero_hand, board_cards)
    cards_needed = opponent_count * 2 + max(0, BOARD_SIZE - len(board_cards))

    for _ in range(simulations):
        dealt = sample(available_deck, cards_needed)
        runout = tuple(dealt[opponent_count * 2:opponent_count * 2 + max(0, BOARD_SIZE - len(board_cards))])
        board = (*board_cards, *runout)
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
