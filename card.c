#include "card.h"

#include <ctype.h>
#include <stddef.h>
#include <string.h>

static Rank parse_rank_char(char c) {
    c = (char)toupper((unsigned char)c);

    if (c >= '2' && c <= '9') {
        return (Rank)(c - '0');
    }

    switch (c) {
        case 'T': return RANK_T;
        case 'J': return RANK_J;
        case 'Q': return RANK_Q;
        case 'K': return RANK_K;
        case 'A': return RANK_A;
        default: return RANK_INVALID;
    }
}

static Suit parse_suit_char(char c) {
    c = (char)tolower((unsigned char)c);

    switch (c) {
        case 'c': return SUIT_CLUBS;
        case 'd': return SUIT_DIAMONDS;
        case 'h': return SUIT_HEARTS;
        case 's': return SUIT_SPADES;
        default: return SUIT_INVALID;
    }
}

int parse_card(const char *text, Card *card) {
    Rank rank;
    Suit suit;

    if (text == NULL || card == NULL || strlen(text) != 2) {
        return 0;
    }

    rank = parse_rank_char(text[0]);
    suit = parse_suit_char(text[1]);

    if (rank == RANK_INVALID || suit == SUIT_INVALID) {
        return 0;
    }

    card->rank = rank;
    card->suit = suit;
    return 1;
}

int parse_hole_cards(const char *text1, const char *text2, HoleCards *hand) {
    Card card1;
    Card card2;

    if (hand == NULL) {
        return 0;
    }

    if (!parse_card(text1, &card1) || !parse_card(text2, &card2)) {
        return 0;
    }

    if (is_same_card(card1, card2)) {
        return 0;
    }

    hand->card1 = card1;
    hand->card2 = card2;
    return 1;
}

int is_same_card(Card a, Card b) {
    return a.rank == b.rank && a.suit == b.suit;
}

void card_to_string(Card card, char *buffer) {
    static const char ranks[] = "??23456789TJQKA";
    char suit = '?';

    if (buffer == NULL) {
        return;
    }

    switch (card.suit) {
        case SUIT_CLUBS: suit = 'c'; break;
        case SUIT_DIAMONDS: suit = 'd'; break;
        case SUIT_HEARTS: suit = 'h'; break;
        case SUIT_SPADES: suit = 's'; break;
        default: suit = '?'; break;
    }

    if (card.rank >= RANK_2 && card.rank <= RANK_A) {
        buffer[0] = ranks[card.rank];
    } else {
        buffer[0] = '?';
    }
    buffer[1] = suit;
    buffer[2] = '\0';
}
