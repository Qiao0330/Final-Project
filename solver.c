#include "solver.h"

#include <stdio.h>

static double clamp_probability(double value) {
    if (value < 0.0) {
        return 0.0;
    }
    if (value > 1.0) {
        return 1.0;
    }
    return value;
}

SolverResult solve_preflop_decision(SolverInput input) {
    SolverResult result;
    EquityInput equity_input;
    double final_pot_call;
    double final_pot_raise;
    double fold_probability;
    double best_action_ev;

    equity_input.hero_hand = input.hero_hand;
    equity_input.opponent_count = players_behind_count(input.hero_position);
    equity_input.simulations = input.simulations;

    result.hero_position = input.hero_position;
    result.opponent_count = equity_input.opponent_count;
    result.hand_class = get_hand_class(input.hero_hand);
    result.range_frequency = get_preflop_frequency(input.hero_position, result.hand_class);
    result.equity_result = estimate_preflop_equity(equity_input);
    result.equity = result.equity_result.equity;

    fold_probability =
        estimate_open_fold_probability(
            input.hero_position,
            input.hero_hand,
            input.pot_size,
            input.raise_amount
        );
    result.fold_probability = clamp_probability(fold_probability);
    fold_probability = result.fold_probability;
    final_pot_call = input.pot_size + input.call_amount;
    final_pot_raise = input.pot_size + input.raise_amount;

    result.ev_fold = 0.0;
    if (input.call_amount > 0.0) {
        result.ev_call = result.equity * final_pot_call - input.call_amount;
    } else {
        result.ev_call = 0.0;
    }
    result.ev_raise =
        fold_probability * input.pot_size +
        (1.0 - fold_probability) *
            (result.equity * final_pot_raise - input.raise_amount);

    best_action_ev = result.ev_call;
    result.recommendation = ACTION_CALL;

    if (result.ev_raise >= best_action_ev) {
        best_action_ev = result.ev_raise;
        result.recommendation = ACTION_RAISE;
    }

    if (best_action_ev <= 0.0) {
        result.recommendation = ACTION_FOLD;
    } else if (result.recommendation == ACTION_CALL && result.ev_call > result.ev_raise) {
        result.recommendation = ACTION_CALL;
    } else {
        result.recommendation = ACTION_RAISE;
    }

    snprintf(
        result.explanation,
        sizeof(result.explanation),
        "Hand class %s has %.0f%% opening frequency from this position. Future fold probability is estimated from opponents' EV versus this position's open range. Recommended %s because it is the highest positive EV action.",
        result.hand_class.name,
        result.range_frequency.open_frequency * 100.0,
        action_to_string(result.recommendation)
    );

    return result;
}

const char *action_to_string(Action action) {
    switch (action) {
        case ACTION_FOLD: return "fold";
        case ACTION_CALL: return "call";
        case ACTION_RAISE: return "raise";
        default: return "unknown";
    }
}
