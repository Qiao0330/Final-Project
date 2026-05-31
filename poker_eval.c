#include "poker_eval.h"

#include <string.h>

static void clear_value(HandValue *value) {
    int i;

    value->category = HAND_HIGH_CARD;
    for (i = 0; i < 5; i++) {
        value->tie_breakers[i] = 0;
    }
}

static int compare_int_desc(const void *left, const void *right) {
    int a = *(const int *)left;
    int b = *(const int *)right;
    return b - a;
}

static void sort_desc(int values[], int count) {
    int i;
    int j;

    for (i = 0; i < count - 1; i++) {
        for (j = i + 1; j < count; j++) {
            if (compare_int_desc(&values[i], &values[j]) > 0) {
                int temp = values[i];
                values[i] = values[j];
                values[j] = temp;
            }
        }
    }
}

static int straight_high_card(const int rank_count[15]) {
    int high;

    for (high = RANK_A; high >= RANK_6; high--) {
        if (rank_count[high] &&
            rank_count[high - 1] &&
            rank_count[high - 2] &&
            rank_count[high - 3] &&
            rank_count[high - 4]) {
            return high;
        }
    }

    if (rank_count[RANK_A] &&
        rank_count[RANK_5] &&
        rank_count[RANK_4] &&
        rank_count[RANK_3] &&
        rank_count[RANK_2]) {
        return RANK_5;
    }

    return 0;
}

static HandValue evaluate_5cards(const Card cards[5]) {
    HandValue value;
    int rank_count[15] = {0};
    int suit_count[4] = {0};
    int ranks[5];
    int kickers[5];
    int pair_ranks[2];
    int straight_high;
    int flush;
    int four = 0;
    int three = 0;
    int pair_count = 0;
    int kicker_count = 0;
    int i;
    int rank;

    clear_value(&value);

    for (i = 0; i < 5; i++) {
        rank_count[cards[i].rank]++;
        suit_count[cards[i].suit]++;
        ranks[i] = cards[i].rank;
    }

    sort_desc(ranks, 5);
    flush = suit_count[cards[0].suit] == 5;
    straight_high = straight_high_card(rank_count);

    if (flush && straight_high) {
        value.category = HAND_STRAIGHT_FLUSH;
        value.tie_breakers[0] = straight_high;
        return value;
    }

    for (rank = RANK_A; rank >= RANK_2; rank--) {
        if (rank_count[rank] == 4) {
            four = rank;
        } else if (rank_count[rank] == 3) {
            three = rank;
        } else if (rank_count[rank] == 2) {
            pair_ranks[pair_count++] = rank;
        } else if (rank_count[rank] == 1) {
            kickers[kicker_count++] = rank;
        }
    }

    if (four) {
        value.category = HAND_FOUR_OF_A_KIND;
        value.tie_breakers[0] = four;
        value.tie_breakers[1] = kickers[0];
        return value;
    }

    if (three && pair_count > 0) {
        value.category = HAND_FULL_HOUSE;
        value.tie_breakers[0] = three;
        value.tie_breakers[1] = pair_ranks[0];
        return value;
    }

    if (flush) {
        value.category = HAND_FLUSH;
        memcpy(value.tie_breakers, ranks, sizeof(ranks));
        return value;
    }

    if (straight_high) {
        value.category = HAND_STRAIGHT;
        value.tie_breakers[0] = straight_high;
        return value;
    }

    if (three) {
        value.category = HAND_THREE_OF_A_KIND;
        value.tie_breakers[0] = three;
        value.tie_breakers[1] = kickers[0];
        value.tie_breakers[2] = kickers[1];
        return value;
    }

    if (pair_count == 2) {
        value.category = HAND_TWO_PAIR;
        value.tie_breakers[0] = pair_ranks[0];
        value.tie_breakers[1] = pair_ranks[1];
        value.tie_breakers[2] = kickers[0];
        return value;
    }

    if (pair_count == 1) {
        value.category = HAND_ONE_PAIR;
        value.tie_breakers[0] = pair_ranks[0];
        value.tie_breakers[1] = kickers[0];
        value.tie_breakers[2] = kickers[1];
        value.tie_breakers[3] = kickers[2];
        return value;
    }

    value.category = HAND_HIGH_CARD;
    memcpy(value.tie_breakers, ranks, sizeof(ranks));
    return value;
}

HandValue evaluate_7cards(const Card cards[7]) {
    HandValue best;
    int initialized = 0;
    int a;
    int b;
    int c;
    int d;
    int e;

    clear_value(&best);

    for (a = 0; a < 3; a++) {
        for (b = a + 1; b < 4; b++) {
            for (c = b + 1; c < 5; c++) {
                for (d = c + 1; d < 6; d++) {
                    for (e = d + 1; e < 7; e++) {
                        Card combo[5] = {
                            cards[a], cards[b], cards[c], cards[d], cards[e]
                        };
                        HandValue current = evaluate_5cards(combo);

                        if (!initialized || compare_hand_values(current, best) > 0) {
                            best = current;
                            initialized = 1;
                        }
                    }
                }
            }
        }
    }

    return best;
}

int compare_hand_values(HandValue a, HandValue b) {
    int i;

    if (a.category > b.category) {
        return 1;
    }
    if (a.category < b.category) {
        return -1;
    }

    for (i = 0; i < 5; i++) {
        if (a.tie_breakers[i] > b.tie_breakers[i]) {
            return 1;
        }
        if (a.tie_breakers[i] < b.tie_breakers[i]) {
            return -1;
        }
    }

    return 0;
}

const char *hand_category_to_string(HandCategory category) {
    switch (category) {
        case HAND_STRAIGHT_FLUSH: return "Straight flush";
        case HAND_FOUR_OF_A_KIND: return "Four of a kind";
        case HAND_FULL_HOUSE: return "Full house";
        case HAND_FLUSH: return "Flush";
        case HAND_STRAIGHT: return "Straight";
        case HAND_THREE_OF_A_KIND: return "Three of a kind";
        case HAND_TWO_PAIR: return "Two pair";
        case HAND_ONE_PAIR: return "One pair";
        case HAND_HIGH_CARD: return "High card";
        default: return "Unknown";
    }
}
