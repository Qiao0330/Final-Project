from __future__ import annotations

from itertools import count

from adapter_utils import action_to_label, hand_to_text
from card import card_to_string
from common import Action
from flop_trainer import (
    POT_3BET,
    POT_4BET,
    POT_5BET,
    POT_SINGLE_RAISED,
    FlopAnswer,
    FlopOption,
    FlopOptionResult,
    FlopScenario,
    _analyze_flop_texture,
    evaluate_flop_answer,
    generate_random_flop_scenario,
)
from range_model import position_to_string


_FLOP_QUESTION_COUNTER = count(1)
_FLOP_QUESTIONS: dict[str, FlopScenario] = {}


def get_flop_trainer_question(settings: dict | None = None) -> dict:
    settings = settings or {}
    scenario = _generate_flop_scenario(settings)
    question_id = f"fq_{next(_FLOP_QUESTION_COUNTER):04d}"
    _FLOP_QUESTIONS[question_id] = scenario

    return {
        "question_id": question_id,
        "mode": "trainer",
        "street": "flop",
        "scenario_type": _scenario_type(scenario),
        "hero_position": position_to_string(scenario.hero_table_position),
        "hero_table_position": position_to_string(scenario.hero_table_position),
        "hero_relative_position": scenario.hero_position,
        "opponent_position": position_to_string(scenario.opponent_position),
        "pfa_position": position_to_string(scenario.pfa_position),
        "defender_position": position_to_string(scenario.defender_position),
        "hero_role": scenario.hero_role,
        "hero_hand": hand_to_text(scenario.hero_hand),
        "flop": _cards_text(scenario.flop),
        "flop_cards": [card_to_string(card) for card in scenario.flop],
        "pot_type": scenario.pot_type,
        "pot_bb": scenario.pot_size,
        "call_amount_bb": scenario.pfa_bet_size if scenario.pfa_action == "bet" else 0.0,
        "pfa_action": scenario.pfa_action or None,
        "pfa_bet_size_bb": scenario.pfa_bet_size if scenario.pfa_action == "bet" else 0.0,
        "preflop_summary": scenario.preflop_summary,
        "remaining_stack_bb": scenario.remaining_stack,
        "available_actions": [
            _option_label(option)
            for option in scenario.options
        ],
        "options": [
            _option_to_dict(index, option)
            for index, option in enumerate(scenario.options)
        ],
        "action_history": [
            {
                "position": "Preflop",
                "action": scenario.preflop_summary,
                "amount": 0.0,
            }
        ],
    }


def grade_flop_trainer_answer(question_id: str, user_action: str) -> dict:
    scenario = _FLOP_QUESTIONS.get(question_id)
    if scenario is None:
        raise ValueError(f"unknown flop question_id: {question_id}")

    selected_index = _selected_option_index(scenario.options, user_action)
    answer = evaluate_flop_answer(scenario, selected_index)
    selected = answer.option_results[selected_index]
    best = answer.option_results[answer.best_index]

    return {
        "question_id": question_id,
        "street": "flop",
        "scenario_type": _scenario_type(scenario),
        "user_action": _option_label(selected.option),
        "correct_action": _option_label(best.option),
        "accepted_actions": [
            _option_label(answer.option_results[index].option)
            for index in answer.acceptable_indices
        ],
        "is_correct": answer.is_correct,
        "score": _score_answer(selected.estimated_ev, best.estimated_ev, answer.is_correct),
        "actions": [
            _result_to_action_dict(index, result, answer)
            for index, result in enumerate(answer.option_results)
        ],
        "feedback": _feedback(answer, selected, best),
        "metrics": {
            "equity": answer.estimated_equity * 100.0,
            "range_advantage": answer.range_analysis.range_advantage,
            "nut_advantage": answer.range_analysis.nut_advantage,
            "hero_strong_density": answer.range_analysis.hero.strong_hand_density * 100.0,
            "opponent_strong_density": answer.range_analysis.opponent.strong_hand_density * 100.0,
            "hero_draw_density": answer.range_analysis.hero.draw_density * 100.0,
            "opponent_draw_density": answer.range_analysis.opponent.draw_density * 100.0,
        },
        "texture": {
            "summary": _texture_summary(answer),
            "board_texture": _texture_board(answer),
        },
    }


def _generate_flop_scenario(settings: dict) -> FlopScenario:
    pot_type = _pot_type_filter(settings)
    for _ in range(200):
        scenario = generate_random_flop_scenario()
        if pot_type is not None and scenario.pot_type != pot_type:
            continue
        if scenario.options:
            return scenario
    return generate_random_flop_scenario()


def _pot_type_filter(settings: dict) -> str | None:
    value = str(settings.get("pot_type") or settings.get("scenario_type") or "random")
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in ("", "random", "all", "any"):
        return None
    aliases = {
        "single_raised": POT_SINGLE_RAISED,
        "single_raised_pot": POT_SINGLE_RAISED,
        "srp": POT_SINGLE_RAISED,
        "3bet": POT_3BET,
        "3_bet": POT_3BET,
        "3bet_pot": POT_3BET,
        "3_bet_pot": POT_3BET,
        "4bet": POT_4BET,
        "4_bet": POT_4BET,
        "4bet_pot": POT_4BET,
        "4_bet_pot": POT_4BET,
        "5bet": POT_5BET,
        "5_bet": POT_5BET,
        "5bet_pot": POT_5BET,
        "5_bet_pot": POT_5BET,
    }
    if normalized not in aliases:
        raise ValueError(f"unknown flop pot_type: {value}")
    return aliases[normalized]


def _scenario_type(scenario: FlopScenario) -> str:
    return str(scenario.pot_type).lower().replace("-", "").replace(" ", "_")


def _cards_text(cards) -> str:
    return "".join(card_to_string(card) for card in cards)


def _option_to_dict(index: int, option: FlopOption) -> dict:
    return {
        "index": index,
        "label": _option_label(option),
        "action": _action_name(option.action),
        "amount": option.amount,
    }


def _result_to_action_dict(index: int, result: FlopOptionResult, answer: FlopAnswer) -> dict:
    return {
        "index": index,
        "name": _option_label(result.option),
        "frequency": 100.0 if index in answer.acceptable_indices else 0.0,
        "ev": result.estimated_ev,
        "score": result.score,
        "reason": result.reason,
        "is_best": index == answer.best_index,
        "is_acceptable": index in answer.acceptable_indices,
    }


def _selected_option_index(options: tuple[FlopOption, ...], user_action: str) -> int:
    normalized = str(user_action).strip()
    for index, option in enumerate(options):
        if normalized == _option_label(option):
            return index
    raise ValueError(f"action is not available for this flop question: {user_action}")


def _option_label(option: FlopOption) -> str:
    if option.action == Action.RAISE:
        return option.label
    return option.label or action_to_label(option.action, option.amount)


def _action_name(action: Action) -> str:
    return {
        Action.FOLD: "fold",
        Action.CALL: "call",
        Action.RAISE: "raise",
        Action.CHECK: "check",
    }.get(action, "unknown")


def _feedback(answer: FlopAnswer, selected: FlopOptionResult, best: FlopOptionResult) -> str:
    accepted = ", ".join(
        _option_label(answer.option_results[index].option)
        for index in answer.acceptable_indices
    )
    return (
        f"{_option_label(best.option)} has the highest estimated EV on this flop. "
        f"Accepted choices: {accepted}. "
        f"Your action was {_option_label(selected.option)}."
    )


def _texture_summary(answer: FlopAnswer) -> str:
    texture = _analyze_flop_texture(answer.scenario.hero_hand, answer.scenario.flop)
    return texture.summary


def _texture_board(answer: FlopAnswer) -> str:
    texture = _analyze_flop_texture(answer.scenario.hero_hand, answer.scenario.flop)
    return texture.board_texture


def _score_answer(selected_ev: float, best_ev: float, is_correct: bool) -> int:
    if is_correct:
        return 100
    ev_gap = max(0.0, best_ev - selected_ev)
    return max(0, min(99, round(100 - ev_gap * 18)))
