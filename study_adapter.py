from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from adapter_utils import (
    action_history_from_dicts,
    action_to_label,
    cards_to_text,
    default_stacks,
    hand_to_text,
    mixed_frequencies_from_named_evs,
    parse_board_text,
    parse_hand_text,
    parse_position_name,
)
from betting_state import betting_state_to_dict, derive_preflop_state
from common import Action, Card, HoleCards, Position, Rank, Suit
from equity import EquityInput, estimate_preflop_equity
from range_equity import (
    continuing_ranges_for_raise,
    engaged_opponent_ranges,
    estimate_equity_against_ranges,
    infer_opponent_ranges,
    range_summary_to_dict,
    single_caller_range,
)
from range_model import (
    all_preflop_hand_classes,
    get_hand_class,
    get_preflop_frequency,
    hand_strength_score,
    position_to_string,
)


@dataclass(frozen=True)
class SingleOpenContext:
    hero_position: Position
    opener_position: Position
    in_position: bool
    call_target: float
    raise_target: float


SINGLE_OPEN_TARGETS = {
    (Position.HJ, Position.UTG): (0.014, 0.071),
    (Position.CO, Position.HJ): (0.020, 0.083),
    (Position.SB, Position.CO): (0.032, 0.096),
    (Position.BB, Position.UTG): (0.175, 0.051),
}


def get_study_view_data(request: dict) -> dict:
    hero_position = parse_position_name(str(request.get("hero_position", "")))
    hero_hand = parse_hand_text(str(request.get("hero_hand", "")))
    board_cards = parse_board_text(str(request.get("board_cards", "")), hero_hand)
    street = _street_name(str(request.get("street", "")), board_cards)
    simulations = int(request.get("simulations", 10000))
    action_history = action_history_from_dicts(request.get("action_history", []))
    auto_state = bool(request.get("auto_state", False)) and street == "preflop"
    derived_state = derive_preflop_state(hero_position, action_history)
    raise_amount_bb = float(request.get("raise_amount_bb", 0.0) or 0.0)
    pot_bb = derived_state.pot_size if auto_state else float(request.get("pot_bb", 0.0))
    call_amount_bb = derived_state.call_amount if auto_state else float(request.get("call_amount_bb", 0.0))
    active_opponent_count = (
        derived_state.active_opponent_count
        if auto_state
        else request.get("active_opponent_count")
    )
    opponent_count = int(active_opponent_count) if active_opponent_count is not None else 0
    range_simulations = _range_simulations(simulations, request)
    opponent_ranges = infer_opponent_ranges(hero_position, hero_hand, action_history)
    engaged_ranges = engaged_opponent_ranges(opponent_ranges, action_history)
    candidate_raise_amounts = _candidate_raise_amounts(request, raise_amount_bb)
    if not candidate_raise_amounts:
        candidate_raise_amounts = _auto_raise_amounts(hero_position, action_history, derived_state.current_bet)
        raise_amount_bb = candidate_raise_amounts[0] if candidate_raise_amounts else 0.0

    range_grid = _range_grid(
        hero_position=hero_position,
        hero_hand=hero_hand,
        pot_bb=pot_bb,
        call_amount_bb=call_amount_bb,
        raise_amount_bb=raise_amount_bb,
        candidate_raise_amounts=candidate_raise_amounts,
        board_cards=board_cards,
        action_history=action_history,
        opponent_ranges=opponent_ranges,
        engaged_ranges=engaged_ranges,
        fallback_opponent_count=opponent_count,
        simulations=range_simulations,
        hero_contribution=derived_state.contributions.get(hero_position, 0.0),
        current_bet=derived_state.current_bet,
    )
    selected_grid_item = next((item for item in range_grid if item["is_selected"]), range_grid[0])
    actions = _actions_from_grid_item(selected_grid_item)
    hand_actions = {
        item["name"]: item["frequency"]
        for item in actions
    }
    recommended_label = selected_grid_item["recommended"]
    selected_evs = selected_grid_item["evs"]
    node_explanation = (
        "Betting round is closed; the displayed strategy is retained for review."
        if derived_state.is_closed and auto_state
        else (
            f"Recommended {recommended_label.lower()} because it has the highest "
            f"estimated EV for {selected_grid_item['hand']} in the displayed strategy model."
        )
    )
    pot_odds = (
        call_amount_bb / (pot_bb + call_amount_bb) * 100.0
        if call_amount_bb > 0.0 and pot_bb + call_amount_bb > 0.0
        else 0.0
    )

    return {
        "mode": "study",
        "street": street,
        "hero_position": position_to_string(hero_position),
        "hero_hand": hand_to_text(hero_hand),
        "board_cards": cards_to_text(board_cards),
        "pot_bb": pot_bb,
        "call_amount_bb": call_amount_bb,
        "auto_state": auto_state,
        "betting_state": betting_state_to_dict(derived_state),
        "pot_odds": pot_odds,
        "candidate_raise_amounts": list(candidate_raise_amounts),
        "range_simulations": range_simulations,
        "opponent_ranges": range_summary_to_dict(opponent_ranges),
        "stacks": default_stacks(),
        "actions": actions,
        "selected_hand": {
            "hand": hand_to_text(hero_hand),
            "actions": hand_actions,
            "recommended": recommended_label,
            "equity": selected_grid_item["equity"],
            "ev": selected_grid_item["ev"],
        },
        "hand_cards": range_grid,
        "range_grid": range_grid,
        "legacy_selected_hand": [
            {
                "hand": hand_to_text(hero_hand),
                "actions": hand_actions,
                "recommended": recommended_label,
                "equity": selected_grid_item["equity"],
                "ev": selected_grid_item["ev"],
            }
        ],
        "metrics": {
            "equity": selected_grid_item["equity"],
            "win_rate": None,
            "tie_rate": None,
            "loss_rate": None,
            "ev_fold": selected_evs.get("Fold", 0.0),
            "ev_check": selected_evs.get("Check", 0.0),
            "ev_call": selected_evs.get("Call", 0.0),
            "ev_raise": selected_evs.get("Raise", 0.0),
            "equity_source": "range-aware Monte Carlo",
        },
        "explanation": node_explanation,
    }


def _actions_from_grid_item(item: dict) -> list[dict]:
    actions: list[dict] = []
    for name in ("Fold", "Call", "Check"):
        if name not in item["actions"]:
            continue
        actions.append(
            {
                "name": name,
                "frequency": item["actions"].get(name, 0.0),
                "ev": item["evs"].get(name, 0.0),
                "combos": None,
                "is_recommended": item["recommended"] == name,
            }
        )
    if item.get("raise_options"):
        for option in item["raise_options"]:
            actions.append(
                {
                    "name": option["label"],
                    "frequency": option["frequency"],
                    "ev": option["ev"],
                    "combos": None,
                    "is_recommended": item["recommended"] == "Raise" and option["is_best"],
                }
            )
    elif "Raise" in item["actions"]:
        actions.append(
            {
                "name": "Raise",
                "frequency": item["actions"].get("Raise", 0.0),
                "ev": item["evs"].get("Raise", 0.0),
                "combos": None,
                "is_recommended": item["recommended"] == "Raise",
            }
        )
    return actions


def _range_grid(
    hero_position,
    hero_hand,
    pot_bb: float,
    call_amount_bb: float,
    raise_amount_bb: float,
    candidate_raise_amounts: tuple[float, ...],
    board_cards: tuple[Card, ...],
    action_history,
    opponent_ranges,
    engaged_ranges,
    fallback_opponent_count: int,
    simulations: int,
    hero_contribution: float,
    current_bet: float,
) -> list[dict]:
    hero_class = get_hand_class(hero_hand).name
    dead_cards = set(board_cards)
    items: list[dict] = []
    for index, hand_class in enumerate(all_preflop_hand_classes()):
        row = index // 13
        col = index % 13
        frequency = get_preflop_frequency(hero_position, hand_class)
        representative = _representative_hand(hand_class, dead_cards)
        if engaged_ranges:
            equity = estimate_equity_against_ranges(
                representative,
                engaged_ranges,
                simulations,
                board_cards,
            )
        else:
            equity = estimate_preflop_equity(
                EquityInput(
                    hero_hand=representative,
                    opponent_count=fallback_opponent_count,
                    simulations=simulations,
                    board_cards=board_cards,
                )
            ).equity
        raise_amounts = candidate_raise_amounts or (raise_amount_bb,)
        action_values, _, _ = _preflop_action_profile(
            hero_position,
            hand_class,
            action_history,
            call_amount_bb,
            pot_bb,
            raise_amounts,
        )
        evs, raise_options = _action_evs_from_equity(
            action_values,
            equity,
            representative,
            opponent_ranges,
            board_cards,
            simulations,
            pot_bb,
            call_amount_bb,
            raise_amounts,
            hero_contribution,
            current_bet,
        )
        recommended = _recommended_action(action_values, evs)
        items.append(
            {
                "hand": hand_class.name,
                "row": row,
                "col": col,
                "suited": hand_class.suited,
                "pair": hand_class.pair,
                "actions": action_values,
                "evs": evs,
                "raise_options": raise_options,
                "recommended": recommended,
                "frequency": action_values.get(recommended, 0.0),
                "ev": evs[recommended],
                "equity": equity * 100.0,
                "representative_hand": hand_to_text(representative),
                "is_selected": hand_class.name == hero_class,
            }
        )
    return items


def _action_evs_from_equity(
    actions: dict[str, float],
    equity: float,
    hero_hand: HoleCards,
    opponent_ranges,
    board_cards: tuple[Card, ...],
    simulations: int,
    pot_bb: float,
    call_amount_bb: float,
    raise_amounts: tuple[float, ...],
    hero_contribution: float,
    current_bet: float,
) -> tuple[dict[str, float], list[dict]]:
    evs: dict[str, float] = {}
    if "Fold" in actions:
        evs["Fold"] = 0.0
    if "Check" in actions:
        evs["Check"] = equity * pot_bb
    if "Call" in actions:
        call_frequency = actions.get("Call", 0.0) / 100.0
        evs["Call"] = (
            equity * (pot_bb + call_amount_bb)
            - call_amount_bb
            - (1.0 - call_frequency) * call_amount_bb * 0.50
        )

    raise_evs: dict[str, float] = {}
    for raise_total in raise_amounts:
        if raise_total <= current_bet:
            continue
        continuing_ranges, fold_probability = continuing_ranges_for_raise(
            opponent_ranges,
            raise_total,
            current_bet,
        )
        called_equity = estimate_equity_against_ranges(
            hero_hand,
            single_caller_range(continuing_ranges),
            simulations,
            board_cards,
        )
        hero_investment = max(0.0, raise_total - hero_contribution)
        caller_investment = max(0.0, raise_total - current_bet)
        final_pot = pot_bb + hero_investment + caller_investment
        raw_raise_ev = (
            fold_probability * pot_bb
            + (1.0 - fold_probability) * (called_equity * final_pot - hero_investment)
        )
        raise_frequency = actions.get("Raise", 0.0) / 100.0
        raise_evs[_raise_label(raise_total)] = (
            raw_raise_ev
            - (1.0 - raise_frequency) * hero_investment * 0.55
        )
    if "Raise" in actions:
        evs["Raise"] = max(raise_evs.values(), default=-999.0)
    return evs, _raise_options(raise_evs, actions.get("Raise", 0.0))


def _preflop_action_profile(
    hero_position,
    hand_class,
    action_history,
    call_amount_bb: float,
    pot_bb: float,
    raise_amounts: tuple[float, ...],
) -> tuple[dict[str, float], dict[str, float], list[dict]]:
    score = hand_strength_score(hand_class)
    raise_count = sum(1 for record in action_history if record.action == Action.RAISE)
    if raise_count == 0:
        frequency = get_preflop_frequency(hero_position, hand_class)
        total_raise = frequency.raise_frequency * 100.0
        call_frequency = frequency.call_frequency * 100.0
        if call_amount_bb <= 0.0:
            actions = {
                "Check": max(0.0, 100.0 - total_raise),
                "Raise": total_raise,
            }
            evs = {
                "Check": max(0.0, (score - 35) / 18.0),
                "Raise": _best_raise_ev(score, _open_raise_threshold(hero_position), pot_bb, raise_amounts),
            }
        else:
            actions = {
                "Fold": max(0.0, 100.0 - call_frequency - total_raise),
                "Call": call_frequency,
                "Raise": total_raise,
            }
            evs = {
                "Fold": 0.0,
                "Call": (score - _defend_call_threshold(hero_position)) / 18.0 if call_frequency > 0.0 else -0.25,
                "Raise": _best_raise_ev(score, _open_raise_threshold(hero_position), pot_bb, raise_amounts),
            }
        return actions, evs, _raise_options_from_score(
            score,
            _open_raise_threshold(hero_position),
            pot_bb,
            raise_amounts,
            total_raise,
        )

    if call_amount_bb <= 0.0:
        raise_threshold = _open_raise_threshold(hero_position)
        total_raise = _frequency_from_threshold(score, raise_threshold)
        evs = {
            "Check": max(0.0, (score - 35) / 18.0),
            "Raise": _best_raise_ev(score, raise_threshold, pot_bb, raise_amounts),
        }
        actions = {
            "Check": 100.0 - total_raise,
            "Raise": total_raise,
        }
        return actions, evs, _raise_options_from_score(score, raise_threshold, pot_bb, raise_amounts, total_raise)

    if raise_count == 1:
        opener_position = next(
            record.position
            for record in action_history
            if record.action == Action.RAISE
        )
        return _single_open_action_profile(
            hero_position,
            opener_position,
            hand_class,
            call_amount_bb,
            pot_bb,
            raise_amounts,
        )
    else:
        call_threshold = _three_bet_call_threshold(hero_position)
        raise_threshold = _three_bet_raise_threshold(hero_position)

    total_raise = _frequency_from_threshold(score, raise_threshold)
    call_frequency = _call_frequency_from_threshold(score, call_threshold, total_raise)
    fold_frequency = max(0.0, 100.0 - call_frequency - total_raise)
    evs = {
        "Fold": 0.0,
        "Call": (score - call_threshold) / 14.0,
        "Raise": _best_raise_ev(score, raise_threshold, pot_bb, raise_amounts),
    }
    actions = {
        "Fold": fold_frequency,
        "Call": call_frequency,
        "Raise": total_raise,
    }
    return actions, evs, _raise_options_from_score(score, raise_threshold, pot_bb, raise_amounts, total_raise)


def _single_open_action_profile(
    hero_position: Position,
    opener_position: Position,
    hand_class,
    call_amount_bb: float,
    pot_bb: float,
    raise_amounts: tuple[float, ...],
) -> tuple[dict[str, float], dict[str, float], list[dict]]:
    context = _single_open_context(hero_position, opener_position)
    call_map, raise_map, call_boundary, raise_boundary = _single_open_strategy(context)
    call_frequency = call_map.get(hand_class.name, 0.0) * 100.0
    raise_frequency = raise_map.get(hand_class.name, 0.0) * 100.0
    fold_frequency = max(0.0, 100.0 - call_frequency - raise_frequency)

    call_score = _call_suitability(hand_class, context)
    raise_score = _raise_suitability(hand_class, context)
    pot_odds = call_amount_bb / max(0.01, pot_bb + call_amount_bb)
    position_realization = 0.08 if context.in_position else -0.08
    blind_discount = 0.10 if hero_position == Position.BB else 0.0
    call_ev = (call_score - call_boundary) / 18.0 + position_realization + blind_discount - pot_odds * 0.15
    raise_ev = (raise_score - raise_boundary) / 15.0 + pot_bb * 0.025
    evs = {
        "Fold": 0.0,
        "Call": call_ev,
        "Raise": raise_ev,
    }
    actions = {
        "Fold": fold_frequency,
        "Call": call_frequency,
        "Raise": raise_frequency,
    }
    return actions, evs, _raise_options_from_base_ev(
        raise_ev,
        raise_score,
        raise_amounts,
        raise_frequency,
    )


def _single_open_context(hero_position: Position, opener_position: Position) -> SingleOpenContext:
    targets = SINGLE_OPEN_TARGETS.get((hero_position, opener_position))
    if targets is None:
        targets = _estimated_single_open_targets(hero_position, opener_position)
    return SingleOpenContext(
        hero_position=hero_position,
        opener_position=opener_position,
        in_position=hero_position not in (Position.SB, Position.BB),
        call_target=targets[0],
        raise_target=targets[1],
    )


def _estimated_single_open_targets(hero_position: Position, opener_position: Position) -> tuple[float, float]:
    opener_lateness = int(opener_position) / int(Position.BTN)
    if hero_position == Position.BB:
        return 0.17 + opener_lateness * 0.16, 0.05 + opener_lateness * 0.03
    if hero_position == Position.SB:
        return 0.025 + opener_lateness * 0.025, 0.085 + opener_lateness * 0.025
    return 0.012 + opener_lateness * 0.018, 0.07 + opener_lateness * 0.025


@lru_cache(maxsize=None)
def _single_open_strategy(
    context: SingleOpenContext,
) -> tuple[dict[str, float], dict[str, float], float, float]:
    hand_classes = all_preflop_hand_classes()
    raise_scores = {
        hand_class.name: _raise_suitability(hand_class, context)
        for hand_class in hand_classes
    }
    raise_map, raise_boundary = _allocate_ranked_frequency(
        hand_classes,
        raise_scores,
        context.raise_target,
    )
    call_candidates = tuple(
        hand_class
        for hand_class in hand_classes
        if raise_map.get(hand_class.name, 0.0) < 1.0
    )
    call_scores = {
        hand_class.name: _call_suitability(hand_class, context)
        for hand_class in call_candidates
    }
    call_map, call_boundary = _allocate_ranked_frequency(
        call_candidates,
        call_scores,
        context.call_target,
        excluded=raise_map,
    )
    return call_map, raise_map, call_boundary, raise_boundary


def _allocate_ranked_frequency(
    hand_classes,
    scores: dict[str, float],
    target_fraction: float,
    excluded: dict[str, float] | None = None,
) -> tuple[dict[str, float], float]:
    excluded = excluded or {}
    target_combos = 1326.0 * max(0.0, min(1.0, target_fraction))
    selected: dict[str, float] = {}
    used_combos = 0.0
    boundary = min(scores.values(), default=0.0)
    candidates = sorted(
        hand_classes,
        key=lambda item: (scores[item.name], _hand_combo_count(item)),
        reverse=True,
    )
    for candidate in candidates:
        available_frequency = 1.0 - excluded.get(candidate.name, 0.0)
        if available_frequency <= 0.0:
            continue
        remaining = target_combos - used_combos
        if remaining <= 0.0:
            break
        combos = _hand_combo_count(candidate)
        frequency = min(available_frequency, remaining / combos)
        if frequency > 0.0:
            selected[candidate.name] = frequency
            used_combos += combos * frequency
            boundary = scores[candidate.name]
    return selected, boundary


def _call_suitability(hand_class, context: SingleOpenContext) -> float:
    high = hand_class.high_rank
    low = hand_class.low_rank
    gap = max(0, high - low - 1)
    score = high * 1.6 + low * 1.1
    if hand_class.pair:
        score += 28.0 + high
    if hand_class.suited:
        score += 12.0
    score += max(0.0, 10.0 - gap * 3.0)
    if high >= int(Rank.TEN) and low >= int(Rank.TEN):
        score += 5.0
    if high == int(Rank.ACE) and low <= int(Rank.FIVE) and hand_class.suited:
        score += 5.0
    if not hand_class.suited and not hand_class.pair and low < int(Rank.TEN):
        score -= 7.0
    if context.in_position:
        score += 5.0
    if context.hero_position == Position.BB:
        score += 9.0
        if hand_class.suited and gap <= 1:
            score += 6.0
    if context.opener_position in (Position.UTG, Position.HJ):
        score -= 3.0
    return score


def _raise_suitability(hand_class, context: SingleOpenContext) -> float:
    high = hand_class.high_rank
    low = hand_class.low_rank
    gap = max(0, high - low - 1)
    value_score = high * 1.8 + low * 1.2
    if hand_class.pair:
        if high >= int(Rank.TEN):
            value_score += 22.0 + high * 2.0
        else:
            value_score += 8.0 + high
    if high >= int(Rank.TEN) and low >= int(Rank.TEN):
        value_score += 7.0

    blocker_score = 0.0
    if high == int(Rank.ACE):
        blocker_score += 8.0
    elif high == int(Rank.KING):
        blocker_score += 4.0
    if hand_class.suited:
        blocker_score += 4.0
    if high == int(Rank.ACE) and low <= int(Rank.FIVE) and hand_class.suited:
        blocker_score += 12.0
    if hand_class.suited and gap <= 1:
        blocker_score += 3.0
    if not hand_class.suited and not hand_class.pair and low < int(Rank.TEN):
        blocker_score -= 8.0
    if context.opener_position in (Position.UTG, Position.HJ):
        blocker_score -= 2.0
        if (
            context.hero_position == Position.BB
            and hand_class.suited
            and high == int(Rank.KING)
            and low >= int(Rank.TEN)
        ):
            blocker_score -= 9.0
    return value_score + blocker_score


def _hand_combo_count(hand_class) -> int:
    if hand_class.pair:
        return 6
    return 4 if hand_class.suited else 12


def _recommended_action(actions: dict[str, float], evs: dict[str, float]) -> str:
    legal_names = [name for name in actions if name in evs]
    return max(legal_names, key=lambda name: evs[name]) if legal_names else max(evs, key=evs.get)


def _open_raise_threshold(position) -> int:
    return {
        "UTG": 66,
        "HJ": 62,
        "CO": 56,
        "BTN": 45,
        "SB": 50,
        "BB": 62,
    }.get(position_to_string(position), 62)


def _defend_call_threshold(position) -> int:
    return {
        "UTG": 70,
        "HJ": 64,
        "CO": 58,
        "BTN": 54,
        "SB": 58,
        "BB": 42,
    }.get(position_to_string(position), 60)


def _defend_raise_threshold(position) -> int:
    return {
        "UTG": 82,
        "HJ": 80,
        "CO": 78,
        "BTN": 76,
        "SB": 78,
        "BB": 75,
    }.get(position_to_string(position), 78)


def _three_bet_call_threshold(position) -> int:
    return {
        "UTG": 78,
        "HJ": 76,
        "CO": 74,
        "BTN": 72,
        "SB": 74,
        "BB": 73,
    }.get(position_to_string(position), 74)


def _three_bet_raise_threshold(position) -> int:
    return {
        "UTG": 86,
        "HJ": 84,
        "CO": 83,
        "BTN": 82,
        "SB": 83,
        "BB": 82,
    }.get(position_to_string(position), 83)


def _frequency_from_threshold(score: int, threshold: int) -> float:
    if score >= threshold + 10:
        return 100.0
    if score >= threshold + 6:
        return 75.0
    if score >= threshold + 3:
        return 45.0
    if score >= threshold:
        return 20.0
    return 0.0


def _call_frequency_from_threshold(score: int, threshold: int, raise_frequency: float) -> float:
    if score < threshold:
        return 0.0
    if score >= threshold + 10:
        return max(0.0, 100.0 - raise_frequency)
    if score >= threshold + 5:
        return max(0.0, 75.0 - raise_frequency * 0.35)
    return max(0.0, 35.0 - raise_frequency * 0.25)


def _best_raise_ev(score: int, threshold: int, pot_bb: float, raise_amounts: tuple[float, ...]) -> float:
    raise_evs = _raise_option_evs_from_score(score, threshold, pot_bb, raise_amounts)
    if not raise_evs:
        return -999.0
    return max(raise_evs.values())


def _raise_option_evs_from_score(score: int, threshold: int, pot_bb: float, raise_amounts: tuple[float, ...]) -> dict[str, float]:
    clean_amounts = tuple(amount for amount in raise_amounts if amount > 0.0)
    if not clean_amounts:
        return {}
    min_amount = min(clean_amounts)
    evs = {}
    for amount in clean_amounts:
        size_ratio = (amount - min_amount) / max(1.0, min_amount)
        premium_bonus = max(0.0, score - 80) / 35.0 * size_ratio
        marginal_penalty = max(0.0, 78 - score) / 30.0 * size_ratio
        evs[_raise_label(amount)] = (score - threshold) / 10.0 + pot_bb * 0.03 + premium_bonus - marginal_penalty
    return evs


def _raise_options_from_score(
    score: int,
    threshold: int,
    pot_bb: float,
    raise_amounts: tuple[float, ...],
    total_raise_frequency: float,
) -> list[dict]:
    raise_evs = _raise_option_evs_from_score(score, threshold, pot_bb, raise_amounts)
    return _raise_options(raise_evs, total_raise_frequency)


def _raise_options_from_base_ev(
    base_ev: float,
    raise_score: float,
    raise_amounts: tuple[float, ...],
    total_raise_frequency: float,
) -> list[dict]:
    clean_amounts = tuple(amount for amount in raise_amounts if amount > 0.0)
    if not clean_amounts:
        return []
    min_amount = min(clean_amounts)
    raise_evs = {}
    for amount in clean_amounts:
        size_ratio = (amount - min_amount) / max(1.0, min_amount)
        premium_bonus = max(0.0, raise_score - 70.0) / 30.0 * size_ratio
        bluff_penalty = max(0.0, 65.0 - raise_score) / 24.0 * size_ratio
        raise_evs[_raise_label(amount)] = base_ev + premium_bonus - bluff_penalty
    return _raise_options(raise_evs, total_raise_frequency)


def _raise_options(raise_evs: dict[str, float], total_raise_frequency: float) -> list[dict]:
    frequencies = mixed_frequencies_from_named_evs(raise_evs)
    best_label = _best_raise_label(raise_evs)
    return [
        {
            "amount": float(label.split(" ", 1)[1]),
            "label": label,
            "ev": ev,
            "frequency": frequencies.get(label, 0.0) / 100.0 * total_raise_frequency,
            "is_best": label == best_label,
        }
        for label, ev in raise_evs.items()
    ]


def _best_raise_label(raise_evs: dict[str, float]) -> str:
    if not raise_evs:
        return "Raise 0.0"
    return max(raise_evs, key=lambda label: raise_evs[label])


def _raise_label(amount: float) -> str:
    return f"Raise {amount:.1f}"


def _range_simulations(simulations: int, request: dict) -> int:
    explicit = request.get("range_simulations")
    if explicit is not None:
        return max(20, min(1000, int(explicit)))
    return max(20, min(120, simulations // 20 if simulations > 0 else 20))


def _auto_raise_amounts(hero_position, action_history, current_bet: float) -> tuple[float, ...]:
    raise_count = sum(1 for record in action_history if record.action == Action.RAISE)
    if raise_count == 0:
        if hero_position == Position.SB:
            return (3.5,)
        return (2.5,)
    if raise_count == 1:
        multiplier = 4.0 if hero_position in (Position.SB, Position.BB) else 3.0
        main_size = max(current_bet + 1.0, current_bet * multiplier)
        small_size = max(current_bet + 1.0, current_bet * (multiplier - 0.5))
        return tuple(sorted({round(min(100.0, small_size), 1), round(min(100.0, main_size), 1)}))
    main_size = max(current_bet + 1.0, current_bet * 2.25)
    jam_size = 100.0 if current_bet >= 12.0 else 0.0
    sizes = {round(min(100.0, main_size), 1)}
    if jam_size:
        sizes.add(jam_size)
    return tuple(sorted(sizes))


def _candidate_raise_amounts(request: dict, fallback_raise_amount: float) -> tuple[float, ...]:
    explicit = request.get("candidate_raise_amounts")
    values: list[float] = []
    if isinstance(explicit, (list, tuple)):
        values.extend(float(value) for value in explicit)
    elif isinstance(explicit, str) and explicit.strip():
        for chunk in explicit.replace(";", ",").split(","):
            value = chunk.strip()
            if value:
                values.append(float(value))
    if not values and fallback_raise_amount > 0.0:
        values.append(fallback_raise_amount)
    return tuple(sorted({round(value, 2) for value in values if value > 0.0}))


def _representative_hand(hand_class, dead_cards: set[Card]) -> HoleCards:
    high = Rank(hand_class.high_rank)
    low = Rank(hand_class.low_rank)
    suits = (Suit.SPADES, Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS)
    if hand_class.pair:
        for first_index, first_suit in enumerate(suits):
            for second_suit in suits[first_index + 1:]:
                hand = HoleCards(
                    Card(rank=high, suit=first_suit),
                    Card(rank=low, suit=second_suit),
                )
                if hand.card1 not in dead_cards and hand.card2 not in dead_cards:
                    return hand
    if hand_class.suited:
        for suit in suits:
            hand = HoleCards(
                Card(rank=high, suit=suit),
                Card(rank=low, suit=suit),
            )
            if hand.card1 not in dead_cards and hand.card2 not in dead_cards:
                return hand
    for high_suit in suits:
        for low_suit in suits:
            if high_suit == low_suit:
                continue
            hand = HoleCards(
                Card(rank=high, suit=high_suit),
                Card(rank=low, suit=low_suit),
            )
            if hand.card1 not in dead_cards and hand.card2 not in dead_cards:
                return hand
    raise ValueError(f"no representative hand available for {hand_class.name}")


def _street_name(requested: str, board_cards: tuple[Card, ...]) -> str:
    value = requested.strip().lower()
    if value in {"preflop", "flop", "turn", "river"}:
        return value
    return {
        0: "preflop",
        3: "flop",
        4: "turn",
        5: "river",
    }.get(len(board_cards), "custom")


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
