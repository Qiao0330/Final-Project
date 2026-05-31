#ifndef RANGE_H
#define RANGE_H

#include "common.h"

typedef struct {
    char name[4];
} HandClass;

typedef struct {
    double open_frequency;
    double call_frequency;
    double raise_frequency;
} RangeActionFrequency;

HandClass get_hand_class(HoleCards hand);
int is_hand_in_open_range(Position pos, HandClass hand_class);
RangeActionFrequency get_preflop_frequency(Position pos, HandClass hand_class);
const char *position_to_string(Position pos);

#endif
