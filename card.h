#ifndef CARD_H
#define CARD_H

#include "common.h"

int parse_card(const char *text, Card *card);
int parse_hole_cards(const char *text1, const char *text2, HoleCards *hand);
int is_same_card(Card a, Card b);
void card_to_string(Card card, char *buffer);

#endif
