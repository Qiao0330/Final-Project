#include "range.h"

#include <string.h>

static int rank_char_value(char rank);

static int rank_value(Rank rank) {
    if (rank >= RANK_2 && rank <= RANK_A) {
        return (int)rank;
    }
    return 0;
}

static char rank_to_char(Rank rank) {
    switch (rank) {
        case RANK_A:
            return 'A';
        case RANK_K:
            return 'K';
        case RANK_Q:
            return 'Q';
        case RANK_J:
            return 'J';
        case RANK_T:
            return 'T';
        case RANK_9:
            return '9';
        case RANK_8:
            return '8';
        case RANK_7:
            return '7';
        case RANK_6:
            return '6';
        case RANK_5:
            return '5';
        case RANK_4:
            return '4';
        case RANK_3:
            return '3';
        case RANK_2:
            return '2';
        default:
            return '?';
    }
}

static int position_open_threshold(Position pos) {
    switch (pos) {
        case POS_UTG:
            return 74;
        case POS_HJ:
            return 68;
        case POS_CO:
            return 58;
        case POS_BTN:
            return 46;
        case POS_SB:
            return 54;
        case POS_BB:
            return 62;
        default:
            return 100;
    }
}

static int hand_class_score(HandClass hand_class) {
    const char *name = hand_class.name;
    int first = 0;
    int second = 0;
    int suited_bonus = 0;
    int connector_bonus = 0;

    if (name[0] == '\0' || name[1] == '\0') {
        return 0;
    }

    first = rank_char_value(name[0]);
    second = rank_char_value(name[1]);

    if (first == 0 || second == 0) {
        return 0;
    }

    if (first == second) {
        return 50 + first * 4;
    }

    if (name[2] == 's') {
        suited_bonus = 8;
    }

    if (first - second == 1) {
        connector_bonus = 5;
    } else if (first - second == 2) {
        connector_bonus = 2;
    }

    return first * 4 + second * 2 + suited_bonus + connector_bonus;
}

static int rank_char_value(char rank) {
    switch (rank) {
        case 'A':
            return 14;
        case 'K':
            return 13;
        case 'Q':
            return 12;
        case 'J':
            return 11;
        case 'T':
            return 10;
        case '9':
            return 9;
        case '8':
            return 8;
        case '7':
            return 7;
        case '6':
            return 6;
        case '5':
            return 5;
        case '4':
            return 4;
        case '3':
            return 3;
        case '2':
            return 2;
        default:
            return 0;
    }
}

HandClass get_hand_class(HoleCards hand) {
    HandClass hand_class = {{0}};
    Card first = hand.card1;
    Card second = hand.card2;

    if (rank_value(first.rank) == 0 || rank_value(second.rank) == 0) {
        strcpy(hand_class.name, "??");
        return hand_class;
    }

    if (rank_value(first.rank) < rank_value(second.rank)) {
        Card temp = first;
        first = second;
        second = temp;
    }

    hand_class.name[0] = rank_to_char(first.rank);
    hand_class.name[1] = rank_to_char(second.rank);

    if (first.rank == second.rank) {
        hand_class.name[2] = '\0';
    } else {
        hand_class.name[2] = (first.suit == second.suit) ? 's' : 'o';
        hand_class.name[3] = '\0';
    }

    return hand_class;
}

int is_hand_in_open_range(Position pos, HandClass hand_class) {
    return get_preflop_frequency(pos, hand_class).open_frequency > 0.0;
}

RangeActionFrequency get_preflop_frequency(Position pos, HandClass hand_class) {
    RangeActionFrequency frequency = {0.0, 0.0, 0.0};
    int score = hand_class_score(hand_class);
    int threshold = position_open_threshold(pos);

    if (score == 0 || pos == POS_INVALID) {
        return frequency;
    }

    if (score >= threshold + 20) {
        frequency.open_frequency = 1.0;
        frequency.raise_frequency = 0.85;
        frequency.call_frequency = 0.15;
    } else if (score >= threshold + 10) {
        frequency.open_frequency = 0.85;
        frequency.raise_frequency = 0.65;
        frequency.call_frequency = 0.20;
    } else if (score >= threshold) {
        frequency.open_frequency = 0.55;
        frequency.raise_frequency = 0.35;
        frequency.call_frequency = 0.20;
    }

    return frequency;
}

const char *position_to_string(Position pos) {
    switch (pos) {
        case POS_UTG:
            return "UTG";
        case POS_HJ:
            return "HJ";
        case POS_CO:
            return "CO";
        case POS_BTN:
            return "BTN";
        case POS_SB:
            return "SB";
        case POS_BB:
            return "BB";
        default:
            return "INVALID";
    }
}
