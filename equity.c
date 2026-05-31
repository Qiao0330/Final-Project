#include "equity.h"

#include "card.h"
#include "poker_eval.h"

#include <stdlib.h>
#include <time.h>

#define DECK_SIZE 52
#define BOARD_SIZE 5
#define MAX_OPPONENTS 5

static void seed_random_once(void) {
    static int seeded = 0;

    if (!seeded) {
        srand((unsigned int)time(NULL));
        seeded = 1;
    }
}

static void build_deck(Card deck[DECK_SIZE]) {
    int index = 0;
    int suit;
    int rank;

    for (suit = SUIT_CLUBS; suit <= SUIT_SPADES; suit++) {
        for (rank = RANK_2; rank <= RANK_A; rank++) {
            deck[index].rank = (Rank)rank;
            deck[index].suit = (Suit)suit;
            index++;
        }
    }
}

static int remove_known_cards(Card deck[DECK_SIZE], HoleCards hand) {
    int read;
    int write = 0;

    for (read = 0; read < DECK_SIZE; read++) {
        if (!is_same_card(deck[read], hand.card1) &&
            !is_same_card(deck[read], hand.card2)) {
            deck[write++] = deck[read];
        }
    }

    return write;
}

static void shuffle_deck(Card deck[], int count) {
    int i;

    for (i = count - 1; i > 0; i--) {
        int j = rand() % (i + 1);
        Card temp = deck[i];
        deck[i] = deck[j];
        deck[j] = temp;
    }
}

static HandValue make_player_value(HoleCards hand, const Card board[BOARD_SIZE]) {
    Card seven[7];
    int i;

    seven[0] = hand.card1;
    seven[1] = hand.card2;
    for (i = 0; i < BOARD_SIZE; i++) {
        seven[i + 2] = board[i];
    }

    return evaluate_7cards(seven);
}

EquityResult estimate_preflop_equity(EquityInput input) {
    EquityResult result = {0};
    int sim;

    if (input.opponent_count < 0) {
        input.opponent_count = 0;
    }
    if (input.opponent_count > MAX_OPPONENTS) {
        input.opponent_count = MAX_OPPONENTS;
    }
    if (input.simulations < 1) {
        input.simulations = 1;
    }

    seed_random_once();
    result.simulations = input.simulations;

    if (input.opponent_count == 0) {
        result.wins = input.simulations;
        result.win_rate = 1.0;
        result.tie_rate = 0.0;
        result.loss_rate = 0.0;
        result.equity = 1.0;
        return result;
    }

    for (sim = 0; sim < input.simulations; sim++) {
        Card deck[DECK_SIZE];
        Card board[BOARD_SIZE];
        HoleCards opponents[MAX_OPPONENTS];
        HandValue hero_value;
        int deck_count;
        int index = 0;
        int opponent;
        int has_better_opponent = 0;
        int has_equal_opponent = 0;

        build_deck(deck);
        deck_count = remove_known_cards(deck, input.hero_hand);
        shuffle_deck(deck, deck_count);

        for (opponent = 0; opponent < input.opponent_count; opponent++) {
            opponents[opponent].card1 = deck[index++];
            opponents[opponent].card2 = deck[index++];
        }

        for (opponent = 0; opponent < BOARD_SIZE; opponent++) {
            board[opponent] = deck[index++];
        }

        hero_value = make_player_value(input.hero_hand, board);

        for (opponent = 0; opponent < input.opponent_count; opponent++) {
            HandValue opponent_value = make_player_value(opponents[opponent], board);
            int comparison = compare_hand_values(hero_value, opponent_value);

            if (comparison < 0) {
                has_better_opponent = 1;
                break;
            }
            if (comparison == 0) {
                has_equal_opponent = 1;
            }
        }

        if (has_better_opponent) {
            result.losses++;
        } else if (has_equal_opponent) {
            result.ties++;
        } else {
            result.wins++;
        }
    }

    result.win_rate = (double)result.wins / result.simulations;
    result.tie_rate = (double)result.ties / result.simulations;
    result.loss_rate = (double)result.losses / result.simulations;
    result.equity = ((double)result.wins + 0.5 * result.ties) / result.simulations;

    return result;
}
