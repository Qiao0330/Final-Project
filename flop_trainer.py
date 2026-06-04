from __future__ import annotations

from dataclasses import dataclass
from random import choices, choice, sample

from card import FULL_DECK, card_to_string
from common import Action, Card, HoleCards, Position, Rank, Suit
from poker_eval import compare_hand_values, evaluate_7cards
from range_model import get_hand_class, get_preflop_frequency, position_to_string


STACK_BB = 100.0
BOARD_SIZE = 3
EQUITY_SIMULATIONS = 1200
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
    estimated_ev: float
    reason: str


@dataclass(frozen=True)
class FlopAnswer:
    scenario: FlopScenario
    selected_index: int
    best_index: int
    acceptable_indices: tuple[int, ...]
    range_analysis: RangeAnalysis
    estimated_equity: float
    option_results: tuple[FlopOptionResult, ...]

    @property
    def is_correct(self) -> bool:
        return self.selected_index in self.acceptable_indices


@dataclass(frozen=True)
class FlopTexture:
    made_strength: int
    draw_strength: int
    high_card_strength: int
    made_hand: str
    straight_draw: str
    flush_draw: str
    backdoor_flush: bool
    backdoor_straight: bool
    is_suited: bool
    is_connected: bool
    board_texture: str
    is_dynamic: bool
    summary: str


@dataclass(frozen=True)
class RangeProfile:
    average_strength: float
    strong_hand_density: float
    nut_hand_density: float
    draw_density: float


@dataclass(frozen=True)
class RangeAnalysis:
    hero: RangeProfile
    opponent: RangeProfile
    range_advantage: str
    nut_advantage: str


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
        options = _make_check_bet_options(pot_size, hero_position, remaining_stack, pot_type, flop)
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
                _make_check_bet_options(pot_size, hero_position, remaining_stack, pot_type, flop)
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
    range_analysis = _analyze_ranges(scenario)
    estimated_equity = _estimate_monte_carlo_equity(scenario, EQUITY_SIMULATIONS)
    option_results = tuple(
        _score_flop_option(scenario, texture, range_analysis, estimated_equity, option)
        for option in scenario.options
    )
    best_index = max(
        range(len(option_results)),
        key=lambda index: (option_results[index].estimated_ev, option_results[index].score),
    )
    best_ev = option_results[best_index].estimated_ev
    acceptable_ev_loss = max(0.15, scenario.pot_size * 0.02)
    acceptable_indices = tuple(
        index
        for index, result in enumerate(option_results)
        if result.estimated_ev >= best_ev - acceptable_ev_loss
    )
    if not acceptable_indices:
        acceptable_indices = (best_index,)

    return FlopAnswer(
        scenario=scenario,
        selected_index=selected_index,
        best_index=best_index,
        acceptable_indices=acceptable_indices,
        range_analysis=range_analysis,
        estimated_equity=estimated_equity,
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
        f"Board texture: {texture.board_texture}",
        f"Range advantage: {answer.range_analysis.range_advantage}",
        f"Nut advantage: {answer.range_analysis.nut_advantage}",
        f"Monte Carlo equity: {answer.estimated_equity * 100:.1f}%",
        (
            f"Strong-hand density: Hero {answer.range_analysis.hero.strong_hand_density * 100:.1f}% / "
            f"Opponent {answer.range_analysis.opponent.strong_hand_density * 100:.1f}%"
        ),
        f"Suggested betting structure: {_betting_strategy(answer.scenario, texture, answer.range_analysis)}",
        f"Your choice: {selected.option.label}",
        f"Highest-EV choice: {best.option.label}",
        f"Result: {'correct' if answer.is_correct else 'not correct'}",
        f"Accepted choices: {', '.join(answer.option_results[index].option.label for index in answer.acceptable_indices)}",
        "",
        "Option comparison:",
    ]

    for index, result in enumerate(answer.option_results, start=1):
        if index - 1 == answer.best_index:
            marker = " <- highest EV"
        elif index - 1 in answer.acceptable_indices:
            marker = " <- acceptable"
        else:
            marker = ""
        lines.append(
            f"{index}. {result.option.label}: estimated EV {result.estimated_ev:+.2f} BB, "
            f"strategy score {result.score:+.2f} - {result.reason}{marker}"
        )

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
    pot_type: str,
    flop: tuple[Card, Card, Card],
) -> tuple[FlopOption, ...]:
    check_label = "Check back" if hero_position == POSITION_IP else "Check"
    options = [FlopOption(check_label, Action.CHECK, 0.0)]
    seen_amounts: set[float] = set()

    for fraction, fraction_label in _reasonable_bet_sizes(pot_type, flop):
        amount = min(remaining_stack, round(pot_size * fraction, 1))
        if amount in seen_amounts:
            continue
        seen_amounts.add(amount)
        capped = "all-in, " if amount < round(pot_size * fraction, 1) else ""
        options.append(FlopOption(f"Bet {amount:.1f} BB ({capped}{fraction_label})", Action.RAISE, amount))

    return tuple(options)


def _reasonable_bet_sizes(
    pot_type: str,
    flop: tuple[Card, Card, Card],
) -> tuple[tuple[float, str], ...]:
    board_ranks = [int(card.rank) for card in flop]
    connected = max(board_ranks) - min(board_ranks) <= 4
    monotone = _is_monotone_board(flop)
    paired = len(set(board_ranks)) < 3
    high_dry = max(board_ranks) >= int(Rank.KING) and not connected and not monotone

    if pot_type in (POT_4BET, POT_5BET):
        return (
            (0.25, "1/4 pot"),
            (0.50, "1/2 pot"),
            (0.75, "3/4 pot"),
        )
    if connected or monotone:
        return (
            (0.50, "1/2 pot"),
            (0.75, "3/4 pot"),
            (1.25, "125% pot overbet"),
        )
    if high_dry or paired:
        return (
            (0.25, "1/4 pot"),
            (1.0 / 3.0, "1/3 pot"),
            (0.50, "1/2 pot"),
        )
    return (
        (1.0 / 3.0, "1/3 pot"),
        (0.50, "1/2 pot"),
        (0.75, "3/4 pot"),
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


def _analyze_ranges(scenario: FlopScenario) -> RangeAnalysis:
    hero_profile = _build_range_profile(
        position=scenario.hero_table_position,
        role=scenario.hero_role,
        pot_type=scenario.pot_type,
        flop=scenario.flop,
        blocked_cards=set(scenario.flop),
    )
    opponent_role = ROLE_DEFENDER if scenario.hero_role == ROLE_AGGRESSOR else ROLE_AGGRESSOR
    opponent_profile = _build_range_profile(
        position=scenario.opponent_position,
        role=opponent_role,
        pot_type=scenario.pot_type,
        flop=scenario.flop,
        blocked_cards={scenario.hero_hand.card1, scenario.hero_hand.card2, *scenario.flop},
    )

    strength_difference = hero_profile.average_strength - opponent_profile.average_strength
    if strength_difference >= 0.18:
        range_advantage = "Hero"
    elif strength_difference <= -0.18:
        range_advantage = "Opponent"
    else:
        range_advantage = "Close"

    nut_difference = hero_profile.nut_hand_density - opponent_profile.nut_hand_density
    if nut_difference >= 0.025:
        nut_advantage = "Hero"
    elif nut_difference <= -0.025:
        nut_advantage = "Opponent"
    else:
        nut_advantage = "Close"

    board_ranks = [int(card.rank) for card in scenario.flop]
    low_connected_board = (
        scenario.pot_type == POT_SINGLE_RAISED
        and max(board_ranks) <= int(Rank.JACK)
        and len(set(board_ranks)) == 3
        and max(board_ranks) - min(board_ranks) <= 4
    )
    if low_connected_board:
        nut_advantage = "Opponent" if scenario.hero_role == ROLE_AGGRESSOR else "Hero"

    return RangeAnalysis(
        hero=hero_profile,
        opponent=opponent_profile,
        range_advantage=range_advantage,
        nut_advantage=nut_advantage,
    )


def _build_range_profile(
    position: Position,
    role: str,
    pot_type: str,
    flop: tuple[Card, Card, Card],
    blocked_cards: set[Card],
) -> RangeProfile:
    total_weight = 0.0
    strength_total = 0.0
    strong_total = 0.0
    nut_total = 0.0
    draw_total = 0.0

    for first_index, first in enumerate(FULL_DECK):
        if first in blocked_cards:
            continue
        for second in FULL_DECK[first_index + 1:]:
            if second in blocked_cards:
                continue

            hand = HoleCards(first, second)
            hand_class = get_hand_class(hand)
            weight = _range_hand_weight(position, role, pot_type, hand_class)
            if weight <= 0.0:
                continue

            texture = _analyze_flop_texture(hand, flop)
            total_weight += weight
            strength_total += weight * (texture.made_strength + texture.draw_strength * 0.30)
            if texture.made_strength >= 4:
                strong_total += weight
            if texture.made_strength >= 5:
                nut_total += weight
            if texture.draw_strength >= 2:
                draw_total += weight

    if total_weight <= 0.0:
        return RangeProfile(0.0, 0.0, 0.0, 0.0)

    return RangeProfile(
        average_strength=strength_total / total_weight,
        strong_hand_density=strong_total / total_weight,
        nut_hand_density=nut_total / total_weight,
        draw_density=draw_total / total_weight,
    )


def _range_hand_weight(position: Position, role: str, pot_type: str, hand_class) -> float:
    open_frequency = get_preflop_frequency(position, hand_class).open_frequency

    if pot_type == POT_SINGLE_RAISED:
        if role == ROLE_AGGRESSOR:
            return open_frequency
        return 1.0 if _is_reasonable_calling_hand(hand_class) else 0.0

    if pot_type == POT_3BET:
        if role == ROLE_AGGRESSOR:
            return open_frequency if _is_reasonable_3bet_pot_hand(hand_class) else 0.0
        return 1.0 if _is_reasonable_3bet_call_hand(hand_class) else 0.0

    if pot_type == POT_4BET:
        if role == ROLE_AGGRESSOR:
            return open_frequency if _is_reasonable_4bet_pot_hand(hand_class) else 0.0
        return 1.0 if _is_reasonable_4bet_call_hand(hand_class) else 0.0

    if role == ROLE_AGGRESSOR:
        return open_frequency if _is_reasonable_5bet_pot_hand(hand_class, role) else 0.0
    return 1.0 if _is_reasonable_5bet_pot_hand(hand_class, role) else 0.0


def _estimate_monte_carlo_equity(scenario: FlopScenario, simulations: int) -> float:
    opponent_role = ROLE_DEFENDER if scenario.hero_role == ROLE_AGGRESSOR else ROLE_AGGRESSOR
    candidates = _opponent_range_candidates(
        position=scenario.opponent_position,
        role=opponent_role,
        pot_type=scenario.pot_type,
        blocked_cards={scenario.hero_hand.card1, scenario.hero_hand.card2, *scenario.flop},
    )
    if not candidates:
        return _estimate_hand_equity(
            _analyze_flop_texture(scenario.hero_hand, scenario.flop),
            _analyze_ranges(scenario),
        )

    hands = [candidate[0] for candidate in candidates]
    weights = [candidate[1] for candidate in candidates]
    wins = 0
    ties = 0
    simulation_count = max(1, simulations)

    for _ in range(simulation_count):
        opponent_hand = choices(hands, weights=weights, k=1)[0]
        blocked = {
            scenario.hero_hand.card1,
            scenario.hero_hand.card2,
            opponent_hand.card1,
            opponent_hand.card2,
            *scenario.flop,
        }
        turn, river = sample([card for card in FULL_DECK if card not in blocked], 2)
        board = (*scenario.flop, turn, river)
        hero_value = evaluate_7cards((scenario.hero_hand.card1, scenario.hero_hand.card2, *board))
        opponent_value = evaluate_7cards((opponent_hand.card1, opponent_hand.card2, *board))
        comparison = compare_hand_values(hero_value, opponent_value)

        if comparison > 0:
            wins += 1
        elif comparison == 0:
            ties += 1

    return (wins + ties * 0.5) / simulation_count


def _opponent_range_candidates(
    position: Position,
    role: str,
    pot_type: str,
    blocked_cards: set[Card],
) -> list[tuple[HoleCards, float]]:
    candidates: list[tuple[HoleCards, float]] = []

    for first_index, first in enumerate(FULL_DECK):
        if first in blocked_cards:
            continue
        for second in FULL_DECK[first_index + 1:]:
            if second in blocked_cards:
                continue

            hand = HoleCards(first, second)
            weight = _range_hand_weight(position, role, pot_type, get_hand_class(hand))
            if weight > 0.0:
                candidates.append((hand, weight))

    return candidates


def _is_reasonable_3bet_call_hand(hand_class) -> bool:
    if hand_class.pair and hand_class.high_rank >= int(Rank.EIGHT):
        return True
    if hand_class.high_rank == int(Rank.ACE) and hand_class.low_rank >= int(Rank.JACK):
        return True
    return hand_class.suited and hand_class.high_rank >= int(Rank.TEN)


def _is_reasonable_4bet_call_hand(hand_class) -> bool:
    if hand_class.pair and hand_class.high_rank >= int(Rank.JACK):
        return True
    return hand_class.high_rank == int(Rank.ACE) and hand_class.low_rank >= int(Rank.KING)


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
    raise_size = min(remaining_stack, round(bet_size * 3.0, 1))
    return (
        FlopOption("Fold", Action.FOLD, 0.0),
        FlopOption("Call", Action.CALL, bet_size),
        FlopOption(f"Raise to {raise_size:.1f} BB (3x bet)", Action.RAISE, raise_size),
    )


def _score_flop_option(
    scenario: FlopScenario,
    texture: FlopTexture,
    range_analysis: RangeAnalysis,
    estimated_equity: float,
    option: FlopOption,
) -> FlopOptionResult:
    estimated_ev = _estimate_option_ev(
        scenario,
        texture,
        range_analysis,
        estimated_equity,
        option,
    )

    if option.action == Action.FOLD:
        score = 0.0
        if texture.made_strength <= 1 and texture.draw_strength == 0 and not texture.backdoor_flush:
            score += 2.0
        if texture.made_strength >= 3 or texture.draw_strength >= 2:
            score -= 5.0
        if range_analysis.range_advantage == "Opponent":
            score += 0.4
        return FlopOptionResult(
            option,
            score,
            estimated_ev,
            "fold performs best with little showdown value and no meaningful draw",
        )

    if option.action == Action.CALL:
        score = texture.made_strength * 1.4 + texture.draw_strength * 1.1 - scenario.pfa_bet_size / scenario.pot_size
        if texture.made_hand in ("top pair", "middle pair", "bottom pair", "underpair", "pocket pair"):
            score += 1.0
        if texture.made_strength >= 5:
            score -= 1.5
        if texture.draw_strength >= 3:
            score += 0.8
        if range_analysis.range_advantage == "Hero":
            score += 0.4
        return FlopOptionResult(
            option,
            score,
            estimated_ev,
            "call preserves medium made hands and strong drawing equity",
        )

    if option.action == Action.CHECK:
        score = 1.0
        if texture.made_strength <= 2 or texture.made_hand == "top pair":
            score += 1.5
        if texture.draw_strength >= 2:
            score += 0.5
        if texture.made_strength >= 5:
            score -= 1.0
        return FlopOptionResult(
            option,
            score,
            estimated_ev,
            "checking protects medium-strength hands and realizes equity",
        )

    score = texture.made_strength * 1.1 + texture.draw_strength * 1.5 + texture.high_card_strength * 0.3
    if scenario.hero_position == POSITION_IP:
        score += 0.4
    if texture.made_strength <= 1 and texture.draw_strength == 0:
        score -= 2.0
    if texture.made_strength <= 2 and texture.draw_strength == 0:
        score -= 2.0

    size_ratio = option.amount / scenario.pot_size
    strategy = _betting_strategy(scenario, texture, range_analysis)
    premium_value = texture.made_strength >= 5
    strong_value = texture.made_strength >= 4 or texture.made_hand == "top pair"
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

    if _has_range_bet_advantage(scenario, range_analysis):
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
    if range_analysis.nut_advantage == "Hero" and size_ratio >= 0.75:
        score += 0.8
    elif range_analysis.nut_advantage == "Opponent" and size_ratio >= 0.75:
        score -= 1.2

    reason = (
        f"{strategy} sizing: large bets favor premium value and quality bluffs; "
        "small and medium bets support a wider linear range"
    )
    return FlopOptionResult(option, score, estimated_ev, reason)


def _estimate_option_ev(
    scenario: FlopScenario,
    texture: FlopTexture,
    range_analysis: RangeAnalysis,
    equity: float,
    option: FlopOption,
) -> float:
    if option.action == Action.FOLD:
        return 0.0

    if option.action == Action.CHECK:
        realization = 0.94 if scenario.hero_position == POSITION_IP else 0.84
        if range_analysis.range_advantage == "Hero":
            realization += 0.02
        elif range_analysis.range_advantage == "Opponent":
            realization -= 0.03
        return equity * scenario.pot_size * max(0.60, min(0.98, realization))

    if option.action == Action.CALL:
        final_pot = scenario.pot_size + scenario.pfa_bet_size * 2.0
        return equity * final_pot - scenario.pfa_bet_size

    if scenario.pfa_action == PFA_BET:
        fold_probability = _estimate_raise_fold_probability(scenario, texture, range_analysis, option)
        pot_when_opponent_folds = scenario.pot_size + scenario.pfa_bet_size
        final_pot = scenario.pot_size + option.amount * 2.0
        continue_equity = max(0.03, equity - 0.20)
        return (
            fold_probability * pot_when_opponent_folds
            + (1.0 - fold_probability) * (continue_equity * final_pot - option.amount)
        )

    fold_probability = _estimate_bet_fold_probability(scenario, texture, range_analysis, option)
    final_pot = scenario.pot_size + option.amount * 2.0
    size_ratio = option.amount / scenario.pot_size
    continue_equity = max(0.03, equity - 0.12 - size_ratio * 0.06)
    return (
        fold_probability * scenario.pot_size
        + (1.0 - fold_probability) * (continue_equity * final_pot - option.amount)
    )


def _estimate_hand_equity(texture: FlopTexture, range_analysis: RangeAnalysis) -> float:
    made_equity = {
        "four of a kind": 0.98,
        "full house": 0.96,
        "flush": 0.90,
        "straight": 0.86,
        "set": 0.84,
        "trips": 0.80,
        "two pair": 0.74,
        "overpair": 0.68,
        "top pair": 0.60,
        "middle pair": 0.48,
        "bottom pair": 0.43,
        "pocket pair": 0.42,
        "underpair": 0.34,
        "pair on board": 0.31,
        "trips on board": 0.36,
        "two overcards": 0.29,
        "one overcard": 0.24,
        "ace high": 0.23,
        "king high": 0.18,
        "no showdown value": 0.13,
    }.get(texture.made_hand, 0.20)

    equity = made_equity + texture.draw_strength * 0.055
    if texture.backdoor_flush:
        equity += 0.025
    if texture.backdoor_straight:
        equity += 0.020
    if range_analysis.range_advantage == "Hero":
        equity += 0.025
    elif range_analysis.range_advantage == "Opponent":
        equity -= 0.025
    return max(0.05, min(0.97, equity))


def _estimate_bet_fold_probability(
    scenario: FlopScenario,
    texture: FlopTexture,
    range_analysis: RangeAnalysis,
    option: FlopOption,
) -> float:
    size_ratio = option.amount / scenario.pot_size
    base = 0.10 + min(0.34, size_ratio * 0.18)

    if range_analysis.range_advantage == "Hero":
        base += 0.06
    elif range_analysis.range_advantage == "Opponent":
        base -= 0.06
    if range_analysis.nut_advantage == "Hero":
        base += 0.04
    elif range_analysis.nut_advantage == "Opponent":
        base -= 0.05
    if texture.backdoor_flush or texture.backdoor_straight:
        base += 0.02

    return max(0.05, min(0.55, base))


def _estimate_raise_fold_probability(
    scenario: FlopScenario,
    texture: FlopTexture,
    range_analysis: RangeAnalysis,
    option: FlopOption,
) -> float:
    base = 0.24
    if range_analysis.nut_advantage == "Hero":
        base += 0.08
    elif range_analysis.nut_advantage == "Opponent":
        base -= 0.10
    if texture.draw_strength >= 3:
        base += 0.03
    if option.amount >= scenario.remaining_stack:
        base += 0.08
    return max(0.05, min(0.55, base))


def _betting_strategy(
    scenario: FlopScenario,
    texture: FlopTexture,
    range_analysis: RangeAnalysis,
) -> str:
    if scenario.pot_type in (POT_4BET, POT_5BET):
        return "linear"
    if _has_range_bet_advantage(scenario, range_analysis):
        return "linear"
    if range_analysis.nut_advantage != "Hero" or texture.is_dynamic or _is_monotone_board(scenario.flop):
        return "polarized"
    return "linear"


def _has_range_bet_advantage(scenario: FlopScenario, range_analysis: RangeAnalysis) -> bool:
    if scenario.hero_role != ROLE_AGGRESSOR:
        return False
    return range_analysis.range_advantage == "Hero"


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

    made_hand, made_strength = _classify_made_hand(hero_hand, flop, rank_counts, suit_counts)
    flush_draw = _classify_flush_draw(hero_hand, suit_counts)
    straight_draw = "" if made_hand == "straight" else _classify_straight_draw(hero_hand, cards)
    backdoor_flush = not flush_draw and _has_backdoor_flush(hero_hand, flop)
    backdoor_straight = not straight_draw and _has_backdoor_straight(hero_hand, flop)
    draw_strength = 0
    if flush_draw:
        draw_strength += 3 if flush_draw == "nut flush draw" else 2
    if straight_draw:
        draw_strength += 3 if straight_draw in ("open-ended straight draw", "double gutshot") else 2
    if flush_draw and straight_draw:
        draw_strength += 1

    high_card_strength = sum(1 for rank in hero_ranks if rank >= int(Rank.JACK))
    board_texture, is_suited, is_connected, is_dynamic = _classify_board_texture(flop)
    summary_parts = [made_hand]
    if flush_draw:
        summary_parts.append(flush_draw)
    if straight_draw:
        summary_parts.append(straight_draw)
    if flush_draw and straight_draw:
        summary_parts.append("combo draw")
    if backdoor_flush:
        summary_parts.append("backdoor flush draw")
    if backdoor_straight:
        summary_parts.append("backdoor straight draw")

    return FlopTexture(
        made_strength=made_strength,
        draw_strength=draw_strength,
        high_card_strength=high_card_strength,
        made_hand=made_hand,
        straight_draw=straight_draw,
        flush_draw=flush_draw,
        backdoor_flush=backdoor_flush,
        backdoor_straight=backdoor_straight,
        is_suited=is_suited,
        is_connected=is_connected,
        board_texture=board_texture,
        is_dynamic=is_dynamic,
        summary=", ".join(summary_parts),
    )


def _classify_made_hand(
    hero_hand: HoleCards,
    flop: tuple[Card, Card, Card],
    rank_counts: dict[int, int],
    suit_counts: dict[Suit, int],
) -> tuple[str, int]:
    hero_ranks = (int(hero_hand.card1.rank), int(hero_hand.card2.rank))
    board_ranks = sorted((int(card.rank) for card in flop), reverse=True)
    counts = sorted(rank_counts.values(), reverse=True)

    if counts[0] == 4:
        return "four of a kind", 6
    if counts[0] == 3 and counts[1] == 2:
        return "full house", 6
    if max(suit_counts.values()) == 5:
        return "flush", 6
    if _has_made_straight(rank_counts):
        return "straight", 5
    if counts[0] == 3:
        trip_rank = next(rank for rank, count in rank_counts.items() if count == 3)
        if trip_rank not in hero_ranks:
            return "trips on board", 2
        if hero_ranks[0] == hero_ranks[1]:
            return "set", 5
        return "trips", 5

    pair_ranks = sorted((rank for rank, count in rank_counts.items() if count == 2), reverse=True)
    if len(pair_ranks) >= 2:
        return "two pair", 4
    if pair_ranks:
        pair_rank = pair_ranks[0]
        if pair_rank not in hero_ranks:
            return "pair on board", 1
        if hero_ranks[0] == hero_ranks[1]:
            if pair_rank > board_ranks[0]:
                return "overpair", 4
            if pair_rank < board_ranks[-1]:
                return "underpair", 2
            return "pocket pair", 2

        distinct_board = sorted(set(board_ranks), reverse=True)
        pair_position = distinct_board.index(pair_rank)
        if pair_position == 0:
            return "top pair", 3
        if pair_position == len(distinct_board) - 1:
            return "bottom pair", 2
        return "middle pair", 2

    board_high = board_ranks[0]
    overcards = sum(1 for rank in hero_ranks if rank > board_high)
    if overcards == 2:
        return "two overcards", 1
    if overcards == 1:
        return "one overcard", 1
    if int(Rank.ACE) in hero_ranks:
        return "ace high", 1
    if int(Rank.KING) in hero_ranks:
        return "king high", 1
    return "no showdown value", 0


def _has_made_straight(rank_counts: dict[int, int]) -> bool:
    ranks = set(rank_counts)
    if int(Rank.ACE) in ranks:
        ranks.add(1)
    return any(set(range(start, start + 5)) <= ranks for start in range(1, 11))


def _classify_flush_draw(hero_hand: HoleCards, suit_counts: dict[Suit, int]) -> str:
    for suit, count in suit_counts.items():
        if count != 4:
            continue
        hero_suited_cards = [card for card in (hero_hand.card1, hero_hand.card2) if card.suit == suit]
        if not hero_suited_cards:
            continue
        if any(card.rank == Rank.ACE for card in hero_suited_cards):
            return "nut flush draw"
        return "flush draw"
    return ""


def _classify_straight_draw(hero_hand: HoleCards, cards: tuple[Card, ...]) -> str:
    ranks = {int(card.rank) for card in cards}
    hero_ranks = {int(hero_hand.card1.rank), int(hero_hand.card2.rank)}
    if int(Rank.ACE) in ranks:
        ranks.add(1)
        if int(Rank.ACE) in hero_ranks:
            hero_ranks.add(1)

    missing_outs: set[int] = set()
    contributing_ranks: set[int] = set()
    for start in range(1, 11):
        window = set(range(start, start + 5))
        present = ranks & window
        if len(present) == 4 and hero_ranks & present:
            missing_outs.update(window - ranks)
            contributing_ranks.update(present)

    if len(missing_outs) >= 2:
        if contributing_ranks and max(contributing_ranks) - min(contributing_ranks) == 3:
            return "open-ended straight draw"
        return "double gutshot"
    if len(missing_outs) == 1:
        return "gutshot"
    return ""


def _classify_board_texture(flop: tuple[Card, Card, Card]) -> tuple[str, bool, bool, bool]:
    board_ranks = sorted((int(card.rank) for card in flop), reverse=True)
    unique_ranks = set(board_ranks)
    suit_count = len({card.suit for card in flop})
    paired = len(unique_ranks) < 3
    connected = not paired and max(board_ranks) - min(board_ranks) <= 4
    semi_connected = not paired and max(board_ranks) - min(board_ranks) <= 6

    suit_label = {1: "monotone", 2: "two-tone", 3: "rainbow"}[suit_count]
    if connected:
        connection_label = "connected"
    elif semi_connected:
        connection_label = "semi-connected"
    else:
        connection_label = "disconnected"
    pair_label = "paired" if paired else "unpaired"
    is_dynamic = suit_count <= 2 or connected
    dynamic_label = "dynamic" if is_dynamic else "static"
    return (
        f"{pair_label}, {suit_label}, {connection_label}, {dynamic_label}",
        suit_count <= 2,
        connected,
        is_dynamic,
    )


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
