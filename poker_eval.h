#ifndef POKER_EVAL_H
#define POKER_EVAL_H

#include "common.h"

typedef enum {
    HAND_HIGH_CARD = 0,
    HAND_ONE_PAIR,
    HAND_TWO_PAIR,
    HAND_THREE_OF_A_KIND,
    HAND_STRAIGHT,
    HAND_FLUSH,
    HAND_FULL_HOUSE,
    HAND_FOUR_OF_A_KIND,
    HAND_STRAIGHT_FLUSH
} HandCategory;

typedef struct {
    HandCategory category;
    int tie_breakers[5];
} HandValue;

HandValue evaluate_7cards(const Card cards[7]);
int compare_hand_values(HandValue a, HandValue b);
const char *hand_category_to_string(HandCategory category);

#endif
