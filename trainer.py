from __future__ import annotations

from dataclasses import dataclass
from random import choices, choice, sample

from card import BOARD_SIZE, FULL_DECK, card_to_string
from common import TABLE_POSITIONS, Action, Card, HoleCards, PlayerAction, Position, Rank
from poker_eval import compare_hand_values, evaluate_7cards
from range_model import (
    get_hand_class,
    get_preflop_frequency,
    players_behind_count,
    position_to_string,
    three_bet_call_suitability,
    three_bet_raise_suitability,
)


POSITIONS = TABLE_POSITIONS
HERO_POSITIONS = TABLE_POSITIONS
STACK_BB = 100.0
DEFAULT_SIMULATIONS = 5000
SCENARIO_OPEN_FIRST = "open_first"
SCENARIO_FACING_OPEN = "facing_open"
SCENARIO_FACING_3BET = "facing_3bet"
SCENARIO_FACING_4BET = "facing_4bet"

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
    scenario_type: str = SCENARIO_FACING_OPEN
    three_bettor_position: Position = Position.INVALID
    three_bet_size: float = 0.0
    four_bettor_position: Position = Position.INVALID
    four_bet_size: float = 0.0


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


def generate_random_scenario(scenario_type_filter: str | None = None) -> TrainerScenario:
    """Generate a random preflop training spot."""
    scenario_type = scenario_type_filter
    if scenario_type == SCENARIO_OPEN_FIRST:
        hero_position = choice((Position.UTG, Position.HJ, Position.CO, Position.BTN, Position.SB))
    elif scenario_type == SCENARIO_FACING_OPEN:
        hero_position = choice((Position.HJ, Position.CO, Position.BTN, Position.SB, Position.BB))
    elif scenario_type == SCENARIO_FACING_3BET:
        hero_position = choice((Position.UTG, Position.HJ, Position.CO, Position.BTN, Position.SB))
    elif scenario_type == SCENARIO_FACING_4BET:
        hero_position = choice((Position.HJ, Position.CO, Position.BTN, Position.SB, Position.BB))
    else:
        hero_position = choice(HERO_POSITIONS)
        possible_scenario_types = [SCENARIO_OPEN_FIRST if hero_position == Position.UTG else SCENARIO_FACING_OPEN]
        if hero_position != Position.BB:
            possible_scenario_types.append(SCENARIO_FACING_3BET)
        if hero_position != Position.UTG:
            possible_scenario_types.append(SCENARIO_FACING_4BET)
        scenario_type = choice(possible_scenario_types)

    hero_contribution = _starting_contribution(hero_position)
    hero_hand = _generate_hero_hand_for_scenario(hero_position, scenario_type)

    if scenario_type == SCENARIO_OPEN_FIRST:
        prior_folds = tuple(
            PlayerAction(position, Action.FOLD, 0.0)
            for position in POSITIONS
            if position < hero_position
        )
        return TrainerScenario(
            hero_position=hero_position,
            hero_hand=hero_hand,
            opener_position=Position.INVALID,
            open_size=0.0,
            pot_size=1.5,
            call_amount=0.0,
            table_actions=prior_folds,
            options=_make_open_first_options(hero_contribution),
            scenario_type=SCENARIO_OPEN_FIRST,
        )

    if scenario_type == SCENARIO_FACING_3BET:
        return _generate_facing_3bet_scenario(hero_position, hero_hand, hero_contribution)

    if scenario_type == SCENARIO_FACING_4BET:
        return _generate_facing_4bet_scenario(hero_position, hero_hand, hero_contribution)

    opener_position = choice(tuple(position for position in POSITIONS if position < hero_position))
    open_size = 3.5 if opener_position == Position.SB and hero_position == Position.BB else choice((2.0, 2.5, 3.0))

    table_actions: list[PlayerAction] = []
    pot_size = 1.5

    for position in POSITIONS:
        if position == hero_position:
            break

        if position == opener_position:
            amount_added = open_size
            if position == Position.SB:
                amount_added = open_size - 0.5
            table_actions.append(PlayerAction(position, Action.RAISE, open_size))
            pot_size += amount_added
        else:
            table_actions.append(PlayerAction(position, Action.FOLD, 0.0))

    call_amount = open_size - hero_contribution
    options = _make_options(
        call_amount=call_amount,
        open_size=open_size,
        hero_contribution=hero_contribution,
    )

    return TrainerScenario(
        hero_position=hero_position,
        hero_hand=hero_hand,
        opener_position=opener_position,
        open_size=open_size,
        pot_size=pot_size,
        call_amount=call_amount,
        table_actions=tuple(table_actions),
        options=options,
        scenario_type=SCENARIO_FACING_OPEN,
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

    raise_counts: dict[Position, int] = {}
    for record in scenario.table_actions:
        if record.action == Action.FOLD:
            lines.append(f"{position_to_string(record.position)} folds.")
        elif record.action == Action.RAISE:
            raise_counts[record.position] = raise_counts.get(record.position, 0) + 1
            if _is_facing_4bet_scenario(scenario) and record.position == scenario.hero_position:
                lines.append(f"Hero 3-bets to {scenario.three_bet_size:.1f} BB.")
            elif _is_facing_4bet_scenario(scenario) and record.position == scenario.four_bettor_position:
                if raise_counts[record.position] >= 2:
                    lines.append(f"{position_to_string(record.position)} 4-bets to {scenario.four_bet_size:.1f} BB.")
                else:
                    lines.append(f"{position_to_string(record.position)} raises to {scenario.open_size:.1f} BB.")
            elif _is_facing_3bet_scenario(scenario) and record.position == scenario.hero_position:
                lines.append(f"Hero opens to {scenario.open_size:.1f} BB.")
            elif _is_facing_3bet_scenario(scenario) and record.position == scenario.three_bettor_position:
                lines.append(f"{position_to_string(record.position)} 3-bets to {scenario.three_bet_size:.1f} BB.")
            else:
                lines.append(f"{position_to_string(record.position)} raises to {scenario.open_size:.1f} BB.")

    if _is_open_first_scenario(scenario):
        lines.append("Hero is first to act.")

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
    scenario_type_filter = _read_training_mode()
    total_attempts = 0
    total_correct = 0
    position_stats = {position: PositionStats() for position in HERO_POSITIONS}

    while True:
        scenario = generate_random_scenario(scenario_type_filter)
        print()
        print(format_scenario(scenario))
        selected_index = _read_choice(len(scenario.options))
        answer = evaluate_trainer_answer(scenario, selected_index, simulations)
        print(format_answer(answer))

        total_attempts += 1
        if answer.is_correct:
            total_correct += 1

        stats = position_stats[scenario.hero_position]
        stats.attempts += 1
        if answer.is_correct:
            stats.correct += 1

        if not _read_yes_no("\nPractice another hand? (y/n): "):
            break

    print(_format_session_summary(total_attempts, total_correct, position_stats))


def _read_training_mode() -> str | None:
    print()
    print("Preflop training mode")
    print("---------------------")
    print("1. Random preflop spots")
    print("2. Facing an open raise")
    print("3. Facing a 3-bet")
    print("4. Facing a 4-bet")

    choice = _read_choice(4)
    return {
        0: None,
        1: SCENARIO_FACING_OPEN,
        2: SCENARIO_FACING_3BET,
        3: SCENARIO_FACING_4BET,
    }[choice]


def _make_options(call_amount: float, open_size: float, hero_contribution: float) -> tuple[TrainerOption, ...]:
    return (
        TrainerOption("Fold", Action.FOLD, 0.0, 0.0, hero_contribution),
        TrainerOption("Call", Action.CALL, call_amount, 0.0, open_size),
        TrainerOption("Raise to 6 BB", Action.RAISE, 0.0, 6.0 - hero_contribution, 6.0),
        TrainerOption("Raise to 15 BB", Action.RAISE, 0.0, 15.0 - hero_contribution, 15.0),
        TrainerOption("All-in 100 BB", Action.RAISE, 0.0, STACK_BB - hero_contribution, STACK_BB),
    )


def _make_open_first_options(hero_contribution: float) -> tuple[TrainerOption, ...]:
    return (
        TrainerOption("Fold", Action.FOLD, 0.0, 0.0, hero_contribution),
        TrainerOption("Raise to 2 BB", Action.RAISE, 0.0, 2.0 - hero_contribution, 2.0),
        TrainerOption("Raise to 2.5 BB", Action.RAISE, 0.0, 2.5 - hero_contribution, 2.5),
        TrainerOption("Raise to 3 BB", Action.RAISE, 0.0, 3.0 - hero_contribution, 3.0),
        TrainerOption("All-in 100 BB", Action.RAISE, 0.0, STACK_BB - hero_contribution, STACK_BB),
    )


def _make_facing_3bet_options(call_amount: float, three_bet_size: float, hero_open_size: float) -> tuple[TrainerOption, ...]:
    return (
        TrainerOption("Fold", Action.FOLD, 0.0, 0.0, hero_open_size),
        TrainerOption("Call", Action.CALL, call_amount, 0.0, three_bet_size),
        TrainerOption("4-bet to 22 BB", Action.RAISE, 0.0, 22.0 - hero_open_size, 22.0),
        TrainerOption("4-bet to 35 BB", Action.RAISE, 0.0, 35.0 - hero_open_size, 35.0),
        TrainerOption("All-in 100 BB", Action.RAISE, 0.0, STACK_BB - hero_open_size, STACK_BB),
    )


def _generate_facing_3bet_scenario(
    hero_position: Position,
    hero_hand: HoleCards,
    hero_contribution: float,
) -> TrainerScenario:
    open_size = 3.5 if hero_position == Position.SB else choice((2.0, 2.5, 3.0))
    possible_three_bettors = tuple(position for position in POSITIONS if position > hero_position)
    three_bettor_position = choice(possible_three_bettors)
    three_bet_size = _three_bet_size(open_size, three_bettor_position)
    table_actions: list[PlayerAction] = []
    pot_size = 1.5

    three_bet_seen = False
    for position in POSITIONS:
        if position == hero_position:
            amount_added = open_size - hero_contribution
            table_actions.append(PlayerAction(position, Action.RAISE, open_size))
            pot_size += amount_added
        elif position == three_bettor_position:
            amount_added = three_bet_size - _starting_contribution(position)
            table_actions.append(PlayerAction(position, Action.RAISE, three_bet_size))
            pot_size += amount_added
            three_bet_seen = True
        else:
            table_actions.append(PlayerAction(position, Action.FOLD, 0.0))
        if three_bet_seen and position == Position.BB:
            break

    call_amount = three_bet_size - open_size
    return TrainerScenario(
        hero_position=hero_position,
        hero_hand=hero_hand,
        opener_position=hero_position,
        open_size=open_size,
        pot_size=pot_size,
        call_amount=call_amount,
        table_actions=tuple(table_actions),
        options=_make_facing_3bet_options(call_amount, three_bet_size, open_size),
        scenario_type=SCENARIO_FACING_3BET,
        three_bettor_position=three_bettor_position,
        three_bet_size=three_bet_size,
    )


def _three_bet_size(open_size: float, three_bettor_position: Position) -> float:
    if three_bettor_position in (Position.SB, Position.BB):
        return min(STACK_BB, round(open_size * choice((3.8, 4.0, 4.5)), 1))
    return min(STACK_BB, round(open_size * choice((3.0, 3.2, 3.5)), 1))


def _make_facing_4bet_options(call_amount: float, four_bet_size: float, hero_three_bet_size: float) -> tuple[TrainerOption, ...]:
    return (
        TrainerOption("Fold", Action.FOLD, 0.0, 0.0, hero_three_bet_size),
        TrainerOption("Call", Action.CALL, call_amount, 0.0, four_bet_size),
        TrainerOption("5-bet to 55 BB", Action.RAISE, 0.0, 55.0 - hero_three_bet_size, 55.0),
        TrainerOption("5-bet to 75 BB", Action.RAISE, 0.0, 75.0 - hero_three_bet_size, 75.0),
        TrainerOption("All-in 100 BB", Action.RAISE, 0.0, STACK_BB - hero_three_bet_size, STACK_BB),
    )


def _generate_facing_4bet_scenario(
    hero_position: Position,
    hero_hand: HoleCards,
    hero_contribution: float,
) -> TrainerScenario:
    possible_openers = tuple(position for position in POSITIONS if position < hero_position)
    opener_position = choice(possible_openers)
    hero_hand = _generate_hero_hand_for_facing_4bet(hero_position, opener_position)
    open_size = choice((2.0, 2.5, 3.0))
    three_bet_size = _three_bet_size(open_size, hero_position)
    four_bet_size = min(STACK_BB, round(three_bet_size * choice((2.2, 2.4, 2.6)), 1))
    table_actions: list[PlayerAction] = []
    pot_size = 1.5

    for position in POSITIONS:
        if position == opener_position:
            amount_added = open_size - _starting_contribution(position)
            table_actions.append(PlayerAction(position, Action.RAISE, open_size))
            pot_size += amount_added
        elif position == hero_position:
            amount_added = three_bet_size - hero_contribution
            table_actions.append(PlayerAction(position, Action.RAISE, three_bet_size))
            pot_size += amount_added
        else:
            table_actions.append(PlayerAction(position, Action.FOLD, 0.0))

    opener_extra = four_bet_size - open_size
    table_actions.append(PlayerAction(opener_position, Action.RAISE, four_bet_size))
    pot_size += opener_extra
    call_amount = four_bet_size - three_bet_size

    return TrainerScenario(
        hero_position=hero_position,
        hero_hand=hero_hand,
        opener_position=opener_position,
        open_size=open_size,
        pot_size=pot_size,
        call_amount=call_amount,
        table_actions=tuple(table_actions),
        options=_make_facing_4bet_options(call_amount, four_bet_size, three_bet_size),
        scenario_type=SCENARIO_FACING_4BET,
        three_bettor_position=hero_position,
        three_bet_size=three_bet_size,
        four_bettor_position=opener_position,
        four_bet_size=four_bet_size,
    )


def _generate_hero_hand_for_scenario(hero_position: Position, scenario_type: str) -> HoleCards:
    if scenario_type not in (SCENARIO_FACING_3BET, SCENARIO_FACING_4BET):
        hero_cards = sample(FULL_DECK, 2)
        return HoleCards(hero_cards[0], hero_cards[1])

    candidates: list[tuple[HoleCards, float]] = []
    for first_index, first in enumerate(FULL_DECK):
        for second in FULL_DECK[first_index + 1:]:
            hand = HoleCards(first, second)
            hand_class = get_hand_class(hand)
            frequency = get_preflop_frequency(hero_position, hand_class).open_frequency
            if frequency > 0.0:
                candidates.append((hand, frequency))

    hands = [candidate[0] for candidate in candidates]
    weights = [candidate[1] for candidate in candidates]
    return choices(hands, weights=weights, k=1)[0]


def _generate_hero_hand_for_facing_4bet(hero_position: Position, opener_position: Position) -> HoleCards:
    candidates: list[tuple[HoleCards, float]] = []

    for first_index, first in enumerate(FULL_DECK):
        for second in FULL_DECK[first_index + 1:]:
            hand = HoleCards(first, second)
            hand_class = get_hand_class(hand)
            frequency = get_preflop_frequency(hero_position, hand_class).open_frequency
            weight = _three_bet_candidate_weight(hand_class, opener_position, frequency)
            if weight > 0.0:
                candidates.append((hand, weight))

    hands = [candidate[0] for candidate in candidates]
    weights = [candidate[1] for candidate in candidates]
    return choices(hands, weights=weights, k=1)[0]


def _three_bet_candidate_weight(hand_class, opener_position: Position, open_frequency: float) -> float:
    if open_frequency <= 0.0:
        return 0.0

    if hand_class.pair:
        if hand_class.high_rank >= int(Rank.QUEEN):
            return open_frequency * 4.0
        if hand_class.high_rank >= int(Rank.TEN):
            return open_frequency * 1.2
        return 0.0

    if hand_class.high_rank == int(Rank.ACE) and hand_class.low_rank >= int(Rank.KING):
        return open_frequency * 4.0

    if not hand_class.suited:
        if hand_class.high_rank == int(Rank.ACE) and hand_class.low_rank >= int(Rank.QUEEN):
            return open_frequency * 1.2
        return 0.0

    if hand_class.high_rank == int(Rank.ACE) and hand_class.low_rank >= int(Rank.FIVE):
        return open_frequency * 2.0
    if hand_class.high_rank == int(Rank.KING) and hand_class.low_rank >= int(Rank.TEN):
        return open_frequency * 1.5
    if opener_position >= Position.CO and hand_class.high_rank >= int(Rank.NINE):
        return open_frequency * 0.8

    return 0.0


def _evaluate_option(
    scenario: TrainerScenario,
    option: TrainerOption,
    simulations: int,
) -> TrainerOptionResult:
    if _is_open_first_scenario(scenario):
        return _evaluate_open_first_option(scenario, option, simulations)
    if _is_facing_3bet_scenario(scenario):
        return _evaluate_facing_3bet_option(scenario, option, simulations)
    if _is_facing_4bet_scenario(scenario):
        return _evaluate_facing_4bet_option(scenario, option, simulations)

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
        realization = _equity_realization(scenario, option)
        final_pot = scenario.pot_size + option.call_amount
        ev = equity * realization * final_pot - option.call_amount
    else:
        equity, fold_probability = _estimate_equity_when_3bet_called(scenario, option, simulations)
        realization = _equity_realization(scenario, option)
        opponent_call_amount = option.total_bet - scenario.open_size
        final_pot = scenario.pot_size + option.raise_amount + opponent_call_amount
        ev = (
            fold_probability * scenario.pot_size
            + (1.0 - fold_probability) * (equity * realization * final_pot - option.raise_amount)
        )
        ev -= _three_bet_strategy_penalty(scenario, option)

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
        "Accuracy by hero position:",
    ]

    for position in HERO_POSITIONS:
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


def _starting_contribution(position: Position) -> float:
    if position == Position.SB:
        return 0.5
    if position == Position.BB:
        return 1.0
    return 0.0


def _is_open_first_scenario(scenario: TrainerScenario) -> bool:
    return scenario.opener_position == Position.INVALID


def _is_facing_3bet_scenario(scenario: TrainerScenario) -> bool:
    return scenario.scenario_type == SCENARIO_FACING_3BET


def _is_facing_4bet_scenario(scenario: TrainerScenario) -> bool:
    return scenario.scenario_type == SCENARIO_FACING_4BET


def _evaluate_facing_3bet_option(
    scenario: TrainerScenario,
    option: TrainerOption,
    simulations: int,
) -> TrainerOptionResult:
    if option.action == Action.FOLD:
        return TrainerOptionResult(
            option=option,
            ev=0.0,
            equity=0.0,
            fold_probability=0.0,
            opponent_count=1,
        )

    if option.action == Action.CALL:
        candidates = _three_bet_range_candidates(scenario)
        equity = _estimate_equity_against_candidates(scenario.hero_hand, candidates, simulations)
        realization = _three_bet_call_realization(scenario, option)
        final_pot = scenario.pot_size + option.call_amount
        ev = equity * realization * final_pot - option.call_amount
        ev += _three_bet_call_playability_bonus(scenario)
        return TrainerOptionResult(
            option=option,
            ev=ev,
            equity=equity,
            fold_probability=0.0,
            opponent_count=1,
        )

    candidates = _four_bet_continue_candidates(scenario, option)
    equity = _estimate_equity_against_candidates(scenario.hero_hand, candidates, simulations)
    fold_probability = _estimate_four_bet_fold_probability(scenario, option)
    opponent_call_amount = option.total_bet - scenario.three_bet_size
    final_pot = scenario.pot_size + option.raise_amount + opponent_call_amount
    ev = (
        fold_probability * scenario.pot_size
        + (1.0 - fold_probability) * (equity * final_pot - option.raise_amount)
    )
    ev += _three_bet_raise_playability_bonus(scenario)
    ev -= _four_bet_strategy_penalty(scenario, option)

    return TrainerOptionResult(
        option=option,
        ev=ev,
        equity=equity,
        fold_probability=fold_probability,
        opponent_count=1,
    )


def _evaluate_facing_4bet_option(
    scenario: TrainerScenario,
    option: TrainerOption,
    simulations: int,
) -> TrainerOptionResult:
    if option.action == Action.FOLD:
        return TrainerOptionResult(
            option=option,
            ev=0.0,
            equity=0.0,
            fold_probability=0.0,
            opponent_count=1,
        )

    if option.action == Action.CALL:
        candidates = _four_bet_range_candidates(scenario)
        equity = _estimate_equity_against_candidates(scenario.hero_hand, candidates, simulations)
        realization = max(0.35, _equity_realization(scenario, option) - 0.06)
        final_pot = scenario.pot_size + option.call_amount
        ev = equity * realization * final_pot - option.call_amount
        return TrainerOptionResult(
            option=option,
            ev=ev,
            equity=equity,
            fold_probability=0.0,
            opponent_count=1,
        )

    candidates = _five_bet_continue_candidates(scenario, option)
    equity = _estimate_equity_against_candidates(scenario.hero_hand, candidates, simulations)
    fold_probability = _estimate_five_bet_fold_probability(scenario, option)
    opponent_call_amount = option.total_bet - scenario.four_bet_size
    final_pot = scenario.pot_size + option.raise_amount + opponent_call_amount
    ev = (
        fold_probability * scenario.pot_size
        + (1.0 - fold_probability) * (equity * final_pot - option.raise_amount)
    )
    ev -= _five_bet_strategy_penalty(scenario, option)

    return TrainerOptionResult(
        option=option,
        ev=ev,
        equity=equity,
        fold_probability=fold_probability,
        opponent_count=1,
    )


def _evaluate_open_first_option(
    scenario: TrainerScenario,
    option: TrainerOption,
    simulations: int,
) -> TrainerOptionResult:
    if option.action == Action.FOLD:
        return TrainerOptionResult(
            option=option,
            ev=0.0,
            equity=0.0,
            fold_probability=0.0,
            opponent_count=players_behind_count(scenario.hero_position),
        )

    hand_class = get_hand_class(scenario.hero_hand)
    open_frequency = get_preflop_frequency(scenario.hero_position, hand_class).open_frequency
    fold_probability = _estimate_open_first_fold_probability(scenario, option, open_frequency)
    candidates = _open_first_continue_candidates(scenario, option)
    equity = _estimate_equity_against_candidates(scenario.hero_hand, candidates, simulations)
    realization = _equity_realization(scenario, option)
    caller_contribution = option.total_bet
    final_pot = scenario.pot_size + option.raise_amount + caller_contribution
    chip_ev = (
        fold_probability * scenario.pot_size
        + (1.0 - fold_probability) * (equity * realization * final_pot - option.raise_amount)
    )
    range_penalty = (1.0 - open_frequency) * option.raise_amount * 0.45
    if option.total_bet >= STACK_BB:
        range_penalty += option.raise_amount * 0.08
    ev = chip_ev - range_penalty

    return TrainerOptionResult(
        option=option,
        ev=ev,
        equity=equity,
        fold_probability=fold_probability,
        opponent_count=players_behind_count(scenario.hero_position),
    )


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
    fold_probability = _adjust_3bet_fold_probability(scenario, option, fold_probability)
    equity = _estimate_equity_against_candidates(scenario.hero_hand, continuing_candidates, simulations)
    return equity, max(0.0, min(0.98, fold_probability))


def _estimate_open_first_fold_probability(
    scenario: TrainerScenario,
    option: TrainerOption,
    open_frequency: float,
) -> float:
    hand_class = get_hand_class(scenario.hero_hand)

    if option.total_bet >= STACK_BB:
        single_opponent_fold = 0.95
    else:
        single_opponent_fold = {
            2.0: 0.80,
            2.5: 0.78,
            3.0: 0.75,
        }.get(option.total_bet, 0.77)

    if open_frequency <= 0.0:
        single_opponent_fold -= 0.04
    elif open_frequency >= 0.75:
        single_opponent_fold += 0.01

    if hand_class.high_rank == int(Rank.ACE):
        single_opponent_fold += 0.02
    elif hand_class.high_rank == int(Rank.KING):
        single_opponent_fold += 0.01

    single_opponent_fold = max(0.05, min(0.98, single_opponent_fold))
    return single_opponent_fold ** max(1, players_behind_count(scenario.hero_position))


def _three_bet_range_candidates(scenario: TrainerScenario) -> list[tuple[HoleCards, float, float]]:
    raw_candidates = _position_range_candidates(
        position=scenario.three_bettor_position,
        hero_hand=scenario.hero_hand,
    )
    candidates = [
        (
            hand,
            weight,
            three_bet_raise_suitability(
                get_hand_class(hand),
                scenario.opener_position,
                scenario.three_bettor_position,
            ),
        )
        for hand, weight, _score in raw_candidates
    ]
    continue_fraction = {
        Position.HJ: 0.22,
        Position.CO: 0.26,
        Position.BTN: 0.32,
        Position.SB: 0.30,
        Position.BB: 0.34,
    }.get(scenario.three_bettor_position, 0.28)
    return _top_weighted_candidates(candidates, continue_fraction)


def _four_bet_continue_candidates(
    scenario: TrainerScenario,
    option: TrainerOption,
) -> list[tuple[HoleCards, float, float]]:
    candidates = _three_bet_range_candidates(scenario)
    continue_fraction = 0.18 if option.total_bet < STACK_BB else 0.12
    if scenario.three_bettor_position in (Position.SB, Position.BB):
        continue_fraction += 0.03
    return _top_weighted_candidates(candidates, continue_fraction)


def _estimate_four_bet_fold_probability(
    scenario: TrainerScenario,
    option: TrainerOption,
) -> float:
    base = 0.58 if option.total_bet < STACK_BB else 0.76
    hand_class = get_hand_class(scenario.hero_hand)
    raise_score = three_bet_raise_suitability(
        hand_class,
        scenario.opener_position,
        scenario.three_bettor_position,
    )

    if hand_class.high_rank == int(Rank.ACE):
        base += 0.07
        if hand_class.suited and hand_class.low_rank <= int(Rank.FIVE):
            base += 0.05
    elif hand_class.high_rank == int(Rank.KING):
        base += 0.03
        if hand_class.low_rank >= int(Rank.QUEEN):
            base -= 0.14
    elif hand_class.high_rank < int(Rank.QUEEN):
        base -= 0.16
    elif hand_class.high_rank == int(Rank.QUEEN):
        base -= 0.08

    if hand_class.pair:
        if hand_class.high_rank >= int(Rank.TEN):
            base += 0.02
        else:
            base -= 0.18
    elif hand_class.high_rank != int(Rank.ACE) and hand_class.low_rank < int(Rank.QUEEN):
        base -= 0.08
    if raise_score >= 82.0:
        base += 0.04
    elif raise_score < 62.0:
        base -= 0.06

    if scenario.hero_position in (Position.UTG, Position.HJ) and scenario.three_bettor_position in (Position.SB, Position.BB):
        base -= 0.08

    return max(0.05, min(0.92, base))


def _four_bet_strategy_penalty(scenario: TrainerScenario, option: TrainerOption) -> float:
    hand_class = get_hand_class(scenario.hero_hand)
    frequency = get_preflop_frequency(scenario.hero_position, hand_class).open_frequency
    penalty = (1.0 - frequency) * option.raise_amount * 0.30

    if option.total_bet >= STACK_BB:
        penalty += option.raise_amount * 0.05
    if hand_class.high_rank < int(Rank.QUEEN) and not hand_class.suited:
        penalty += option.raise_amount * 0.06
    if hand_class.pair and hand_class.high_rank < int(Rank.TEN):
        penalty += option.raise_amount * 0.14
    if scenario.hero_position in (Position.UTG, Position.HJ) and scenario.three_bettor_position in (Position.SB, Position.BB):
        penalty += option.raise_amount * 0.04

    return penalty


def _four_bet_range_candidates(scenario: TrainerScenario) -> list[tuple[HoleCards, float, float]]:
    candidates = _position_range_candidates(
        position=scenario.four_bettor_position,
        hero_hand=scenario.hero_hand,
    )
    continue_fraction = {
        Position.UTG: 0.18,
        Position.HJ: 0.20,
        Position.CO: 0.24,
        Position.BTN: 0.28,
        Position.SB: 0.26,
    }.get(scenario.four_bettor_position, 0.22)
    return _top_weighted_candidates(candidates, continue_fraction)


def _five_bet_continue_candidates(
    scenario: TrainerScenario,
    option: TrainerOption,
) -> list[tuple[HoleCards, float, float]]:
    candidates = _four_bet_range_candidates(scenario)
    continue_fraction = 0.22 if option.total_bet < STACK_BB else 0.16
    return _top_weighted_candidates(candidates, continue_fraction)


def _estimate_five_bet_fold_probability(
    scenario: TrainerScenario,
    option: TrainerOption,
) -> float:
    base = 0.42 if option.total_bet < STACK_BB else 0.58
    hand_class = get_hand_class(scenario.hero_hand)

    if hand_class.high_rank == int(Rank.ACE):
        base += 0.05
    elif hand_class.high_rank == int(Rank.KING):
        base += 0.03 if hand_class.suited or hand_class.low_rank >= int(Rank.QUEEN) else -0.06
    elif hand_class.high_rank < int(Rank.QUEEN):
        base -= 0.10

    if not hand_class.suited and not hand_class.pair and hand_class.low_rank < int(Rank.QUEEN):
        base -= 0.12

    if hand_class.pair and hand_class.high_rank >= int(Rank.QUEEN):
        base += 0.03

    return max(0.03, min(0.80, base))


def _five_bet_strategy_penalty(scenario: TrainerScenario, option: TrainerOption) -> float:
    hand_class = get_hand_class(scenario.hero_hand)
    frequency = get_preflop_frequency(scenario.hero_position, hand_class).open_frequency
    penalty = (1.0 - frequency) * option.raise_amount * 0.25

    if option.total_bet >= STACK_BB:
        penalty += option.raise_amount * 0.04
    if hand_class.high_rank < int(Rank.KING) and not (hand_class.pair and hand_class.high_rank >= int(Rank.JACK)):
        penalty += option.raise_amount * 0.05
    if not hand_class.suited and not hand_class.pair and hand_class.low_rank < int(Rank.QUEEN):
        penalty += option.raise_amount * 0.12

    return penalty


def _position_range_candidates(
    position: Position,
    hero_hand: HoleCards,
) -> list[tuple[HoleCards, float, float]]:
    candidates: list[tuple[HoleCards, float, float]] = []
    hero_cards = {hero_hand.card1, hero_hand.card2}

    for first_index, first in enumerate(FULL_DECK):
        if first in hero_cards:
            continue

        for second in FULL_DECK[first_index + 1:]:
            if second in hero_cards:
                continue

            hand = HoleCards(first, second)
            hand_class = get_hand_class(hand)
            frequency = get_preflop_frequency(position, hand_class).open_frequency
            if frequency <= 0.0:
                continue

            candidates.append((hand, frequency, _hand_strength_proxy(hand_class)))

    return candidates


def _open_first_continue_candidates(
    scenario: TrainerScenario,
    option: TrainerOption,
) -> list[tuple[HoleCards, float, float]]:
    all_candidates: list[tuple[HoleCards, float, float]] = []
    hero_cards = {scenario.hero_hand.card1, scenario.hero_hand.card2}

    for defender_position in POSITIONS:
        if defender_position <= scenario.hero_position:
            continue

        defender_candidates: list[tuple[HoleCards, float, float]] = []
        for first_index, first in enumerate(FULL_DECK):
            if first in hero_cards:
                continue

            for second in FULL_DECK[first_index + 1:]:
                if second in hero_cards:
                    continue

                hand = HoleCards(first, second)
                hand_class = get_hand_class(hand)
                frequency = get_preflop_frequency(defender_position, hand_class).open_frequency
                if frequency <= 0.0:
                    continue

                defender_candidates.append((hand, frequency, _hand_strength_proxy(hand_class)))

        continue_fraction = _open_first_continue_fraction(defender_position, option.total_bet)
        all_candidates.extend(_top_weighted_candidates(defender_candidates, continue_fraction))

    return all_candidates


def _open_first_continue_fraction(defender_position: Position, total_bet: float) -> float:
    if total_bet >= STACK_BB:
        return {
            Position.HJ: 0.05,
            Position.CO: 0.06,
            Position.BTN: 0.08,
            Position.SB: 0.07,
            Position.BB: 0.08,
        }.get(defender_position, 0.07)

    base = {
        Position.HJ: 0.20,
        Position.CO: 0.24,
        Position.BTN: 0.32,
        Position.SB: 0.28,
        Position.BB: 0.36,
    }.get(defender_position, 0.25)
    if total_bet <= 2.0:
        base += 0.06
    elif total_bet >= 3.0:
        base -= 0.04

    return max(0.05, min(0.70, base))


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


def _equity_realization(scenario: TrainerScenario, option: TrainerOption) -> float:
    if option.total_bet >= STACK_BB:
        return 1.0

    hand_class = get_hand_class(scenario.hero_hand)
    realization = 0.50
    gap = hand_class.high_rank - hand_class.low_rank - 1

    if hand_class.pair:
        realization += 0.18
    if hand_class.suited:
        realization += 0.15
    if hand_class.high_rank == int(Rank.ACE):
        realization += 0.12
    elif hand_class.high_rank == int(Rank.KING):
        realization += 0.08
    elif hand_class.high_rank >= int(Rank.QUEEN):
        realization += 0.08
    elif hand_class.high_rank >= int(Rank.TEN):
        realization += 0.05
    if hand_class.low_rank >= int(Rank.EIGHT):
        realization += 0.04

    if gap <= 1 and not hand_class.pair:
        realization += 0.06
    elif gap >= 4:
        realization -= 0.06

    opener_bonus = {
        Position.UTG: 0.00,
        Position.HJ: 0.02,
        Position.CO: 0.04,
        Position.BTN: 0.06,
        Position.SB: 0.08,
    }.get(scenario.opener_position, 0.0)

    hero_position_bonus = {
        Position.HJ: 0.01,
        Position.CO: 0.04,
        Position.BTN: 0.08,
        Position.SB: -0.08,
    }.get(scenario.hero_position, 0.0)
    if scenario.hero_position == Position.BB:
        hero_position_bonus = 0.06 if scenario.opener_position == Position.SB else -0.02

    realization += opener_bonus + hero_position_bonus

    if option.action == Action.RAISE:
        realization += 0.04

    return max(0.42, min(0.92, realization))


def _three_bet_call_realization(scenario: TrainerScenario, option: TrainerOption) -> float:
    hand_class = get_hand_class(scenario.hero_hand)
    call_score = three_bet_call_suitability(
        hand_class,
        scenario.opener_position,
        scenario.three_bettor_position,
    )
    realization = _equity_realization(scenario, option)
    realization += max(-0.04, min(0.12, (call_score - 55.0) / 120.0))
    if hand_class.suited and not hand_class.pair:
        realization += 0.03
    if hand_class.suited and max(0, hand_class.high_rank - hand_class.low_rank - 1) <= 1:
        realization += 0.03
    if scenario.hero_position not in (Position.SB, Position.BB):
        realization += 0.03
    return max(0.42, min(0.98, realization))


def _three_bet_call_playability_bonus(scenario: TrainerScenario) -> float:
    hand_class = get_hand_class(scenario.hero_hand)
    call_score = three_bet_call_suitability(
        hand_class,
        scenario.opener_position,
        scenario.three_bettor_position,
    )
    bonus = max(0.0, call_score - 54.0) * 0.030
    if hand_class.suited and not hand_class.pair:
        bonus += 0.18
    if hand_class.suited and max(0, hand_class.high_rank - hand_class.low_rank - 1) <= 1:
        bonus += 0.75
    if hand_class.high_rank == int(Rank.ACE) and hand_class.suited:
        bonus += 0.16
    return min(1.45, bonus)


def _three_bet_raise_playability_bonus(scenario: TrainerScenario) -> float:
    hand_class = get_hand_class(scenario.hero_hand)
    raise_score = three_bet_raise_suitability(
        hand_class,
        scenario.opener_position,
        scenario.three_bettor_position,
    )
    bonus = max(0.0, raise_score - 70.0) * 0.018
    if hand_class.high_rank == int(Rank.ACE):
        bonus += 0.12
    if hand_class.high_rank == int(Rank.ACE) and hand_class.suited and hand_class.low_rank <= int(Rank.FIVE):
        bonus += 0.18
    if hand_class.pair and hand_class.high_rank >= int(Rank.QUEEN):
        bonus += 0.16
    return min(0.85, bonus)


def _adjust_3bet_fold_probability(
    scenario: TrainerScenario,
    option: TrainerOption,
    fold_probability: float,
) -> float:
    hand_class = get_hand_class(scenario.hero_hand)
    adjustment = 0.0

    if hand_class.high_rank == int(Rank.ACE):
        adjustment += 0.05
    elif hand_class.high_rank == int(Rank.KING):
        adjustment += 0.03
    elif scenario.opener_position in (Position.UTG, Position.HJ):
        adjustment -= 0.12

    if option.total_bet >= 15.0 and hand_class.high_rank < int(Rank.QUEEN):
        adjustment -= 0.08
    if option.total_bet >= STACK_BB and hand_class.high_rank < int(Rank.ACE):
        adjustment -= 0.12

    if hand_class.pair and hand_class.high_rank >= int(Rank.TEN):
        adjustment += 0.03

    return max(0.0, min(0.98, fold_probability + adjustment))


def _three_bet_strategy_penalty(scenario: TrainerScenario, option: TrainerOption) -> float:
    hand_class = get_hand_class(scenario.hero_hand)
    frequency = get_preflop_frequency(scenario.hero_position, hand_class).open_frequency
    raise_score = three_bet_raise_suitability(
        hand_class,
        scenario.opener_position,
        scenario.three_bettor_position,
    )
    penalty = (1.0 - frequency) * option.raise_amount * 0.10

    if option.total_bet >= STACK_BB:
        penalty += option.raise_amount * 0.05
    if hand_class.high_rank < int(Rank.QUEEN) and not hand_class.pair and raise_score < 70.0:
        penalty += option.raise_amount * 0.02
    if (
        hand_class.high_rank == int(Rank.ACE)
        and hand_class.suited
        and hand_class.low_rank <= int(Rank.FIVE)
    ):
        penalty -= option.raise_amount * 0.04
    if hand_class.pair and hand_class.high_rank >= int(Rank.QUEEN):
        penalty -= option.raise_amount * 0.03

    return max(0.0, penalty)


def _continue_fraction(opener_position: Position, total_bet: float) -> float:
    if total_bet >= STACK_BB:
        return {
            Position.UTG: 0.08,
            Position.HJ: 0.10,
            Position.CO: 0.12,
            Position.BTN: 0.15,
            Position.SB: 0.14,
        }.get(opener_position, 0.11)

    if total_bet >= 15.0:
        return {
            Position.UTG: 0.36,
            Position.HJ: 0.40,
            Position.CO: 0.46,
            Position.BTN: 0.52,
            Position.SB: 0.48,
        }.get(opener_position, 0.44)

    return {
        Position.UTG: 0.90,
        Position.HJ: 0.87,
        Position.CO: 0.84,
        Position.BTN: 0.80,
        Position.SB: 0.82,
    }.get(opener_position, 0.84)


if __name__ == "__main__":
    run_training_session()
