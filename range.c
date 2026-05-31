#include "range.h"

#include "card.h"

#include <stdio.h>

static char rank_to_char(int rank) {
    static const char ranks[] = "??23456789TJQKA";

    if (rank >= RANK_2 && rank <= RANK_A) {
        return ranks[rank];
    }

    return '?';
}

static int position_open_threshold(Position pos) {
    switch (pos) {
        case POS_UTG: return 58;
        case POS_HJ: return 52;
        case POS_CO: return 46;
        case POS_BTN: return 39;
        case POS_SB: return 42;
        case POS_BB: return 36;
        default: return 58;
    }
}

static double position_aggression(Position pos) {
    switch (pos) {
        case POS_UTG: return 0.72;
        case POS_HJ: return 0.78;
        case POS_CO: return 0.84;
        case POS_BTN: return 0.90;
        case POS_SB: return 0.82;
        case POS_BB: return 0.70;
        default: return 0.75;
    }
}

static int hand_strength_score(HandClass hand_class) {
    int score;
    int gap;

    if (hand_class.pair) {
        return 45 + hand_class.high_rank * 3;
    }

    gap = hand_class.high_rank - hand_class.low_rank - 1;
    score = hand_class.high_rank * 3 + hand_class.low_rank * 2;

    if (hand_class.suited) {
        score += 6;
    }

    if (gap == 0) {
        score += 5;
    } else if (gap == 1) {
        score += 3;
    } else if (gap == 2) {
        score += 1;
    } else {
        score -= gap * 2;
    }

    if (hand_class.high_rank >= RANK_T && hand_class.low_rank >= RANK_T) {
        score += 4;
    }

    if (hand_class.high_rank == RANK_A) {
        score += 3;
    }

    return score;
}

static int combination_count(HandClass hand_class) {
    if (hand_class.pair) {
        return 6;
    }
    return hand_class.suited ? 4 : 12;
}

static double clamp_double(double value, double min, double max) {
    if (value < min) {
        return min;
    }
    if (value > max) {
        return max;
    }
    return value;
}

static double average_open_range_score(Position pos) {
    int high;
    int low;
    double weighted_score = 0.0;
    double total_weight = 0.0;

    for (high = RANK_A; high >= RANK_2; high--) {
        for (low = high; low >= RANK_2; low--) {
            int suited_options = high == low ? 1 : 2;
            int suited_index;

            for (suited_index = 0; suited_index < suited_options; suited_index++) {
                HandClass hand_class;
                RangeActionFrequency frequency;
                int combos;
                int score;

                hand_class.high_rank = high;
                hand_class.low_rank = low;
                hand_class.pair = high == low;
                hand_class.suited = !hand_class.pair && suited_index == 0;

                if (hand_class.pair) {
                    snprintf(
                        hand_class.name,
                        sizeof(hand_class.name),
                        "%c%c",
                        rank_to_char(high),
                        rank_to_char(low)
                    );
                } else {
                    snprintf(
                        hand_class.name,
                        sizeof(hand_class.name),
                        "%c%c%c",
                        rank_to_char(high),
                        rank_to_char(low),
                        hand_class.suited ? 's' : 'o'
                    );
                }

                frequency = get_preflop_frequency(pos, hand_class);
                combos = combination_count(hand_class);
                score = hand_strength_score(hand_class);

                weighted_score += score * frequency.open_frequency * combos;
                total_weight += frequency.open_frequency * combos;
            }
        }
    }

    if (total_weight <= 0.0) {
        return position_open_threshold(pos);
    }

    return weighted_score / total_weight;
}

static double estimate_single_opponent_fold_probability(
    Position hero_position,
    Position opponent_position,
    HoleCards hero_hand,
    double pot_size,
    double raise_amount
) {
    int first_rank;
    int first_suit;
    int second_rank;
    int second_suit;
    double hero_range_score = average_open_range_score(hero_position);
    double position_penalty = opponent_position == POS_SB ? 0.03 : 0.0;
    double final_pot = pot_size + raise_amount + raise_amount;
    double call_amount = raise_amount;
    int total = 0;
    int folds = 0;

    if (raise_amount <= 0.0) {
        return 0.0;
    }

    for (first_rank = RANK_2; first_rank <= RANK_A; first_rank++) {
        for (first_suit = SUIT_CLUBS; first_suit <= SUIT_SPADES; first_suit++) {
            Card first = {(Rank)first_rank, (Suit)first_suit};

            if (is_same_card(first, hero_hand.card1) || is_same_card(first, hero_hand.card2)) {
                continue;
            }

            for (second_rank = first_rank; second_rank <= RANK_A; second_rank++) {
                for (second_suit = SUIT_CLUBS; second_suit <= SUIT_SPADES; second_suit++) {
                    Card second = {(Rank)second_rank, (Suit)second_suit};
                    HoleCards opponent_hand;
                    HandClass opponent_class;
                    double score;
                    double equity_vs_open_range;
                    double continue_ev;

                    if (first_rank == second_rank && first_suit >= second_suit) {
                        continue;
                    }
                    if (first_rank != second_rank && first_rank > second_rank) {
                        continue;
                    }
                    if (is_same_card(second, hero_hand.card1) || is_same_card(second, hero_hand.card2)) {
                        continue;
                    }

                    opponent_hand.card1 = first;
                    opponent_hand.card2 = second;
                    opponent_class = get_hand_class(opponent_hand);
                    score = hand_strength_score(opponent_class);

                    equity_vs_open_range =
                        0.50 + (score - hero_range_score) / 100.0 - position_penalty;
                    equity_vs_open_range = clamp_double(equity_vs_open_range, 0.05, 0.95);

                    continue_ev = equity_vs_open_range * final_pot - call_amount;

                    total++;
                    if (continue_ev <= 0.0) {
                        folds++;
                    }
                }
            }
        }
    }

    if (total == 0) {
        return 1.0;
    }

    return (double)folds / total;
}

HandClass get_hand_class(HoleCards hand) {
    HandClass hand_class;
    int first = hand.card1.rank;
    int second = hand.card2.rank;

    if (first >= second) {
        hand_class.high_rank = first;
        hand_class.low_rank = second;
    } else {
        hand_class.high_rank = second;
        hand_class.low_rank = first;
    }

    hand_class.pair = hand_class.high_rank == hand_class.low_rank;
    hand_class.suited = hand.card1.suit == hand.card2.suit;

    if (hand_class.pair) {
        snprintf(
            hand_class.name,
            sizeof(hand_class.name),
            "%c%c",
            rank_to_char(hand_class.high_rank),
            rank_to_char(hand_class.low_rank)
        );
    } else {
        snprintf(
            hand_class.name,
            sizeof(hand_class.name),
            "%c%c%c",
            rank_to_char(hand_class.high_rank),
            rank_to_char(hand_class.low_rank),
            hand_class.suited ? 's' : 'o'
        );
    }

    return hand_class;
}

RangeActionFrequency get_preflop_frequency(Position pos, HandClass hand_class) {
    RangeActionFrequency frequency = {0.0, 0.0, 0.0};
    int score = hand_strength_score(hand_class);
    int threshold = position_open_threshold(pos);
    double open_frequency;

    if (score >= threshold + 7) {
        open_frequency = 1.0;
    } else if (score >= threshold + 3) {
        open_frequency = 0.75;
    } else if (score >= threshold) {
        open_frequency = 0.50;
    } else if (score >= threshold - 3) {
        open_frequency = 0.25;
    } else {
        open_frequency = 0.0;
    }

    frequency.open_frequency = open_frequency;
    frequency.raise_frequency = open_frequency * position_aggression(pos);
    frequency.call_frequency = open_frequency - frequency.raise_frequency;

    return frequency;
}

int is_hand_in_open_range(Position pos, HandClass hand_class) {
    return get_preflop_frequency(pos, hand_class).open_frequency > 0.0;
}

int players_behind_count(Position pos) {
    if (pos < POS_UTG || pos > POS_BB) {
        return 0;
    }

    return POS_BB - pos;
}

double estimate_open_fold_probability(Position hero_position, HoleCards hero_hand, double pot_size, double raise_amount) {
    Position opponent_position;
    double all_fold_probability = 1.0;

    if (players_behind_count(hero_position) == 0) {
        return 1.0;
    }

    for (opponent_position = (Position)(hero_position + 1);
         opponent_position <= POS_BB;
         opponent_position = (Position)(opponent_position + 1)) {
        double single_fold_probability =
            estimate_single_opponent_fold_probability(
                hero_position,
                opponent_position,
                hero_hand,
                pot_size,
                raise_amount
            );

        all_fold_probability *= single_fold_probability;
    }

    return clamp_double(all_fold_probability, 0.0, 1.0);
}

const char *position_to_string(Position pos) {
    switch (pos) {
        case POS_UTG: return "UTG";
        case POS_HJ: return "HJ";
        case POS_CO: return "CO";
        case POS_BTN: return "BTN";
        case POS_SB: return "SB";
        case POS_BB: return "BB";
        default: return "Unknown";
    }
}

const char *opening_range_summary(Position pos) {
    switch (pos) {
        case POS_UTG:
            return "tight: strong pairs, strong broadways, premium suited aces";
        case POS_HJ:
            return "medium-tight: pairs, broadways, suited aces, selected suited connectors";
        case POS_CO:
            return "medium: most pairs, broadways, suited aces, suited connectors";
        case POS_BTN:
            return "wide: many suited hands, broadways, aces, pairs, connectors";
        case POS_SB:
            return "wide but cautious: many playable hands, adjusted for out-of-position risk";
        case POS_BB:
            return "widest defend/check range in this simplified model";
        default:
            return "no range";
    }
}
