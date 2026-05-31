from __future__ import annotations

from card import parse_hole_cards
from common import HoleCards, Position
from range_model import opening_range_summary, position_to_string
from solver import SolverInput, SolverResult, action_to_string, solve_preflop_decision


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

    return SolverInput(
        hero_position=_read_position(),
        hero_hand=_read_hole_cards(),
        pot_size=_read_float_min("Current pot size: ", 0.0),
        call_amount=_read_float_min("Call amount: ", 0.0),
        raise_amount=_read_float_min("Raise amount: ", 0.0),
        simulations=_read_int_range("Simulation count (1-1000000): ", 1, 1_000_000),
    )


def print_solver_result(result: SolverResult) -> None:
    print("\nResult")
    print("------")
    print(f"Hero position: {position_to_string(result.hero_position)}")
    print(f"Players behind: {result.opponent_count}")
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
    print(f"EV call:     {result.ev_call:.4f}")
    print(f"EV raise:    {result.ev_raise:.4f}")
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
    print("Players before hero are treated as folded.")
    print("Players behind hero are derived from position: BTN has SB and BB only.")
    print("Pot size, call amount, and raise amount cannot be negative.")
    print("Fold probability is estimated automatically from opponent EV versus hero open range.")
    print_opening_ranges()


def print_opening_ranges() -> None:
    print("\nPosition opening range model")
    print("----------------------------")
    for pos in (Position.UTG, Position.HJ, Position.CO, Position.BTN, Position.SB, Position.BB):
        print(f"{position_to_string(pos)}: {opening_range_summary(pos)}")
