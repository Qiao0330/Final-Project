from __future__ import annotations

from dataclasses import dataclass
from random import choices, choice, sample

from card import card_to_string
from common import Action, Card, HoleCards, PlayerAction, Position, Rank, Suit
from poker_eval import compare_hand_values, evaluate_7cards
from range_model import get_hand_class, get_preflop_frequency, position_to_string


POSITIONS = (Position.UTG, Position.HJ, Position.CO, Position.BTN, Position.SB, Position.BB)
STACK_BB = 100.0
DEFAULT_SIMULATIONS = 5000
BOARD_SIZE = 5

FULL_DECK = tuple(
    Card(rank=Rank(rank), suit=Suit(suit))
    for suit in range(int(Suit.CLUBS), int(Suit.SPADES) + 1)
    for rank in range(int(Rank.TWO), int(Rank.ACE) + 1)
)


@dataclass(frozen=True)
class TrainerOption:
    label: str
    action: Action
    call_amount: float
    raise_amount: float
    total_bet: float


@dataclass(frozen=True)
class TrainerScenario:
    hero_position: Position
    hero_hand: HoleCards
    opener_position: Position
    open_size: float
    pot_size: float
    call_amount: float
    table_actions: tuple[PlayerAction, ...]
    options: tuple[TrainerOption, ...]


@dataclass(frozen=True)
class TrainerOptionResult:
    option: TrainerOption
    ev: float
    equity: float
    fold_probability: float
    opponent_count: int


@dataclass(frozen=True)
class TrainerAnswer:
    scenario: TrainerScenario
    selected_index: int
    best_index: int
    option_results: tuple[TrainerOptionResult, ...]

    @property
    def is_correct(self) -> bool:
        return self.selected_index == self.best_index


@dataclass
class PositionStats:
    attempts: int = 0
    correct: int = 0


def generate_random_scenario() -> TrainerScenario:
    """Generate a simple heads-up preflop spot where Hero faces one open raise."""
    opener_position = choice((Position.UTG, Position.HJ, Position.CO, Position.BTN, Position.SB))
    hero_position = Position.BB
    open_size = choice((2.0, 2.5, 3.0))
    hero_cards = sample(FULL_DECK, 2)
    hero_hand = HoleCards(hero_cards[0], hero_cards[1])

    table_actions: list[PlayerAction] = []
    pot_size = 1.5

    for position in POSITIONS:
        if position == hero_position:
            break

        if position == opener_position:
            amount_added = open_size
            if position == Position.SB:
                amount_added = open_size - 0.5
            table_actions.append(PlayerAction(position, Action.RAISE, amount_added))
            pot_size += amount_added
        else:
            table_actions.append(PlayerAction(position, Action.FOLD, 0.0))

    call_amount = open_size - 1.0
    options = _make_options(call_amount=call_amount, open_size=open_size)

    return TrainerScenario(
        hero_position=hero_position,
        hero_hand=hero_hand,
        opener_position=opener_position,
        open_size=open_size,
        pot_size=pot_size,
        call_amount=call_amount,
        table_actions=tuple(table_actions),
        options=options,
    )


def evaluate_trainer_answer(
    scenario: TrainerScenario,
    selected_index: int,
    simulations: int = DEFAULT_SIMULATIONS,
) -> TrainerAnswer:
    if selected_index < 0 or selected_index >= len(scenario.options):
        raise ValueError("selected_index is out of range")

    option_results = tuple(
        _evaluate_option(scenario, option, simulations)
        for option in scenario.options
    )
    best_index = max(range(len(option_results)), key=lambda index: option_results[index].ev)

    return TrainerAnswer(
        scenario=scenario,
        selected_index=selected_index,
        best_index=best_index,
        option_results=option_results,
    )


def format_scenario(scenario: TrainerScenario) -> str:
    first = card_to_string(scenario.hero_hand.card1)
    second = card_to_string(scenario.hero_hand.card2)
    lines = [
        "Preflop training scenario",
        "-------------------------",
        "6-max table, effective stack 100 BB",
    ]

    for record in scenario.table_actions:
        if record.action == Action.FOLD:
            lines.append(f"{position_to_string(record.position)} folds.")
        elif record.action == Action.RAISE:
            lines.append(f"{position_to_string(record.position)} raises to {scenario.open_size:.1f} BB.")

    lines.extend([
        f"Hero is {position_to_string(scenario.hero_position)} with {first} {second}.",
        "",
        "Choose your action:",
    ])

    for index, option in enumerate(scenario.options, start=1):
        lines.append(f"{index}. {option.label}")

    return "\n".join(lines)


def format_answer(answer: TrainerAnswer) -> str:
    selected = answer.option_results[answer.selected_index]
    best = answer.option_results[answer.best_index]
    lines = [
        "",
        "Training result",
        "---------------",
        f"Your choice: {selected.option.label}",
        f"Best choice: {best.option.label}",
        f"Result: {'correct' if answer.is_correct else 'not correct'}",
        "",
        "Chip EV comparison:",
    ]

    for index, result in enumerate(answer.option_results, start=1):
        marker = " <- best" if index - 1 == answer.best_index else ""
        equity_text = "n/a" if result.option.action == Action.FOLD else f"{result.equity:.4f}"
        lines.append(
            f"{index}. {result.option.label}: EV {result.ev:+.4f} BB, "
            f"equity {equity_text}, fold prob {result.fold_probability * 100:.2f}%"
            f"{marker}"
        )

    return "\n".join(lines)


def run_training_round(simulations: int = DEFAULT_SIMULATIONS) -> None:
    scenario = generate_random_scenario()
    print(format_scenario(scenario))

    while True:
        text = input("Your choice (1-5): ").strip()
        try:
            selected_index = int(text) - 1
        except ValueError:
            selected_index = -1

        if 0 <= selected_index < len(scenario.options):
            break

        print("Invalid choice. Please enter 1 to 5.")

    answer = evaluate_trainer_answer(scenario, selected_index, simulations)
    print(format_answer(answer))


def run_training_session(simulations: int = DEFAULT_SIMULATIONS) -> None:
    total_attempts = 0
    total_correct = 0
    position_stats = {position: PositionStats() for position in POSITIONS}

    while True:
        scenario = generate_random_scenario()
        print()
        print(format_scenario(scenario))
        selected_index = _read_choice(len(scenario.options))
        answer = evaluate_trainer_answer(scenario, selected_index, simulations)
        print(format_answer(answer))

        total_attempts += 1
        if answer.is_correct:
            total_correct += 1

        stats = position_stats[scenario.opener_position]
        stats.attempts += 1
        if answer.is_correct:
            stats.correct += 1

        if not _read_yes_no("\nPractice another hand? (y/n): "):
            break

    print(_format_session_summary(total_attempts, total_correct, position_stats))


def _make_options(call_amount: float, open_size: float) -> tuple[TrainerOption, ...]:
    return (
        TrainerOption("Fold", Action.FOLD, 0.0, 0.0, 1.0),
        TrainerOption("Call", Action.CALL, call_amount, 0.0, open_size),
        TrainerOption("Raise to 6 BB", Action.RAISE, 0.0, 5.0, 6.0),
        TrainerOption("Raise to 15 BB", Action.RAISE, 0.0, 14.0, 15.0),
        TrainerOption("All-in 100 BB", Action.RAISE, 0.0, 99.0, STACK_BB),
    )


def _evaluate_option(
    scenario: TrainerScenario,
    option: TrainerOption,
    simulations: int,
) -> TrainerOptionResult:
    fold_probability = 0.0

    if option.action == Action.FOLD:
        return TrainerOptionResult(
            option=option,
            ev=0.0,
            equity=0.0,
            fold_probability=0.0,
            opponent_count=1,
        )

    if option.action == Action.CALL:
        equity = _estimate_equity_against_opener_range(scenario, simulations)
        final_pot = scenario.pot_size + option.call_amount
        ev = equity * final_pot - option.call_amount
    else:
        equity, fold_probability = _estimate_equity_when_3bet_called(scenario, option, simulations)
        opponent_call_amount = option.total_bet - scenario.open_size
        final_pot = scenario.pot_size + option.raise_amount + opponent_call_amount
        ev = (
            fold_probability * scenario.pot_size
            + (1.0 - fold_probability) * (equity * final_pot - option.raise_amount)
        )

    return TrainerOptionResult(
        option=option,
        ev=ev,
        equity=equity,
        fold_probability=fold_probability,
        opponent_count=1,
    )


def _read_choice(option_count: int) -> int:
    while True:
        text = input(f"Your choice (1-{option_count}): ").strip()
        try:
            selected_index = int(text) - 1
        except ValueError:
            selected_index = -1

        if 0 <= selected_index < option_count:
            return selected_index

        print(f"Invalid choice. Please enter 1 to {option_count}.")


def _read_yes_no(prompt: str) -> bool:
    while True:
        text = input(prompt).strip().lower()
        if text in ("y", "yes"):
            return True
        if text in ("n", "no"):
            return False
        print("Invalid input. Please enter y or n.")


def _format_session_summary(
    total_attempts: int,
    total_correct: int,
    position_stats: dict[Position, PositionStats],
) -> str:
    accuracy = (total_correct / total_attempts * 100.0) if total_attempts else 0.0
    lines = [
        "",
        "Session summary",
        "---------------",
        f"Total accuracy: {total_correct}/{total_attempts} ({accuracy:.2f}%)",
        "",
        "Accuracy by opener position:",
    ]

    for position in POSITIONS:
        stats = position_stats[position]
        if stats.attempts == 0:
            lines.append(f"{position_to_string(position)}: no hands practiced")
            continue

        position_accuracy = stats.correct / stats.attempts * 100.0
        lines.append(
            f"{position_to_string(position)}: "
            f"{stats.correct}/{stats.attempts} ({position_accuracy:.2f}%)"
        )

    return "\n".join(lines)


def _estimate_equity_against_opener_range(scenario: TrainerScenario, simulations: int) -> float:
    candidates = _opener_range_candidates(scenario, minimum_score=None)
    return _estimate_equity_against_candidates(scenario.hero_hand, candidates, simulations)


def _estimate_equity_when_3bet_called(
    scenario: TrainerScenario,
    option: TrainerOption,
    simulations: int,
) -> tuple[float, float]:
    all_candidates = _opener_range_candidates(scenario, minimum_score=None)
    if not all_candidates:
        return 1.0, 1.0

    continue_fraction = _continue_fraction(scenario.opener_position, option.total_bet)
    continuing_candidates = _top_weighted_candidates(all_candidates, continue_fraction)
    total_weight = sum(candidate[1] for candidate in all_candidates)
    continue_weight = sum(candidate[1] for candidate in continuing_candidates)
    fold_probability = 1.0 - (continue_weight / total_weight if total_weight > 0.0 else 0.0)
    equity = _estimate_equity_against_candidates(scenario.hero_hand, continuing_candidates, simulations)
    return equity, max(0.0, min(0.98, fold_probability))


def _opener_range_candidates(
    scenario: TrainerScenario,
    minimum_score: float | None,
) -> list[tuple[HoleCards, float, float]]:
    candidates: list[tuple[HoleCards, float, float]] = []
    hero_cards = {scenario.hero_hand.card1, scenario.hero_hand.card2}

    for first_index, first in enumerate(FULL_DECK):
        if first in hero_cards:
            continue

        for second in FULL_DECK[first_index + 1:]:
            if second in hero_cards:
                continue

            opponent_hand = HoleCards(first, second)
            hand_class = get_hand_class(opponent_hand)
            frequency = get_preflop_frequency(scenario.opener_position, hand_class).open_frequency
            if frequency <= 0.0:
                continue

            score = _hand_strength_proxy(hand_class)
            if minimum_score is not None and score < minimum_score:
                continue

            candidates.append((opponent_hand, frequency, score))

    return candidates


def _top_weighted_candidates(
    candidates: list[tuple[HoleCards, float, float]],
    continue_fraction: float,
) -> list[tuple[HoleCards, float, float]]:
    target_weight = sum(candidate[1] for candidate in candidates) * continue_fraction
    selected: list[tuple[HoleCards, float, float]] = []
    running_weight = 0.0

    for candidate in sorted(candidates, key=lambda item: item[2], reverse=True):
        selected.append(candidate)
        running_weight += candidate[1]
        if running_weight >= target_weight:
            break

    return selected or candidates[:1]


def _estimate_equity_against_candidates(
    hero_hand: HoleCards,
    candidates: list[tuple[HoleCards, float, float]],
    simulations: int,
) -> float:
    if not candidates:
        return 1.0

    hands = [candidate[0] for candidate in candidates]
    weights = [candidate[1] for candidate in candidates]
    wins = 0
    ties = 0
    hero_known_cards = {hero_hand.card1, hero_hand.card2}
    simulation_count = max(1, simulations)

    for _ in range(simulation_count):
        opponent_hand = choices(hands, weights=weights, k=1)[0]
        known_cards = {
            hero_hand.card1,
            hero_hand.card2,
            opponent_hand.card1,
            opponent_hand.card2,
        }
        deck = [card for card in FULL_DECK if card not in known_cards and card not in hero_known_cards]
        board = tuple(sample(deck, BOARD_SIZE))
        hero_value = evaluate_7cards((hero_hand.card1, hero_hand.card2, *board))
        opponent_value = evaluate_7cards((opponent_hand.card1, opponent_hand.card2, *board))
        comparison = compare_hand_values(hero_value, opponent_value)

        if comparison > 0:
            wins += 1
        elif comparison == 0:
            ties += 1

    return (wins + 0.5 * ties) / simulation_count


def _hand_strength_proxy(hand_class) -> float:
    if hand_class.pair:
        return 60.0 + hand_class.high_rank * 4.0

    score = hand_class.high_rank * 4.0 + hand_class.low_rank * 2.5
    gap = hand_class.high_rank - hand_class.low_rank - 1

    if hand_class.suited:
        score += 5.0
    if gap == 0:
        score += 4.0
    elif gap == 1:
        score += 2.0
    elif gap >= 3:
        score -= gap * 2.0
    if hand_class.high_rank == int(Rank.ACE):
        score += 4.0

    return score


def _continue_fraction(opener_position: Position, total_bet: float) -> float:
    if total_bet >= STACK_BB:
        return {
            Position.UTG: 0.05,
            Position.HJ: 0.06,
            Position.CO: 0.08,
            Position.BTN: 0.10,
            Position.SB: 0.09,
        }.get(opener_position, 0.07)

    if total_bet >= 15.0:
        return {
            Position.UTG: 0.20,
            Position.HJ: 0.24,
            Position.CO: 0.30,
            Position.BTN: 0.36,
            Position.SB: 0.32,
        }.get(opener_position, 0.28)

    return {
        Position.UTG: 0.42,
        Position.HJ: 0.46,
        Position.CO: 0.52,
        Position.BTN: 0.58,
        Position.SB: 0.54,
    }.get(opener_position, 0.50)


if __name__ == "__main__":
    run_training_session()
