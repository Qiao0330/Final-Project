from __future__ import annotations

from dataclasses import dataclass

from common import Action, HoleCards, PlayerAction, Position
from equity import EquityInput, EquityResult, estimate_preflop_equity
from range_model import (
    HandClass,
    RangeActionFrequency,
    estimate_open_fold_probability,
    get_hand_class,
    get_preflop_frequency,
    players_behind_count,
)


@dataclass(frozen=True)
class SolverInput:
    hero_position: Position
    hero_hand: HoleCards
    pot_size: float
    call_amount: float
    raise_amount: float
    simulations: int
    prior_actions: tuple[PlayerAction, ...] = ()


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
    recommendation: Action
    explanation: str
    prior_actions: tuple[PlayerAction, ...]


def _clamp_probability(value: float) -> float:
    return max(0.0, min(1.0, value))


def solve_preflop_decision(solver_input: SolverInput) -> SolverResult:
    active_before_hero = sum(
        1 for record in solver_input.prior_actions
        if record.action in (Action.CALL, Action.RAISE)
    )
    opponent_count = active_before_hero + players_behind_count(solver_input.hero_position)
    equity_result = estimate_preflop_equity(
        EquityInput(
            hero_hand=solver_input.hero_hand,
            opponent_count=opponent_count,
            simulations=solver_input.simulations,
        )
    )
    equity = equity_result.equity
    hand_class = get_hand_class(solver_input.hero_hand)
    range_frequency = get_preflop_frequency(solver_input.hero_position, hand_class)

    fold_probability = _clamp_probability(
        estimate_open_fold_probability(
            hero_position=solver_input.hero_position,
            hero_hand=solver_input.hero_hand,
            pot_size=solver_input.pot_size,
            raise_amount=solver_input.raise_amount,
        )
    )

    final_pot_call = solver_input.pot_size + solver_input.call_amount
    final_pot_raise = solver_input.pot_size + solver_input.raise_amount

    ev_fold = 0.0
    ev_call = equity * final_pot_call - solver_input.call_amount if solver_input.call_amount > 0.0 else 0.0
    ev_raise = (
        fold_probability * solver_input.pot_size
        + (1.0 - fold_probability) * (equity * final_pot_raise - solver_input.raise_amount)
    )

    best_action_ev = ev_call
    recommendation = Action.CALL

    if ev_raise >= best_action_ev:
        best_action_ev = ev_raise
        recommendation = Action.RAISE

    if best_action_ev <= 0.0:
        recommendation = Action.FOLD
    elif recommendation == Action.CALL and ev_call > ev_raise:
        recommendation = Action.CALL
    else:
        recommendation = Action.RAISE

    explanation = (
        f"Hand class {hand_class.name} has {range_frequency.open_frequency * 100:.0f}% "
        f"opening frequency from this position. Prior active opponents and players "
        f"behind hero are included in the equity estimate. Future fold probability "
        f"is estimated from opponents' EV versus this position's open range. Recommended "
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
        recommendation=recommendation,
        explanation=explanation,
        prior_actions=solver_input.prior_actions,
    )


def action_to_string(action: Action) -> str:
    return {
        Action.FOLD: "fold",
        Action.CALL: "call",
        Action.RAISE: "raise",
    }.get(action, "unknown")
