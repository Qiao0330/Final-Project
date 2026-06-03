from __future__ import annotations

from dataclasses import dataclass

from common import Action, PlayerAction, Position
from range_model import position_to_string


POSITIONS = (Position.UTG, Position.HJ, Position.CO, Position.BTN, Position.SB, Position.BB)
EFFECTIVE_STACK_BB = 100.0


@dataclass(frozen=True)
class PreflopBettingState:
    pot_size: float
    current_bet: float
    call_amount: float
    active_opponent_count: int
    folded_positions: tuple[Position, ...]
    contributions: dict[Position, float]
    next_to_act: Position | None
    is_closed: bool
    legal_actions: tuple[Action, ...]
    min_raise_total: float
    max_raise_total: float
    validation_errors: tuple[str, ...]


def derive_preflop_state(
    hero_position: Position,
    action_history: tuple[PlayerAction, ...],
) -> PreflopBettingState:
    contributions = {position: 0.0 for position in POSITIONS}
    folded: set[Position] = set()
    acted: set[Position] = set()
    contributions[Position.SB] = 0.5
    contributions[Position.BB] = 1.0
    current_bet = 1.0
    last_raise_increment = 1.0
    validation_errors: list[str] = []

    for record in action_history:
        position = record.position
        if position in folded:
            validation_errors.append(f"{position_to_string(position)} already folded")
            continue
        if record.action == Action.FOLD:
            folded.add(position)
            acted.add(position)
            continue
        if record.action == Action.CHECK:
            if current_bet > contributions[position]:
                validation_errors.append(f"{position_to_string(position)} cannot check facing {current_bet - contributions[position]:.2f} BB")
            acted.add(position)
            continue
        if record.action == Action.CALL:
            amount_to_call = max(0.0, current_bet - contributions[position])
            amount_added = record.amount if record.amount > 0.0 else amount_to_call
            if amount_added > amount_to_call and contributions[position] + amount_added < EFFECTIVE_STACK_BB:
                validation_errors.append(f"{position_to_string(position)} call exceeds required amount")
            amount_added = min(amount_added, EFFECTIVE_STACK_BB - contributions[position])
            contributions[position] += amount_added
            acted.add(position)
            continue
        if record.action == Action.RAISE:
            new_total = record.amount
            min_total = _min_raise_total(current_bet, last_raise_increment)
            if new_total < min_total and new_total < EFFECTIVE_STACK_BB:
                validation_errors.append(f"{position_to_string(position)} raise total must be at least {min_total:.2f} BB")
            new_total = min(max(new_total, current_bet), EFFECTIVE_STACK_BB)
            raise_increment = max(0.0, new_total - current_bet)
            contributions[position] = new_total
            current_bet = new_total
            if raise_increment > 0.0:
                last_raise_increment = raise_increment
            acted = {position}

    pot_size = sum(contributions.values())
    call_amount = 0.0 if hero_position in folded else max(0.0, current_bet - contributions[hero_position])
    active_positions = [
        position for position in POSITIONS
        if position not in folded
    ]
    active_opponent_count = len([
        position for position in active_positions
        if position != hero_position
    ])
    is_closed = _betting_is_closed(folded, contributions, current_bet, acted)
    next_to_act = _next_to_act(folded, contributions, current_bet, acted)
    legal_actions = _legal_actions(next_to_act, folded, contributions, current_bet)
    min_raise_total = _min_raise_total(current_bet, last_raise_increment)

    return PreflopBettingState(
        pot_size=pot_size,
        current_bet=current_bet,
        call_amount=call_amount,
        active_opponent_count=active_opponent_count,
        folded_positions=tuple(sorted(folded, key=int)),
        contributions=contributions,
        next_to_act=next_to_act,
        is_closed=is_closed,
        legal_actions=legal_actions,
        min_raise_total=min_raise_total,
        max_raise_total=EFFECTIVE_STACK_BB,
        validation_errors=tuple(validation_errors),
    )


def betting_state_to_dict(state: PreflopBettingState) -> dict:
    return {
        "pot_bb": state.pot_size,
        "current_bet_bb": state.current_bet,
        "call_amount_bb": state.call_amount,
        "active_opponent_count": state.active_opponent_count,
        "folded_positions": [
            position_to_string(position)
            for position in state.folded_positions
        ],
        "contributions": {
            position_to_string(position): amount
            for position, amount in state.contributions.items()
        },
        "next_to_act": position_to_string(state.next_to_act) if state.next_to_act is not None else None,
        "is_closed": state.is_closed,
        "min_raise_total_bb": state.min_raise_total,
        "max_raise_total_bb": state.max_raise_total,
        "validation_errors": list(state.validation_errors),
        "legal_actions": [
            _action_to_string(action)
            for action in state.legal_actions
        ],
        "seats": {
            position_to_string(position): _seat_state_to_dict(position, state)
            for position in POSITIONS
        },
    }


def _active_positions(folded: set[Position]) -> list[Position]:
    return [position for position in POSITIONS if position not in folded]


def _betting_is_closed(
    folded: set[Position],
    contributions: dict[Position, float],
    current_bet: float,
    acted: set[Position],
) -> bool:
    active = _active_positions(folded)
    if len(active) <= 1:
        return True
    return all(
        contributions[position] >= current_bet and position in acted
        for position in active
    )


def _next_to_act(
    folded: set[Position],
    contributions: dict[Position, float],
    current_bet: float,
    acted: set[Position],
) -> Position | None:
    if _betting_is_closed(folded, contributions, current_bet, acted):
        return None
    for position in POSITIONS:
        if position in folded:
            continue
        if contributions[position] < current_bet or position not in acted:
            return position
    return None


def _legal_actions(
    position: Position | None,
    folded: set[Position],
    contributions: dict[Position, float],
    current_bet: float,
) -> tuple[Action, ...]:
    if position is None or position in folded:
        return ()
    to_call = max(0.0, current_bet - contributions[position])
    if to_call > 0.0:
        return (Action.FOLD, Action.CALL, Action.RAISE)
    return (Action.CHECK, Action.RAISE)


def _min_raise_total(current_bet: float, last_raise_increment: float) -> float:
    return min(EFFECTIVE_STACK_BB, current_bet + max(1.0, last_raise_increment))


def _seat_state_to_dict(position: Position, state: PreflopBettingState) -> dict:
    to_call = max(0.0, state.current_bet - state.contributions[position])
    can_act = state.next_to_act == position and not state.is_closed
    return {
        "position": position_to_string(position),
        "contribution": state.contributions[position],
        "to_call": to_call,
        "min_raise_total": state.min_raise_total,
        "max_raise_total": state.max_raise_total,
        "folded": position in state.folded_positions,
        "can_act": can_act,
        "available_actions": [
            _action_to_string(action)
            for action in state.legal_actions
        ] if can_act else [],
    }


def _action_to_string(action: Action) -> str:
    return {
        Action.FOLD: "fold",
        Action.CALL: "call",
        Action.RAISE: "raise",
        Action.CHECK: "check",
    }.get(action, "unknown")
