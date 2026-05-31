#ifndef RANGE_H
#define RANGE_H

#include "common.h"

typedef struct {
    char name[4];
    int high_rank;
    int low_rank;
    int suited;
    int pair;
} HandClass;

typedef struct {
    double open_frequency;
    double call_frequency;
    double raise_frequency;
} RangeActionFrequency;

HandClass get_hand_class(HoleCards hand);
RangeActionFrequency get_preflop_frequency(Position pos, HandClass hand_class);
int is_hand_in_open_range(Position pos, HandClass hand_class);
int players_behind_count(Position pos);
double estimate_open_fold_probability(Position hero_position, HoleCards hero_hand, double pot_size, double raise_amount);
const char *position_to_string(Position pos);
const char *opening_range_summary(Position pos);

#endif
