from __future__ import annotations

from dataclasses import dataclass

from common import TABLE_POSITIONS, Action, PlayerAction, Position
from range_model import position_to_string


POSITIONS = TABLE_POSITIONS
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
    view_nodes: dict[Position, tuple[PlayerAction, ...]]


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
    last_actor: Position | None = None
    validation_errors: list[str] = []
    processed_records: list[PlayerAction] = []
    view_nodes: dict[Position, tuple[PlayerAction, ...]] = {}

    for record in action_history:
        position = record.position
        expected_position = _next_to_act(folded, contributions, current_bet, acted, last_actor)
        if expected_position is None:
            validation_errors.append("betting round is already closed")
            continue
        if position != expected_position:
            validation_errors.append(
                f"out-of-turn action: expected {position_to_string(expected_position)}, "
                f"got {position_to_string(position)}"
            )
            continue
        if position in folded:
            validation_errors.append(f"{position_to_string(position)} already folded")
            continue
        if record.action == Action.FOLD:
            view_nodes[position] = tuple(processed_records)
            folded.add(position)
            acted.add(position)
            last_actor = position
            processed_records.append(record)
            continue
        if record.action == Action.CHECK:
            if current_bet > contributions[position]:
                validation_errors.append(f"{position_to_string(position)} cannot check facing {current_bet - contributions[position]:.2f} BB")
                continue
            view_nodes[position] = tuple(processed_records)
            acted.add(position)
            last_actor = position
            processed_records.append(record)
            continue
        if record.action == Action.CALL:
            amount_to_call = max(0.0, current_bet - contributions[position])
            if amount_to_call <= 0.0:
                validation_errors.append(f"{position_to_string(position)} cannot call when check is available")
                continue
            amount_added = min(amount_to_call, EFFECTIVE_STACK_BB - contributions[position])
            if record.amount > 0.0 and abs(record.amount - amount_added) > 1e-9:
                validation_errors.append(
                    f"{position_to_string(position)} call must add exactly {amount_added:.2f} BB"
                )
                continue
            view_nodes[position] = tuple(processed_records)
            contributions[position] += amount_added
            acted.add(position)
            last_actor = position
            processed_records.append(record)
            continue
        if record.action == Action.RAISE:
            new_total = min(record.amount, EFFECTIVE_STACK_BB)
            min_total = _min_raise_total(current_bet, last_raise_increment)
            if current_bet >= EFFECTIVE_STACK_BB or new_total <= current_bet:
                validation_errors.append(f"{position_to_string(position)} cannot raise to {record.amount:.2f} BB")
                continue
            if new_total < min_total and new_total < EFFECTIVE_STACK_BB:
                validation_errors.append(f"{position_to_string(position)} raise total must be at least {min_total:.2f} BB")
                continue
            view_nodes[position] = tuple(processed_records)
            raise_increment = max(0.0, new_total - current_bet)
            contributions[position] = new_total
            current_bet = new_total
            if raise_increment > 0.0:
                last_raise_increment = raise_increment
            acted = {position}
            last_actor = position
            processed_records.append(record)

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
    next_to_act = _next_to_act(folded, contributions, current_bet, acted, last_actor)
    legal_actions = _legal_actions(next_to_act, folded, contributions, current_bet)
    min_raise_total = _min_raise_total(current_bet, last_raise_increment)
    generated_view_nodes = _complete_view_nodes(
        processed_records=tuple(processed_records),
        existing_nodes=view_nodes,
        folded=folded,
        contributions=contributions,
        current_bet=current_bet,
        acted=acted,
        last_actor=last_actor,
    )

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
        view_nodes=generated_view_nodes,
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
        "view_nodes": {
            position_to_string(position): [
                _action_record_to_dict(record)
                for record in history
            ]
            for position, history in state.view_nodes.items()
        },
        "legal_actions": [
            _action_to_string(action)
            for action in state.legal_actions
        ],
        "seats": {
            position_to_string(position): _seat_state_to_dict(position, state)
            for position in POSITIONS
        },
    }


def _complete_view_nodes(
    processed_records: tuple[PlayerAction, ...],
    existing_nodes: dict[Position, tuple[PlayerAction, ...]],
    folded: set[Position],
    contributions: dict[Position, float],
    current_bet: float,
    acted: set[Position],
    last_actor: Position | None,
) -> dict[Position, tuple[PlayerAction, ...]]:
    nodes = dict(existing_nodes)
    for target in POSITIONS:
        if target in nodes and target in folded:
            continue
        generated = _generate_view_node_to_target(
            target=target,
            processed_records=processed_records,
            folded=folded,
            contributions=contributions,
            current_bet=current_bet,
            acted=acted,
            last_actor=last_actor,
        )
        if generated is not None:
            nodes[target] = generated
        elif target in nodes:
            continue
    return {
        position: nodes[position]
        for position in POSITIONS
        if position in nodes
    }


def _generate_view_node_to_target(
    target: Position,
    processed_records: tuple[PlayerAction, ...],
    folded: set[Position],
    contributions: dict[Position, float],
    current_bet: float,
    acted: set[Position],
    last_actor: Position | None,
) -> tuple[PlayerAction, ...] | None:
    if target in folded:
        return None
    local_folded = set(folded)
    local_contributions = dict(contributions)
    local_acted = set(acted)
    local_last_actor = last_actor
    generated = list(processed_records)

    for _ in range(len(POSITIONS) * 2):
        next_position = _next_to_act(
            local_folded,
            local_contributions,
            current_bet,
            local_acted,
            local_last_actor,
        )
        if next_position is None:
            return None
        if next_position == target:
            return tuple(generated)

        to_call = max(0.0, current_bet - local_contributions[next_position])
        if to_call > 0.0:
            record = PlayerAction(next_position, Action.FOLD, 0.0)
            local_folded.add(next_position)
        else:
            record = PlayerAction(next_position, Action.CHECK, 0.0)
        generated.append(record)
        local_acted.add(next_position)
        local_last_actor = next_position
    return None


def _action_record_to_dict(record: PlayerAction) -> dict:
    return {
        "position": position_to_string(record.position),
        "action": _action_to_string(record.action),
        "amount": record.amount,
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
        (
            contributions[position] >= EFFECTIVE_STACK_BB
            or (contributions[position] >= current_bet and position in acted)
        )
        for position in active
    )


def _next_to_act(
    folded: set[Position],
    contributions: dict[Position, float],
    current_bet: float,
    acted: set[Position],
    after_position: Position | None = None,
) -> Position | None:
    if _betting_is_closed(folded, contributions, current_bet, acted):
        return None
    start_index = 0 if after_position is None else (POSITIONS.index(after_position) + 1) % len(POSITIONS)
    for offset in range(len(POSITIONS)):
        position = POSITIONS[(start_index + offset) % len(POSITIONS)]
        if position in folded:
            continue
        if contributions[position] >= EFFECTIVE_STACK_BB:
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
    can_raise = current_bet < EFFECTIVE_STACK_BB and contributions[position] < EFFECTIVE_STACK_BB
    if to_call > 0.0:
        return (Action.FOLD, Action.CALL, Action.RAISE) if can_raise else (Action.FOLD, Action.CALL)
    return (Action.CHECK, Action.RAISE) if can_raise else (Action.CHECK,)


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
