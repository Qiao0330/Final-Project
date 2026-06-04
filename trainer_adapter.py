from __future__ import annotations

from itertools import count

from adapter_utils import action_record_to_dict, action_to_label, default_stacks, hand_to_text
from common import Action, Position
from range_model import position_to_string
from trainer import (
    DEFAULT_SIMULATIONS,
    SCENARIO_FACING_3BET,
    SCENARIO_FACING_4BET,
    SCENARIO_FACING_OPEN,
    SCENARIO_OPEN_FIRST,
    TrainerOptionResult,
    evaluate_trainer_answer,
    generate_random_scenario,
)


_QUESTION_COUNTER = count(1)
_QUESTIONS: dict[str, tuple[object, int]] = {}


def get_trainer_question(settings: dict | None = None) -> dict:
    settings = settings or {}
    simulations = int(settings.get("simulations", DEFAULT_SIMULATIONS))
    scenario_type_filter = _scenario_type_filter(settings)
    scenario = generate_random_scenario(scenario_type_filter)
    question_id = f"q_{next(_QUESTION_COUNTER):04d}"
    _QUESTIONS[question_id] = (scenario, simulations)

    available_actions = _available_action_labels(scenario.options)
    first_raise = next((option.total_bet for option in scenario.options if option.action == Action.RAISE), 0.0)

    return {
        "question_id": question_id,
        "mode": "trainer",
        "street": "preflop",
        "scenario_type": scenario.scenario_type,
        "hero_position": position_to_string(scenario.hero_position),
        "hero_hand": hand_to_text(scenario.hero_hand),
        "opener_position": _position_or_none(scenario.opener_position),
        "open_size_bb": scenario.open_size,
        "three_bettor_position": _position_or_none(scenario.three_bettor_position),
        "three_bet_size_bb": scenario.three_bet_size,
        "four_bettor_position": _position_or_none(scenario.four_bettor_position),
        "four_bet_size_bb": scenario.four_bet_size,
        "pot_bb": scenario.pot_size,
        "call_amount_bb": scenario.call_amount,
        "raise_amount_bb": first_raise,
        "action_history": [
            action_record_to_dict(record)
            for record in scenario.table_actions
        ],
        "available_actions": available_actions,
        "stacks": default_stacks(),
    }


def grade_trainer_answer(question_id: str, user_action: str) -> dict:
    stored = _QUESTIONS.get(question_id)
    if stored is None:
        raise ValueError(f"unknown question_id: {question_id}")

    scenario, simulations = stored
    answer = evaluate_trainer_answer(scenario, 0, simulations)
    aggregated = _aggregate_results(answer.option_results)
    correct_action, best_result = max(aggregated.items(), key=lambda item: item[1].ev)
    normalized_user_action = _normalize_action_label(user_action)
    selected_result = aggregated.get(normalized_user_action)
    if selected_result is None:
        raise ValueError(f"action is not available for this question: {user_action}")

    is_correct = normalized_user_action == correct_action
    score = _score_answer(selected_result.ev, best_result.ev, is_correct)

    return {
        "question_id": question_id,
        "scenario_type": scenario.scenario_type,
        "user_action": normalized_user_action,
        "correct_action": correct_action,
        "is_correct": is_correct,
        "score": score,
        "actions": [
            {
                "name": label,
                "frequency": 100.0 if label == correct_action else 0.0,
                "ev": result.ev,
                "is_best": label == correct_action,
            }
            for label, result in aggregated.items()
        ],
        "feedback": (
            f"{correct_action} has the best chip EV in this preflop trainer spot. "
            f"Your action was {normalized_user_action}."
        ),
        "metrics": {
            "equity": best_result.equity * 100.0,
            "ev_fold": aggregated.get("Fold").ev if "Fold" in aggregated else 0.0,
            "ev_call": aggregated.get("Call").ev if "Call" in aggregated else 0.0,
            "ev_raise": _best_prefixed_ev(aggregated, "Raise"),
            "ev_all_in": aggregated.get("All-in").ev if "All-in" in aggregated else 0.0,
        },
    }


def _scenario_type_filter(settings: dict) -> str | None:
    value = str(
        settings.get("scenario_type")
        or settings.get("training_mode")
        or settings.get("mode_filter")
        or ""
    ).strip().lower().replace("-", "_")
    if value in ("", "random", "any", "all"):
        return None
    aliases = {
        "open": SCENARIO_OPEN_FIRST,
        "open_first": SCENARIO_OPEN_FIRST,
        "rfi": SCENARIO_OPEN_FIRST,
        "facing_open": SCENARIO_FACING_OPEN,
        "vs_open": SCENARIO_FACING_OPEN,
        "defend": SCENARIO_FACING_OPEN,
        "facing_3bet": SCENARIO_FACING_3BET,
        "facing_3_bet": SCENARIO_FACING_3BET,
        "vs_3bet": SCENARIO_FACING_3BET,
        "vs_3_bet": SCENARIO_FACING_3BET,
        "facing_4bet": SCENARIO_FACING_4BET,
        "facing_4_bet": SCENARIO_FACING_4BET,
        "vs_4bet": SCENARIO_FACING_4BET,
        "vs_4_bet": SCENARIO_FACING_4BET,
    }
    if value not in aliases:
        raise ValueError(f"unknown trainer scenario_type: {value}")
    return aliases[value]


def _position_or_none(position) -> str | None:
    return None if position == Position.INVALID else position_to_string(position)


def _available_action_labels(options) -> list[str]:
    labels: list[str] = []
    for option in options:
        label = _option_label(option)
        if label not in labels:
            labels.append(label)
    return labels


def _aggregate_results(results: tuple[TrainerOptionResult, ...]) -> dict[str, TrainerOptionResult]:
    aggregated: dict[str, TrainerOptionResult] = {}
    for result in results:
        label = _option_label(result.option)
        current = aggregated.get(label)
        if current is None or result.ev > current.ev:
            aggregated[label] = result
    return aggregated


def _option_label(option) -> str:
    return action_to_label(option.action, option.total_bet if option.action == Action.RAISE else 0.0)


def _normalize_action_label(text: str) -> str:
    value = str(text).strip().lower()
    if value in ("fold",):
        return "Fold"
    if value in ("call",):
        return "Call"
    if value == "raise" or value.startswith("raise "):
        return " ".join(part.capitalize() if index == 0 else part for index, part in enumerate(str(text).strip().split()))
    if value in ("all-in", "allin", "all in", "all-in 100 bb"):
        return "All-in"
    if value in ("check",):
        return "Check"
    raise ValueError(f"unknown action: {text}")


def _best_prefixed_ev(results: dict[str, TrainerOptionResult], prefix: str) -> float:
    values = [
        result.ev for label, result in results.items()
        if label == prefix or label.startswith(f"{prefix} ")
    ]
    return max(values) if values else 0.0


def _score_answer(selected_ev: float, best_ev: float, is_correct: bool) -> int:
    if is_correct:
        return 100
    ev_gap = max(0.0, best_ev - selected_ev)
    return max(0, min(99, round(100 - ev_gap * 25)))
