#ifndef EQUITY_H
#define EQUITY_H

#include "common.h"

typedef struct {
    int simulations;
    int wins;
    int ties;
    int losses;
    double win_rate;
    double tie_rate;
    double loss_rate;
    double equity;
} EquityResult;

typedef struct {
    HoleCards hero_hand;
    int opponent_count;
    int simulations;
} EquityInput;

EquityResult estimate_preflop_equity(EquityInput input);

#endif
