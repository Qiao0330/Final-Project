#include "card.h"
#include "poker_eval.h"
#include "range.h"

#include <stdio.h>
#include <string.h>

static int failures = 0;

static void expect_true(int condition, const char *message) {
    if (!condition) {
        printf("FAIL: %s\n", message);
        failures++;
    }
}

static Card must_parse(const char *text) {
    Card card;

    if (!parse_card(text, &card)) {
        printf("FAIL: could not parse %s\n", text);
        failures++;
    }

    return card;
}

static void test_card_parsing(void) {
    Card card;
    HoleCards hand;

    expect_true(parse_card("Ah", &card), "Ah should be valid");
    expect_true(parse_card("Th", &card), "Th should be valid");
    expect_true(!parse_card("10h", &card), "10h should be invalid");
    expect_true(!parse_card("Kx", &card), "Kx should be invalid");
    expect_true(!parse_hole_cards("Ah", "Ah", &hand), "duplicate cards should be invalid");
}

static void test_hand_evaluator(void) {
    Card straight_flush[7] = {
        must_parse("Ah"), must_parse("Kh"), must_parse("Qh"),
        must_parse("Jh"), must_parse("Th"), must_parse("2c"), must_parse("3d")
    };
    Card four_kind[7] = {
        must_parse("As"), must_parse("Ad"), must_parse("Ac"),
        must_parse("Ah"), must_parse("Ks"), must_parse("2c"), must_parse("3d")
    };
    Card full_house[7] = {
        must_parse("Ks"), must_parse("Kd"), must_parse("Kc"),
        must_parse("2h"), must_parse("2s"), must_parse("9c"), must_parse("4d")
    };
    Card flush[7] = {
        must_parse("Ah"), must_parse("Kh"), must_parse("9h"),
        must_parse("7h"), must_parse("3h"), must_parse("2c"), must_parse("4d")
    };
    Card two_pair[7] = {
        must_parse("As"), must_parse("Ad"), must_parse("Kc"),
        must_parse("Kh"), must_parse("9s"), must_parse("3c"), must_parse("2d")
    };
    Card one_pair[7] = {
        must_parse("Qs"), must_parse("Qd"), must_parse("Jc"),
        must_parse("9h"), must_parse("7s"), must_parse("4c"), must_parse("2d")
    };
    Card ace_kicker[7] = {
        must_parse("As"), must_parse("Kd"), must_parse("Qc"),
        must_parse("9h"), must_parse("7s"), must_parse("4c"), must_parse("2d")
    };
    Card king_kicker[7] = {
        must_parse("Ks"), must_parse("Qd"), must_parse("Jc"),
        must_parse("9h"), must_parse("7s"), must_parse("4c"), must_parse("2d")
    };

    expect_true(
        compare_hand_values(evaluate_7cards(straight_flush), evaluate_7cards(four_kind)) > 0,
        "straight flush should beat four of a kind"
    );
    expect_true(
        compare_hand_values(evaluate_7cards(full_house), evaluate_7cards(flush)) > 0,
        "full house should beat flush"
    );
    expect_true(
        compare_hand_values(evaluate_7cards(two_pair), evaluate_7cards(one_pair)) > 0,
        "two pair should beat one pair"
    );
    expect_true(
        compare_hand_values(evaluate_7cards(ace_kicker), evaluate_7cards(king_kicker)) > 0,
        "high-card kicker comparison should work"
    );
}

static void test_range_model(void) {
    HoleCards hand;
    HandClass hand_class;

    expect_true(parse_hole_cards("Ah", "Kh", &hand), "Ah Kh should parse");
    hand_class = get_hand_class(hand);
    expect_true(strcmp(hand_class.name, "AKs") == 0, "Ah Kh should be AKs");
    expect_true(is_hand_in_open_range(POS_UTG, hand_class), "AKs should be in UTG open range");

    expect_true(parse_hole_cards("As", "Kd", &hand), "As Kd should parse");
    hand_class = get_hand_class(hand);
    expect_true(strcmp(hand_class.name, "AKo") == 0, "As Kd should be AKo");

    expect_true(parse_hole_cards("7c", "7d", &hand), "7c 7d should parse");
    hand_class = get_hand_class(hand);
    expect_true(strcmp(hand_class.name, "77") == 0, "7c 7d should be 77");

    expect_true(parse_hole_cards("7c", "2d", &hand), "7c 2d should parse");
    hand_class = get_hand_class(hand);
    expect_true(!is_hand_in_open_range(POS_UTG, hand_class), "72o should not be in UTG open range");

    expect_true(players_behind_count(POS_BTN) == 2, "BTN should only have SB and BB behind");
    expect_true(players_behind_count(POS_UTG) == 5, "UTG should have five players behind");

    expect_true(parse_hole_cards("Ah", "As", &hand), "Ah As should parse");
    {
        double fold_probability = estimate_open_fold_probability(POS_BTN, hand, 1.5, 2.5);
        expect_true(fold_probability >= 0.0 && fold_probability <= 1.0, "auto fold probability should be 0 to 1");
    }
}

int main(void) {
    test_card_parsing();
    test_hand_evaluator();
    test_range_model();

    if (failures == 0) {
        printf("All tests passed.\n");
        return 0;
    }

    printf("%d test(s) failed.\n", failures);
    return 1;
}
