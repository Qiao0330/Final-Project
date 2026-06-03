from __future__ import annotations

from dataclasses import dataclass

from card import parse_hole_cards
from common import Action, HoleCards, PlayerAction, Position
from range_model import opening_range_summary, position_to_string
from solver import SolverInput, SolverResult, action_to_string, solve_preflop_decision


POSITIONS = (Position.UTG, Position.HJ, Position.CO, Position.BTN, Position.SB, Position.BB)


@dataclass(frozen=True)
class HeroDecisionContext:
    pot_size: float
    call_amount: float
    raise_amount: float
    table_actions_before_decision: tuple[PlayerAction, ...]
    active_opponent_count: int


def _active_opponent_count(hero_position: Position, folded: set[Position]) -> int:
    return len([
        position for position in POSITIONS
        if position != hero_position and position not in folded
    ])


def _read_int_range(prompt: str, minimum: int, maximum: int) -> int:
    while True:
        text = input(prompt).strip()
        try:
            value = int(text)
        except ValueError:
            value = minimum - 1

        if minimum <= value <= maximum:
            return value

        print(f"Invalid input. Please enter an integer from {minimum} to {maximum}.")


def _read_float_min(prompt: str, minimum: float) -> float:
    while True:
        text = input(prompt).strip()
        try:
            value = float(text)
        except ValueError:
            value = minimum - 1.0

        if value >= minimum:
            return value

        print(f"Invalid input. Please enter a number greater than or equal to {minimum:.2f}.")


def _read_hole_cards() -> HoleCards:
    while True:
        first = input("Hero first card  (example Ah): ").strip()
        second = input("Hero second card (example Ks): ").strip()
        hand = parse_hole_cards(first, second)

        if hand is not None:
            return hand

        print("Invalid cards. Use rank-suit format like Ah, Ks, Tc. Duplicates and 10h are invalid.")


def _read_position() -> Position:
    print("\nHero position")
    print("1. UTG")
    print("2. HJ")
    print("3. CO")
    print("4. BTN")
    print("5. SB")
    print("6. BB")

    choice = _read_int_range("Choose hero position: ", 1, 6)
    return Position(choice - 1)


def _read_any_position(prompt: str) -> Position:
    print("1. UTG  2. HJ  3. CO  4. BTN  5. SB  6. BB")
    choice = _read_int_range(prompt, 1, 6)
    return Position(choice - 1)


def _read_action_record(position: Position) -> PlayerAction:
    print(f"\nAction for {position_to_string(position)}")
    print("1. Fold")
    print("2. Call")
    print("3. Raise")
    print("4. Check")
    choice = _read_int_range("Choose action: ", 1, 4)
    action = {
        1: Action.FOLD,
        2: Action.CALL,
        3: Action.RAISE,
        4: Action.CHECK,
    }[choice]
    amount = 0.0
    if action in (Action.CALL, Action.RAISE):
        amount = _read_float_min("Amount added in BB: ", 0.0)
    return PlayerAction(position=position, action=action, amount=amount)


def _read_action_history() -> tuple[PlayerAction, ...]:
    count = _read_int_range("Number of prior action records (0-30): ", 0, 30)
    records: list[PlayerAction] = []
    for index in range(count):
        print(f"\nPrior action {index + 1}")
        position = _read_any_position("Choose acting position: ")
        records.append(_read_action_record(position))
    return tuple(records)


def _read_candidate_raise_amounts() -> tuple[float, ...]:
    print("\nCandidate raise sizes")
    print("Enter the amount Hero would invest for each raise option.")
    print("Use 0 to skip raise analysis for this spot.")
    count = _read_int_range("Number of raise sizes to compare (0-5): ", 0, 5)
    values: list[float] = []
    for index in range(count):
        amount = _read_float_min(f"Raise option {index + 1} amount in BB: ", 0.01)
        values.append(amount)
    return tuple(values)


def _read_player_action(position: Position, to_call: float) -> Action:
    print(f"\n{position_to_string(position)} action")
    if to_call > 0.0:
        print(f"To call: {to_call:.2f} BB")
        print("1. Fold")
        print("2. Call")
        print("3. Raise")

        choice = _read_int_range("Choose action: ", 1, 3)
        return {
            1: Action.FOLD,
            2: Action.CALL,
            3: Action.RAISE,
        }[choice]

    print("1. Check")
    print("2. Raise")

    choice = _read_int_range("Choose action: ", 1, 2)
    return {
        1: Action.CHECK,
        2: Action.RAISE,
    }[choice]


def _read_raise_total(position: Position, current_bet: float, current_contribution: float) -> float:
    while True:
        total = _read_float_min(
            f"New total bet for {position_to_string(position)} after raise: ",
            0.0,
        )
        if total > current_bet and total >= current_contribution:
            return total

        print(f"Invalid raise. Total bet must be greater than current bet {current_bet:.2f}.")


def _active_positions(folded: set[Position]) -> list[Position]:
    return [position for position in POSITIONS if position not in folded]


def _betting_is_closed(folded: set[Position], contributions: dict[Position, float], current_bet: float, acted: set[Position]) -> bool:
    active = _active_positions(folded)
    if len(active) <= 1:
        return True

    return all(
        contributions[position] == current_bet and position in acted
        for position in active
    )


def _next_position_index(index: int) -> int:
    return (index + 1) % len(POSITIONS)


def _print_table_state(pot_size: float, current_bet: float, contributions: dict[Position, float], folded: set[Position]) -> None:
    print("\nCurrent table state")
    print("-------------------")
    print(f"Pot: {pot_size:.2f} BB")
    print(f"Current bet to match: {current_bet:.2f} BB")
    for position in POSITIONS:
        state = "folded" if position in folded else "active"
        print(f"  {position_to_string(position)}: {contributions[position]:.2f} BB ({state})")


def _print_action_summary(records: list[PlayerAction]) -> None:
    print("\nCompleted preflop action summary")
    print("--------------------------------")
    if not records:
        print("No voluntary actions entered.")
        return

    for record in records:
        amount = ""
        if record.amount > 0.0:
            prefix = "+" if record.action == Action.RAISE else ""
            amount = f" {prefix}{record.amount:.2f}"
        print(f"  {position_to_string(record.position)} {action_to_string(record.action)}{amount}")


def _read_complete_preflop_actions(hero_position: Position) -> tuple[HeroDecisionContext, tuple[PlayerAction, ...]]:
    contributions = {position: 0.0 for position in POSITIONS}
    folded: set[Position] = set()
    acted: set[Position] = set()
    records: list[PlayerAction] = []

    contributions[Position.SB] = 0.5
    contributions[Position.BB] = 1.0
    pot_size = 1.5
    current_bet = 1.0
    last_hero_context: HeroDecisionContext | None = None
    last_hero_pot_size = 0.0
    last_hero_call_amount = 0.0
    last_hero_raise_amount = 0.0

    print("\nBlinds posted automatically")
    print("---------------------------")
    print("SB posts 0.50 BB")
    print("BB posts 1.00 BB")

    index = 0
    while not _betting_is_closed(folded, contributions, current_bet, acted):
        position = POSITIONS[index]

        if position in folded:
            index = _next_position_index(index)
            continue

        if contributions[position] == current_bet and position in acted:
            index = _next_position_index(index)
            continue

        _print_table_state(pot_size, current_bet, contributions, folded)
        to_call = max(0.0, current_bet - contributions[position])

        if position == hero_position:
            print(f"\nHero decision point at {position_to_string(hero_position)}.")
            last_hero_pot_size = pot_size
            last_hero_call_amount = to_call
            last_hero_raise_amount = 0.0

        action = _read_player_action(position, to_call)
        amount_added = 0.0

        if action == Action.FOLD:
            folded.add(position)
        elif action in (Action.CALL, Action.CHECK):
            amount_added = to_call
            contributions[position] += amount_added
            pot_size += amount_added
        elif action == Action.RAISE:
            new_total = _read_raise_total(position, current_bet, contributions[position])
            amount_added = new_total - contributions[position]
            contributions[position] = new_total
            pot_size += amount_added
            current_bet = new_total
            acted = set()
            if position == hero_position:
                last_hero_raise_amount = amount_added

        acted.add(position)
        records.append(PlayerAction(position=position, action=action, amount=amount_added))
        if position == hero_position:
            last_hero_context = HeroDecisionContext(
                pot_size=last_hero_pot_size,
                call_amount=last_hero_call_amount,
                raise_amount=last_hero_raise_amount,
                table_actions_before_decision=tuple(records),
                active_opponent_count=_active_opponent_count(hero_position, folded),
            )
        index = _next_position_index(index)

    if last_hero_context is None:
        to_call = max(0.0, current_bet - contributions[hero_position])
        last_hero_context = HeroDecisionContext(
            pot_size=pot_size,
            call_amount=to_call,
            raise_amount=0.0,
            table_actions_before_decision=tuple(records),
            active_opponent_count=_active_opponent_count(hero_position, folded),
        )

    _print_action_summary(records)
    return HeroDecisionContext(
        pot_size=last_hero_context.pot_size,
        call_amount=last_hero_context.call_amount,
        raise_amount=last_hero_context.raise_amount,
        table_actions_before_decision=tuple(records),
        active_opponent_count=_active_opponent_count(hero_position, folded),
    ), tuple(records)


def run_main_menu() -> None:
    while True:
        print()
        print("============================================")
        print("Texas Hold'em Preflop Decision System")
        print("============================================")
        print("1. New analysis")
        print("2. Input guide")
        print("3. Exit")

        choice = _read_int_range("Choose an option: ", 1, 3)

        if choice == 1:
            solver_input = read_solver_input()
            result = solve_preflop_decision(solver_input)
            print_solver_result(result)
        elif choice == 2:
            print_input_guide()
        else:
            return


def read_solver_input() -> SolverInput:
    print("\nNew decision analysis")
    print("---------------------")

    hero_position = _read_position()
    hero_hand = _read_hole_cards()
    print("\nCurrent decision point")
    pot_size = _read_float_min("Current pot size in BB: ", 0.0)
    call_amount = _read_float_min("Amount Hero must call in BB (0 if check is available): ", 0.0)
    candidate_raise_amounts = _read_candidate_raise_amounts()
    active_opponent_count = _read_int_range("Active opponent count (0-5): ", 0, 5)
    table_actions = _read_action_history()
    simulations = _read_int_range("Simulation count (1-1000000): ", 1, 1_000_000)
    primary_raise_amount = candidate_raise_amounts[0] if candidate_raise_amounts else 0.0

    return SolverInput(
        hero_position=hero_position,
        hero_hand=hero_hand,
        pot_size=pot_size,
        call_amount=call_amount,
        raise_amount=primary_raise_amount,
        simulations=simulations,
        table_actions=table_actions,
        active_opponent_count=active_opponent_count,
        candidate_raise_amounts=candidate_raise_amounts,
    )


def print_solver_result(result: SolverResult) -> None:
    print("\nResult")
    print("------")
    print(f"Hero position: {position_to_string(result.hero_position)}")
    if result.table_actions:
        print("Entered actions:")
        for record in result.table_actions:
            print(
                f"  {position_to_string(record.position)} "
                f"{action_to_string(record.action)}"
                f"{f' +{record.amount:.2f}' if record.amount > 0.0 and record.action == Action.RAISE else ''}"
                f"{f' {record.amount:.2f}' if record.amount > 0.0 and record.action != Action.RAISE else ''}"
            )
    else:
        print("Entered actions: none")
    print(f"Estimated opponents: {result.opponent_count}")
    print(f"Hand class:    {result.hand_class.name}")
    print(f"In open range: {'yes' if result.range_frequency.open_frequency > 0.0 else 'no'}")
    print(f"Open freq:     {result.range_frequency.open_frequency * 100:.0f}%")
    print(f"Call freq:     {result.range_frequency.call_frequency * 100:.0f}%")
    print(f"Raise freq:    {result.range_frequency.raise_frequency * 100:.0f}%")
    print(f"Auto fold prob: {result.fold_probability * 100:.2f}%")
    print()
    print(f"Simulations: {result.equity_result.simulations}")
    print(f"Wins:        {result.equity_result.wins} ({result.equity_result.win_rate * 100:.2f}%)")
    print(f"Ties:        {result.equity_result.ties} ({result.equity_result.tie_rate * 100:.2f}%)")
    print(f"Losses:      {result.equity_result.losses} ({result.equity_result.loss_rate * 100:.2f}%)")
    print(f"Equity:      {result.equity:.4f}")
    print()
    print(f"EV fold:     {result.ev_fold:.4f}")
    print(f"EV check:    {result.ev_check:.4f}")
    print(f"EV call:     {result.ev_call:.4f}")
    print(f"EV raise:    {result.ev_raise:.4f}"
          f"{f' at {result.best_raise_amount:.2f} BB' if result.best_raise_amount > 0.0 else ''}")
    print("Action EVs:")
    for action_ev in result.action_evs:
        amount = f" {action_ev.amount:.2f} BB" if action_ev.amount > 0.0 else ""
        print(f"  {action_to_string(action_ev.action)}{amount}: {action_ev.ev:+.4f}")
    print()
    print(f"Recommendation: {action_to_string(result.recommendation)}")
    print(f"Explanation:    {result.explanation}")


def print_input_guide() -> None:
    print("\nInput guide")
    print("-----------")
    print("Card format: rank followed by suit.")
    print("Ranks: 2 3 4 5 6 7 8 9 T J Q K A")
    print("Suits: c=clubs, d=diamonds, h=hearts, s=spades")
    print("Valid examples: Ah, Ks, Qd, Tc, 7c")
    print("Invalid examples: 10h, Kx, ZZ, duplicated cards like Ah Ah")
    print()
    print("In a new analysis, enter Hero position and cards first.")
    print("Then enter the current pot, call amount, candidate raise sizes, active opponents, and prior actions.")
    print("Use call amount 0 when Hero can check. The solver will compare check against raise options.")
    print_opening_ranges()


def print_opening_ranges() -> None:
    print("\nPosition opening range model")
    print("----------------------------")
    for pos in (Position.UTG, Position.HJ, Position.CO, Position.BTN, Position.SB, Position.BB):
        print(f"{position_to_string(pos)}: {opening_range_summary(pos)}")
