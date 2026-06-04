from __future__ import annotations

from dataclasses import dataclass
from random import choice, sample

from card import FULL_DECK, card_to_string
from common import Action, Card, HoleCards, Position, Rank, Suit
from range_model import get_hand_class, get_preflop_frequency, position_to_string


STACK_BB = 100.0
BOARD_SIZE = 3
ROLE_AGGRESSOR = "Preflop aggressor"
ROLE_DEFENDER = "Defender"
POSITION_IP = "IP"
POSITION_OOP = "OOP"
PFA_CHECK = "check"
PFA_BET = "bet"
POT_SINGLE_RAISED = "Single-raised pot"
POT_3BET = "3-bet pot"
POT_4BET = "4-bet pot"
POT_5BET = "5-bet pot"

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
    opponent_position: Position
    pfa_position: Position
    defender_position: Position
    pot_type: str
    preflop_summary: str
    remaining_stack: float
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
    backdoor_flush: bool
    backdoor_straight: bool
    is_suited: bool
    is_connected: bool
    summary: str


def generate_random_flop_scenario() -> FlopScenario:
    pot_type, pot_size, remaining_stack = _random_pot_setup()
    hero_role = choice((ROLE_AGGRESSOR, ROLE_DEFENDER))
    pfa_position, defender_position = _random_position_pair()
    hero_table_position = pfa_position if hero_role == ROLE_AGGRESSOR else defender_position
    villain_position = defender_position if hero_role == ROLE_AGGRESSOR else pfa_position
    hero_hand = _generate_hand_for_pot_type(pot_type, hero_role, hero_table_position)
    available_board = [card for card in FULL_DECK if card not in (hero_hand.card1, hero_hand.card2)]
    flop_cards = sample(available_board, BOARD_SIZE)
    flop = (flop_cards[0], flop_cards[1], flop_cards[2])
    preflop_summary = _make_preflop_summary(
        pot_type,
        hero_role,
        hero_table_position,
        villain_position,
    )
    hero_position = POSITION_IP if _is_in_position(hero_table_position, villain_position) else POSITION_OOP
    pfa_bet_size = round(pot_size * choice((0.33, 0.50, 0.75)), 1)

    if hero_role == ROLE_AGGRESSOR:
        pfa_action = ""
        options = _make_check_bet_options(pot_size, hero_position, remaining_stack)
    else:
        if hero_position == POSITION_OOP:
            pfa_action = choice((PFA_CHECK, PFA_BET))
            options = (
                ()
                if pfa_action == PFA_CHECK
                else _make_facing_bet_options(pfa_bet_size, pot_size, remaining_stack)
            )
        else:
            pfa_action = choice((PFA_CHECK, PFA_BET))
            options = (
                _make_check_bet_options(pot_size, hero_position, remaining_stack)
                if pfa_action == PFA_CHECK
                else _make_facing_bet_options(pfa_bet_size, pot_size, remaining_stack)
            )

    return FlopScenario(
        hero_hand=hero_hand,
        flop=flop,
        pot_size=pot_size,
        hero_role=hero_role,
        hero_position=hero_position,
        hero_table_position=hero_table_position,
        opponent_position=villain_position,
        pfa_position=pfa_position,
        defender_position=defender_position,
        pot_type=pot_type,
        preflop_summary=preflop_summary,
        remaining_stack=remaining_stack,
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
        f"Pot type: {scenario.pot_type}",
        f"Pot: {scenario.pot_size:.1f} BB",
        f"Hero: {position_to_string(scenario.hero_table_position)}",
        f"Opponent: {position_to_string(scenario.opponent_position)}",
        f"Preflop: {scenario.preflop_summary}",
        f"Hero hand: {first} {second}",
        f"Flop: {flop_text}",
        "",
    ]

    if scenario.hero_role == ROLE_AGGRESSOR:
        if scenario.hero_position == POSITION_IP:
            lines.append("Opponent checks to Hero.")
        else:
            lines.append("Hero is first to act.")
    elif scenario.hero_position == POSITION_OOP:
        lines.append("Hero checks.")
        if scenario.pfa_action == PFA_CHECK:
            lines.append("Opponent checks back. The hand goes to the turn.")
        else:
            lines.append(f"Opponent bets {scenario.pfa_bet_size:.1f} BB.")
    else:
        if scenario.pfa_action == PFA_CHECK:
            lines.append("Opponent checks.")
        else:
            lines.append(f"Opponent bets {scenario.pfa_bet_size:.1f} BB.")

    if scenario.options:
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
        f"Suggested betting structure: {_betting_strategy(answer.scenario, texture)}",
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


def _make_check_bet_options(
    pot_size: float,
    hero_position: str,
    remaining_stack: float,
) -> tuple[FlopOption, ...]:
    check_label = "Check back" if hero_position == POSITION_IP else "Check"
    options = [FlopOption(check_label, Action.CHECK, 0.0)]
    seen_amounts: set[float] = set()

    for fraction, fraction_label in (
        (0.25, "1/4 pot"),
        (1.0 / 3.0, "1/3 pot"),
        (0.50, "1/2 pot"),
        (0.75, "3/4 pot"),
        (1.25, "125% pot overbet"),
        (1.50, "150% pot overbet"),
    ):
        amount = min(remaining_stack, round(pot_size * fraction, 1))
        if amount in seen_amounts:
            continue
        seen_amounts.add(amount)
        capped = "all-in, " if amount < round(pot_size * fraction, 1) else ""
        options.append(FlopOption(f"Bet {amount:.1f} BB ({capped}{fraction_label})", Action.RAISE, amount))

    return tuple(options)


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


def _random_pot_setup() -> tuple[str, float, float]:
    pot_type = choice((POT_SINGLE_RAISED, POT_3BET, POT_4BET, POT_5BET))
    return {
        POT_SINGLE_RAISED: (pot_type, choice((5.5, 6.5, 8.5)), 96.0),
        POT_3BET: (pot_type, choice((18.5, 21.5, 24.5)), 88.0),
        POT_4BET: (pot_type, choice((42.0, 48.0, 55.0)), 74.0),
        POT_5BET: (pot_type, choice((72.0, 80.0, 90.0)), 52.0),
    }[pot_type]


def _generate_hand_for_pot_type(
    pot_type: str,
    hero_role: str,
    hero_position: Position,
) -> HoleCards:
    while True:
        cards = sample(FULL_DECK, 2)
        hand = HoleCards(cards[0], cards[1])
        hand_class = get_hand_class(hand)
        open_frequency = get_preflop_frequency(hero_position, hand_class).open_frequency

        if pot_type == POT_SINGLE_RAISED and hero_role == ROLE_AGGRESSOR and open_frequency > 0.0:
            return hand
        if pot_type == POT_SINGLE_RAISED and hero_role == ROLE_DEFENDER and _is_reasonable_calling_hand(hand_class):
            return hand
        if pot_type == POT_3BET and _is_reasonable_3bet_pot_hand(hand_class):
            return hand
        if pot_type == POT_4BET and _is_reasonable_4bet_pot_hand(hand_class):
            return hand
        if pot_type == POT_5BET and _is_reasonable_5bet_pot_hand(hand_class, hero_role):
            return hand


def _is_reasonable_calling_hand(hand_class) -> bool:
    if hand_class.pair:
        return True
    if hand_class.suited and hand_class.high_rank >= int(Rank.SEVEN):
        return True
    if hand_class.high_rank == int(Rank.ACE):
        return True
    return hand_class.high_rank >= int(Rank.TEN) and hand_class.low_rank >= int(Rank.EIGHT)


def _is_reasonable_3bet_pot_hand(hand_class) -> bool:
    if hand_class.pair and hand_class.high_rank >= int(Rank.SEVEN):
        return True
    if hand_class.high_rank == int(Rank.ACE) and hand_class.low_rank >= int(Rank.TEN):
        return True
    if hand_class.suited and hand_class.high_rank >= int(Rank.NINE):
        return True
    return hand_class.suited and hand_class.high_rank == int(Rank.ACE) and hand_class.low_rank >= int(Rank.FIVE)


def _is_reasonable_4bet_pot_hand(hand_class) -> bool:
    if hand_class.pair and hand_class.high_rank >= int(Rank.TEN):
        return True
    if hand_class.high_rank == int(Rank.ACE) and hand_class.low_rank >= int(Rank.QUEEN):
        return True
    return hand_class.suited and hand_class.high_rank == int(Rank.ACE) and hand_class.low_rank >= int(Rank.FIVE)


def _is_reasonable_5bet_pot_hand(hand_class, hero_role: str) -> bool:
    if hand_class.pair and hand_class.high_rank >= int(Rank.QUEEN):
        return True
    if hand_class.high_rank == int(Rank.ACE) and hand_class.low_rank >= int(Rank.KING):
        return True
    return hero_role == ROLE_DEFENDER and hand_class.pair and hand_class.high_rank == int(Rank.JACK)


def _make_preflop_summary(
    pot_type: str,
    hero_role: str,
    hero_position: Position,
    opponent_position: Position,
) -> str:
    hero = f"Hero {position_to_string(hero_position)}"
    opponent = position_to_string(opponent_position)

    if hero_role == ROLE_AGGRESSOR:
        return {
            POT_SINGLE_RAISED: f"{hero} opens, {opponent} calls",
            POT_3BET: f"{hero} is the 3-bettor, {opponent} calls",
            POT_4BET: f"{hero} is the 4-bettor, {opponent} calls",
            POT_5BET: f"{hero} is the 5-bettor, {opponent} calls",
        }[pot_type]

    return {
        POT_SINGLE_RAISED: f"{opponent} opens, {hero} calls",
        POT_3BET: f"{opponent} is the 3-bettor, {hero} calls",
        POT_4BET: f"{opponent} is the 4-bettor, {hero} calls",
        POT_5BET: f"{opponent} is the 5-bettor, {hero} calls",
    }[pot_type]


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


def _make_facing_bet_options(
    bet_size: float,
    pot_size: float,
    remaining_stack: float,
) -> tuple[FlopOption, ...]:
    small_raise = min(remaining_stack, round(bet_size * 2.5, 1))
    large_raise = min(remaining_stack, round(bet_size * 3.5, 1))
    options = [
        FlopOption("Fold", Action.FOLD, 0.0),
        FlopOption("Call", Action.CALL, bet_size),
        FlopOption(f"Raise to {small_raise:.1f} BB (2.5x bet)", Action.RAISE, small_raise),
    ]
    if large_raise != small_raise:
        options.append(FlopOption(f"Raise to {large_raise:.1f} BB (3.5x bet)", Action.RAISE, large_raise))
    return tuple(options)


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

    size_ratio = option.amount / scenario.pot_size
    strategy = _betting_strategy(scenario, texture)
    premium_value = texture.made_strength >= 5
    strong_value = texture.made_strength >= 4
    quality_bluff = (
        texture.made_strength <= 1
        and (
            texture.draw_strength >= 2
            or texture.backdoor_flush
            or texture.backdoor_straight
        )
    )

    if strategy == "polarized":
        if premium_value:
            score += 2.5 - abs(size_ratio - 1.25)
        elif strong_value or quality_bluff:
            score += 1.8 - abs(size_ratio - 0.75)
        else:
            score -= 1.8 + max(0.0, size_ratio - 0.50) * 2.0
    else:
        if strong_value:
            score += 1.8 - abs(size_ratio - 0.50)
        elif texture.draw_strength >= 2:
            score += 1.4 - abs(size_ratio - 0.50)
        elif texture.made_strength == 3:
            score += 1.0 - abs(size_ratio - 1.0 / 3.0)
        elif quality_bluff:
            score += 0.9 - abs(size_ratio - 0.25)
        else:
            score -= 1.0 + max(0.0, size_ratio - 0.50)

    if _has_range_bet_advantage(scenario):
        if size_ratio <= 1.0 / 3.0:
            if quality_bluff:
                score += 5.8 - abs(size_ratio - 1.0 / 3.0) * 2.0
            else:
                score += 2.0
        elif size_ratio <= 0.50:
            score += 2.5 if quality_bluff else 0.8
        elif texture.made_strength < 4:
            score -= 1.5

    if size_ratio > 1.0 and not (premium_value or quality_bluff):
        score -= 3.0

    reason = (
        f"{strategy} sizing: large bets favor premium value and quality bluffs; "
        "small and medium bets support a wider linear range"
    )
    return FlopOptionResult(option, score, reason)


def _betting_strategy(scenario: FlopScenario, texture: FlopTexture) -> str:
    if scenario.pot_type in (POT_4BET, POT_5BET):
        return "linear"
    if _has_range_bet_advantage(scenario):
        return "linear"
    if texture.is_connected or _is_monotone_board(scenario.flop):
        return "polarized"
    return "linear"


def _has_range_bet_advantage(scenario: FlopScenario) -> bool:
    if scenario.hero_role != ROLE_AGGRESSOR:
        return False

    board_ranks = sorted((int(card.rank) for card in scenario.flop), reverse=True)
    high_card = board_ranks[0]
    rank_span = high_card - board_ranks[-1]
    paired = len(set(board_ranks)) < 3

    return high_card >= int(Rank.KING) and (rank_span >= 5 or paired)


def _is_monotone_board(flop: tuple[Card, Card, Card]) -> bool:
    return len({card.suit for card in flop}) == 1


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
    backdoor_flush = not flush_draw and _has_backdoor_flush(hero_hand, flop)
    backdoor_straight = not straight_draw and _has_backdoor_straight(hero_hand, flop)
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
    if backdoor_flush:
        summary_parts.append("backdoor flush draw")
    if backdoor_straight:
        summary_parts.append("backdoor straight draw")

    high_card_strength = sum(1 for rank in hero_ranks if rank >= int(Rank.JACK))
    is_suited = len(set(card.suit for card in flop)) <= 2
    is_connected = max(board_ranks) - min(board_ranks) <= 4

    return FlopTexture(
        made_strength=made_strength,
        draw_strength=draw_strength,
        high_card_strength=high_card_strength,
        backdoor_flush=backdoor_flush,
        backdoor_straight=backdoor_straight,
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


def _has_backdoor_flush(hero_hand: HoleCards, flop: tuple[Card, Card, Card]) -> bool:
    all_cards = (hero_hand.card1, hero_hand.card2, *flop)
    for suit in (Suit.CLUBS, Suit.DIAMONDS, Suit.HEARTS, Suit.SPADES):
        suited_cards = [card for card in all_cards if card.suit == suit]
        hero_has_suit = hero_hand.card1.suit == suit or hero_hand.card2.suit == suit
        if len(suited_cards) == 3 and hero_has_suit:
            return True
    return False


def _has_backdoor_straight(hero_hand: HoleCards, flop: tuple[Card, Card, Card]) -> bool:
    ranks = {int(card.rank) for card in (hero_hand.card1, hero_hand.card2, *flop)}
    hero_ranks = {int(hero_hand.card1.rank), int(hero_hand.card2.rank)}
    if int(Rank.ACE) in ranks:
        ranks.add(1)
        if int(Rank.ACE) in hero_ranks:
            hero_ranks.add(1)

    for start in range(1, 11):
        window = set(range(start, start + 5))
        if len(ranks & window) == 3 and hero_ranks & window:
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
