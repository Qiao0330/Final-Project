#ifndef SOLVER_H
#define SOLVER_H

#include "common.h"
#include "equity.h"
#include "range.h"

typedef struct {
    Position hero_position;
    HoleCards hero_hand;
    double pot_size;
    double call_amount;
    double raise_amount;
    int simulations;
} SolverInput;

typedef struct {
    EquityResult equity_result;
    Position hero_position;
    int opponent_count;
    double fold_probability;
    HandClass hand_class;
    RangeActionFrequency range_frequency;
    double equity;
    double ev_fold;
    double ev_call;
    double ev_raise;
    Action recommendation;
    char explanation[256];
} SolverResult;

SolverResult solve_preflop_decision(SolverInput input);
const char *action_to_string(Action action);

#endif
