from __future__ import annotations

from dataclasses import dataclass
from random import choice, sample

from card import card_to_string
from common import Action, Card, HoleCards, PlayerAction, Position, Rank, Suit
from equity import EquityInput, estimate_preflop_equity
from range_model import position_to_string


POSITIONS = (Position.UTG, Position.HJ, Position.CO, Position.BTN, Position.SB, Position.BB)
STACK_BB = 100.0
DEFAULT_SIMULATIONS = 5000

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

    equity = estimate_preflop_equity(
        EquityInput(
            hero_hand=scenario.hero_hand,
            opponent_count=1,
            simulations=simulations,
        )
    ).equity
    option_results = tuple(
        _evaluate_option(scenario, option, equity)
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
        f"{position_to_string(scenario.opener_position)} raises to {scenario.open_size:.1f} BB.",
    ]

    for record in scenario.table_actions:
        if record.action == Action.FOLD:
            lines.append(f"{position_to_string(record.position)} folds.")

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
        lines.append(
            f"{index}. {result.option.label}: EV {result.ev:+.4f} BB, "
            f"equity {result.equity:.4f}, fold prob {result.fold_probability * 100:.2f}%"
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
    equity: float,
) -> TrainerOptionResult:
    if option.action == Action.FOLD:
        return TrainerOptionResult(
            option=option,
            ev=0.0,
            equity=equity,
            fold_probability=0.0,
            opponent_count=1,
        )

    if option.action == Action.CALL:
        final_pot = scenario.pot_size + option.call_amount
        ev = equity * final_pot - option.call_amount
        fold_probability = 0.0
    else:
        fold_probability = _estimate_3bet_fold_probability(scenario, option)
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


def _estimate_3bet_fold_probability(scenario: TrainerScenario, option: TrainerOption) -> float:
    if option.total_bet <= scenario.open_size:
        return 0.0

    size_ratio = option.total_bet / scenario.open_size
    base_by_position = {
        Position.UTG: 0.34,
        Position.HJ: 0.39,
        Position.CO: 0.45,
        Position.BTN: 0.50,
        Position.SB: 0.47,
    }
    base = base_by_position.get(scenario.opener_position, 0.42)
    size_bonus = min(0.30, max(0.0, (size_ratio - 3.0) * 0.08))

    if option.total_bet >= STACK_BB:
        return 0.68

    return max(0.05, min(0.80, base + size_bonus))


if __name__ == "__main__":
    run_training_round()
