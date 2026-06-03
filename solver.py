from __future__ import annotations

from dataclasses import dataclass

from common import Action, Card, HoleCards, PlayerAction, Position
from equity import EquityInput, EquityResult, estimate_preflop_equity
from range_model import HandClass, RangeActionFrequency, get_hand_class, get_preflop_frequency
from range_model import estimate_open_fold_probability


@dataclass(frozen=True)
class SolverInput:
    hero_position: Position
    hero_hand: HoleCards
    pot_size: float
    call_amount: float
    raise_amount: float
    simulations: int
    prior_actions: tuple[PlayerAction, ...] = ()
    table_actions: tuple[PlayerAction, ...] = ()
    future_contribution: float = 0.0
    active_opponent_count: int | None = None
    candidate_raise_amounts: tuple[float, ...] = ()
    board_cards: tuple[Card, ...] = ()


@dataclass(frozen=True)
class SolverActionEV:
    action: Action
    amount: float
    ev: float


@dataclass(frozen=True)
class SolverResult:
    equity_result: EquityResult
    hero_position: Position
    opponent_count: int
    fold_probability: float
    hand_class: HandClass
    range_frequency: RangeActionFrequency
    equity: float
    ev_fold: float
    ev_call: float
    ev_raise: float
    ev_check: float
    best_raise_amount: float
    recommendation: Action
    explanation: str
    prior_actions: tuple[PlayerAction, ...]
    table_actions: tuple[PlayerAction, ...]
    action_evs: tuple[SolverActionEV, ...]


def _clamp_probability(value: float) -> float:
    return max(0.0, min(1.0, value))


def _candidate_raise_amounts(solver_input: SolverInput) -> tuple[float, ...]:
    values = solver_input.candidate_raise_amounts or (
        (solver_input.raise_amount,) if solver_input.raise_amount > 0.0 else ()
    )
    clean_values = sorted({amount for amount in values if amount > 0.0})
    return tuple(clean_values)


def solve_preflop_decision(solver_input: SolverInput) -> SolverResult:
    action_records = solver_input.table_actions or solver_input.prior_actions
    raise_amounts = _candidate_raise_amounts(solver_input)
    fold_model_raise_amount = max(raise_amounts) if raise_amounts else solver_input.raise_amount
    if solver_input.active_opponent_count is not None:
        opponent_count = max(0, solver_input.active_opponent_count)
    else:
        opponent_count = sum(
            1 for record in action_records
            if record.action in (Action.CALL, Action.RAISE) and record.position != solver_input.hero_position
        )
    equity_result = estimate_preflop_equity(
        EquityInput(
            hero_hand=solver_input.hero_hand,
            opponent_count=opponent_count,
            simulations=solver_input.simulations,
            board_cards=solver_input.board_cards,
        )
    )
    equity = equity_result.equity
    hand_class = get_hand_class(solver_input.hero_hand)
    range_frequency = get_preflop_frequency(solver_input.hero_position, hand_class)

    last_hero_action_index = -1
    for index, record in enumerate(action_records):
        if record.position == solver_input.hero_position:
            last_hero_action_index = index

    actions_after_hero = (
        action_records[last_hero_action_index + 1:]
        if last_hero_action_index >= 0
        else ()
    )
    non_hero_actions_after_hero = [
        record for record in actions_after_hero
        if record.position != solver_input.hero_position
    ]
    if non_hero_actions_after_hero:
        folds_after_hero = sum(
            1 for record in non_hero_actions_after_hero
            if record.action == Action.FOLD
        )
        fold_probability = folds_after_hero / len(non_hero_actions_after_hero)
    else:
        fold_probability = estimate_open_fold_probability(
            hero_position=solver_input.hero_position,
            hero_hand=solver_input.hero_hand,
            pot_size=solver_input.pot_size,
            raise_amount=fold_model_raise_amount,
        )
    fold_probability = _clamp_probability(fold_probability)

    future_contribution = max(0.0, solver_input.future_contribution)
    final_pot_call = solver_input.pot_size + solver_input.call_amount + future_contribution

    ev_fold = 0.0
    ev_check = equity * (solver_input.pot_size + future_contribution) if solver_input.call_amount == 0.0 else 0.0
    ev_call = equity * final_pot_call - solver_input.call_amount if solver_input.call_amount > 0.0 else 0.0

    action_evs: list[SolverActionEV] = [SolverActionEV(Action.FOLD, 0.0, ev_fold)]
    if solver_input.call_amount > 0.0:
        action_evs.append(SolverActionEV(Action.CALL, solver_input.call_amount, ev_call))
    else:
        action_evs.append(SolverActionEV(Action.CHECK, 0.0, ev_check))

    raise_results: list[SolverActionEV] = []
    for raise_amount in raise_amounts:
        final_pot_raise = solver_input.pot_size + raise_amount + future_contribution
        ev = (
            fold_probability * solver_input.pot_size
            + (1.0 - fold_probability) * (equity * final_pot_raise - raise_amount)
        )
        raise_results.append(SolverActionEV(Action.RAISE, raise_amount, ev))
        action_evs.append(raise_results[-1])

    best_raise = max(raise_results, key=lambda item: item.ev) if raise_results else None
    ev_raise = best_raise.ev if best_raise is not None else 0.0
    best_raise_amount = best_raise.amount if best_raise is not None else 0.0

    best_action = max(action_evs, key=lambda item: item.ev)
    recommendation = best_action.action
    if recommendation != Action.CHECK and best_action.ev <= 0.0:
        recommendation = Action.FOLD

    explanation = (
        f"Hand class {hand_class.name} has {range_frequency.open_frequency * 100:.0f}% "
        f"opening frequency from this position. Board has "
        f"{len(solver_input.board_cards)} known card(s). Opponent count is based on the "
        f"actual entered actions: non-hero players who call or raise are included "
        f"in the equity estimate. Raise EV uses the best candidate sizing "
        f"({best_raise_amount:.2f} BB). Future fold probability is based on entered "
        f"post-hero actions or the simplified range model. Recommended "
        f"{action_to_string(recommendation)} because it is the highest positive EV action."
    )

    return SolverResult(
        equity_result=equity_result,
        hero_position=solver_input.hero_position,
        opponent_count=opponent_count,
        fold_probability=fold_probability,
        hand_class=hand_class,
        range_frequency=range_frequency,
        equity=equity,
        ev_fold=ev_fold,
        ev_call=ev_call,
        ev_raise=ev_raise,
        ev_check=ev_check,
        best_raise_amount=best_raise_amount,
        recommendation=recommendation,
        explanation=explanation,
        prior_actions=solver_input.prior_actions,
        table_actions=action_records,
        action_evs=tuple(action_evs),
    )


def action_to_string(action: Action) -> str:
    return {
        Action.FOLD: "fold",
        Action.CALL: "call",
        Action.RAISE: "raise",
        Action.CHECK: "check",
    }.get(action, "unknown")
