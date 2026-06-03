from __future__ import annotations

from dataclasses import dataclass
from random import choice, sample

from card import card_to_string
from common import Action, Card, HoleCards, Position, Rank, Suit
from range_model import position_to_string


STACK_BB = 100.0
BOARD_SIZE = 3
ROLE_AGGRESSOR = "Preflop aggressor"
ROLE_DEFENDER = "Defender"
POSITION_IP = "IP"
POSITION_OOP = "OOP"
PFA_CHECK = "check"
PFA_BET = "bet"

FULL_DECK = tuple(
    Card(rank=Rank(rank), suit=Suit(suit))
    for suit in range(int(Suit.CLUBS), int(Suit.SPADES) + 1)
    for rank in range(int(Rank.TWO), int(Rank.ACE) + 1)
)


@dataclass(frozen=True)
class FlopOption:
    label: str
    action: Action
    amount: float = 0.0


@dataclass(frozen=True)
class FlopScenario:
    hero_hand: HoleCards
    flop: tuple[Card, Card, Card]
    pot_size: float
    hero_role: str
    hero_position: str
    hero_table_position: Position
    pfa_position: Position
    defender_position: Position
    pfa_action: str
    pfa_bet_size: float
    options: tuple[FlopOption, ...]


@dataclass(frozen=True)
class FlopOptionResult:
    option: FlopOption
    score: float
    reason: str


@dataclass(frozen=True)
class FlopAnswer:
    scenario: FlopScenario
    selected_index: int
    best_index: int
    option_results: tuple[FlopOptionResult, ...]

    @property
    def is_correct(self) -> bool:
        return self.selected_index == self.best_index


@dataclass(frozen=True)
class FlopTexture:
    made_strength: int
    draw_strength: int
    high_card_strength: int
    is_suited: bool
    is_connected: bool
    summary: str


def generate_random_flop_scenario() -> FlopScenario:
    dealt = sample(FULL_DECK, 5)
    hero_hand = HoleCards(dealt[0], dealt[1])
    flop = (dealt[2], dealt[3], dealt[4])
    pot_size = choice((5.5, 6.5, 8.5, 10.5, 13.5))
    hero_role = choice((ROLE_AGGRESSOR, ROLE_DEFENDER))
    pfa_position, defender_position = _random_position_pair()
    hero_table_position = pfa_position if hero_role == ROLE_AGGRESSOR else defender_position
    villain_position = defender_position if hero_role == ROLE_AGGRESSOR else pfa_position
    hero_position = POSITION_IP if _is_in_position(hero_table_position, villain_position) else POSITION_OOP
    pfa_bet_size = round(pot_size * choice((0.33, 0.50, 0.75)), 1)

    if hero_role == ROLE_AGGRESSOR:
        pfa_action = ""
        options = _make_check_bet_options(pot_size, hero_position)
    else:
        if hero_position == POSITION_OOP:
            pfa_action = ""
            options = _make_check_bet_options(pot_size, hero_position)
        else:
            pfa_action = choice((PFA_CHECK, PFA_BET))
            options = (
                _make_check_bet_options(pot_size, hero_position)
                if pfa_action == PFA_CHECK
                else _make_facing_bet_options(pfa_bet_size, pot_size)
            )

    return FlopScenario(
        hero_hand=hero_hand,
        flop=flop,
        pot_size=pot_size,
        hero_role=hero_role,
        hero_position=hero_position,
        hero_table_position=hero_table_position,
        pfa_position=pfa_position,
        defender_position=defender_position,
        pfa_action=pfa_action,
        pfa_bet_size=pfa_bet_size,
        options=options,
    )


def evaluate_flop_answer(scenario: FlopScenario, selected_index: int) -> FlopAnswer:
    if selected_index < 0 or selected_index >= len(scenario.options):
        raise ValueError("selected_index is out of range")

    texture = _analyze_flop_texture(scenario.hero_hand, scenario.flop)
    option_results = tuple(_score_flop_option(scenario, texture, option) for option in scenario.options)
    best_index = max(range(len(option_results)), key=lambda index: option_results[index].score)

    return FlopAnswer(
        scenario=scenario,
        selected_index=selected_index,
        best_index=best_index,
        option_results=option_results,
    )


def format_flop_scenario(scenario: FlopScenario) -> str:
    first = card_to_string(scenario.hero_hand.card1)
    second = card_to_string(scenario.hero_hand.card2)
    flop_text = " ".join(card_to_string(card) for card in scenario.flop)
    lines = [
        "Flop training scenario",
        "----------------------",
        "6-max table, effective stack 100 BB",
        f"Pot: {scenario.pot_size:.1f} BB",
        f"Hero role: {scenario.hero_role}",
        f"Hero table position: {position_to_string(scenario.hero_table_position)}",
        f"PFA position: {position_to_string(scenario.pfa_position)}",
        f"Defender position: {position_to_string(scenario.defender_position)}",
        f"Hero postflop position: {scenario.hero_position}",
        f"Hero hand: {first} {second}",
        f"Flop: {flop_text}",
        "",
    ]

    if scenario.hero_role == ROLE_AGGRESSOR:
        if scenario.hero_position == POSITION_IP:
            lines.append("Defender checks to Hero.")
        else:
            lines.append("Hero is first to act as the preflop aggressor.")
    elif scenario.hero_position == POSITION_OOP:
        lines.append("Hero is the defender out of position and acts first.")
    else:
        if scenario.pfa_action == PFA_CHECK:
            lines.append("Preflop aggressor checks.")
        else:
            lines.append(f"Preflop aggressor bets {scenario.pfa_bet_size:.1f} BB.")

    lines.extend(["", "Choose your action:"])
    for index, option in enumerate(scenario.options, start=1):
        lines.append(f"{index}. {option.label}")

    return "\n".join(lines)


def format_flop_answer(answer: FlopAnswer) -> str:
    texture = _analyze_flop_texture(answer.scenario.hero_hand, answer.scenario.flop)
    selected = answer.option_results[answer.selected_index]
    best = answer.option_results[answer.best_index]
    lines = [
        "",
        "Training result",
        "---------------",
        f"Board read: {texture.summary}",
        f"Your choice: {selected.option.label}",
        f"Best choice: {best.option.label}",
        f"Result: {'correct' if answer.is_correct else 'not correct'}",
        "",
        "Option comparison:",
    ]

    for index, result in enumerate(answer.option_results, start=1):
        marker = " <- best" if index - 1 == answer.best_index else ""
        lines.append(f"{index}. {result.option.label}: score {result.score:+.2f} - {result.reason}{marker}")

    return "\n".join(lines)


def run_flop_training_session() -> None:
    total_attempts = 0
    total_correct = 0

    while True:
        scenario = generate_random_flop_scenario()
        print()
        print(format_flop_scenario(scenario))

        if not scenario.options:
            print("No decision point in this scenario.")
        else:
            selected_index = _read_choice(len(scenario.options))
            answer = evaluate_flop_answer(scenario, selected_index)
            print(format_flop_answer(answer))
            total_attempts += 1
            if answer.is_correct:
                total_correct += 1

        if not _read_yes_no("\nPractice another flop? (y/n): "):
            break

    accuracy = (total_correct / total_attempts * 100.0) if total_attempts else 0.0
    print()
    print("Session summary")
    print("---------------")
    print(f"Total accuracy: {total_correct}/{total_attempts} ({accuracy:.2f}%)")


def _make_check_bet_options(pot_size: float, hero_position: str) -> tuple[FlopOption, ...]:
    check_label = "Check back" if hero_position == POSITION_IP else "Check"
    return (
        FlopOption(check_label, Action.CHECK, 0.0),
        FlopOption(f"Bet {round(pot_size * 0.50, 1):.1f} BB", Action.RAISE, round(pot_size * 0.50, 1)),
    )


def _random_position_pair() -> tuple[Position, Position]:
    return choice((
        (Position.UTG, Position.BB),
        (Position.HJ, Position.BB),
        (Position.CO, Position.BB),
        (Position.BTN, Position.BB),
        (Position.SB, Position.BB),
        (Position.HJ, Position.CO),
        (Position.CO, Position.BTN),
        (Position.BTN, Position.SB),
    ))


def _is_in_position(hero_position: Position, villain_position: Position) -> bool:
    if hero_position == Position.BB and villain_position == Position.SB:
        return True
    if hero_position == Position.SB and villain_position == Position.BB:
        return False
    if hero_position in (Position.SB, Position.BB) and villain_position not in (Position.SB, Position.BB):
        return False
    if villain_position in (Position.SB, Position.BB) and hero_position not in (Position.SB, Position.BB):
        return True
    return hero_position > villain_position


def _make_facing_bet_options(bet_size: float, pot_size: float) -> tuple[FlopOption, ...]:
    raise_size = round(pot_size + bet_size * 3.0, 1)
    return (
        FlopOption("Fold", Action.FOLD, 0.0),
        FlopOption("Call", Action.CALL, bet_size),
        FlopOption(f"Raise to {raise_size:.1f} BB", Action.RAISE, raise_size),
    )


def _score_flop_option(scenario: FlopScenario, texture: FlopTexture, option: FlopOption) -> FlopOptionResult:
    if option.action == Action.FOLD:
        score = 0.0
        if texture.made_strength <= 1 and texture.draw_strength == 0:
            score += 2.0
        if texture.made_strength >= 3 or texture.draw_strength >= 3:
            score -= 5.0
        return FlopOptionResult(option, score, "fold is best with weak made hands and no strong draw")

    if option.action == Action.CALL:
        score = texture.made_strength * 1.4 + texture.draw_strength * 1.1 - scenario.pfa_bet_size / scenario.pot_size
        if texture.made_strength >= 5:
            score -= 1.0
        return FlopOptionResult(option, score, "call keeps medium strength and draw-heavy hands in")

    if option.action == Action.CHECK:
        score = 1.0
        if texture.made_strength <= 2:
            score += 1.5
        if texture.draw_strength >= 2:
            score += 0.5
        if texture.made_strength >= 4:
            score -= 1.0
        return FlopOptionResult(option, score, "checking controls the pot with medium or weak holdings")

    score = texture.made_strength * 1.1 + texture.draw_strength * 1.5 + texture.high_card_strength * 0.3
    if scenario.hero_position == POSITION_IP:
        score += 0.4
    if texture.made_strength <= 1 and texture.draw_strength == 0:
        score -= 2.0
    if texture.made_strength <= 2 and texture.draw_strength == 0:
        score -= 2.0
    reason = "betting or raising is preferred with value hands, strong draws, and some pressure hands"
    return FlopOptionResult(option, score, reason)


def _analyze_flop_texture(hero_hand: HoleCards, flop: tuple[Card, Card, Card]) -> FlopTexture:
    cards = (hero_hand.card1, hero_hand.card2, *flop)
    hero_ranks = (int(hero_hand.card1.rank), int(hero_hand.card2.rank))
    board_ranks = [int(card.rank) for card in flop]
    rank_counts: dict[int, int] = {}
    suit_counts: dict[Suit, int] = {}

    for card in cards:
        rank_counts[int(card.rank)] = rank_counts.get(int(card.rank), 0) + 1
        suit_counts[card.suit] = suit_counts.get(card.suit, 0) + 1

    made_strength = 0
    summary_parts: list[str] = []
    hero_pair_ranks = [rank for rank in hero_ranks if rank_counts.get(rank, 0) >= 2]
    board_high = max(board_ranks)

    if any(count >= 3 for count in rank_counts.values()):
        made_strength = 6
        summary_parts.append("trips or better")
    elif len(hero_pair_ranks) == 2 and hero_ranks[0] != hero_ranks[1]:
        made_strength = 5
        summary_parts.append("two pair")
    elif hero_ranks[0] == hero_ranks[1] and hero_ranks[0] > board_high:
        made_strength = 4
        summary_parts.append("overpair")
    elif hero_pair_ranks:
        best_pair = max(hero_pair_ranks)
        if best_pair >= board_high:
            made_strength = 3
            summary_parts.append("top pair")
        else:
            made_strength = 2
            summary_parts.append("pair")
    elif max(hero_ranks) > board_high:
        made_strength = 1
        summary_parts.append("overcards")
    else:
        summary_parts.append("air")

    flush_draw = any(count >= 4 for count in suit_counts.values())
    straight_draw = _has_straight_draw([int(card.rank) for card in cards])
    draw_strength = 0
    if flush_draw:
        draw_strength += 2
        summary_parts.append("flush draw")
    if straight_draw:
        draw_strength += 2
        summary_parts.append("straight draw")
    if flush_draw and straight_draw:
        draw_strength += 1
        summary_parts.append("combo draw")

    high_card_strength = sum(1 for rank in hero_ranks if rank >= int(Rank.JACK))
    is_suited = len(set(card.suit for card in flop)) <= 2
    is_connected = max(board_ranks) - min(board_ranks) <= 4

    return FlopTexture(
        made_strength=made_strength,
        draw_strength=draw_strength,
        high_card_strength=high_card_strength,
        is_suited=is_suited,
        is_connected=is_connected,
        summary=", ".join(summary_parts),
    )


def _has_straight_draw(ranks: list[int]) -> bool:
    unique = set(ranks)
    if int(Rank.ACE) in unique:
        unique.add(1)

    for start in range(1, 11):
        window = set(range(start, start + 5))
        if len(unique & window) >= 4:
            return True

    return False


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


if __name__ == "__main__":
    run_flop_training_session()
