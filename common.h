#ifndef COMMON_H
#define COMMON_H

typedef enum {
    SUIT_CLUBS,
    SUIT_DIAMONDS,
    SUIT_HEARTS,
    SUIT_SPADES,
    SUIT_INVALID
} Suit;

typedef enum {
    RANK_2 = 2,
    RANK_3,
    RANK_4,
    RANK_5,
    RANK_6,
    RANK_7,
    RANK_8,
    RANK_9,
    RANK_T = 10,
    RANK_J,
    RANK_Q,
    RANK_K,
    RANK_A,
    RANK_INVALID
} Rank;

typedef enum {
    POS_UTG,
    POS_HJ,
    POS_CO,
    POS_BTN,
    POS_SB,
    POS_BB,
    POS_INVALID
} Position;

typedef enum {
    ACTION_FOLD,
    ACTION_CALL,
    ACTION_RAISE
} Action;

typedef struct {
    Rank rank;
    Suit suit;
} Card;

typedef struct {
    Card card1;
    Card card2;
} HoleCards;

#endif
