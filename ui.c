#include "ui.h"

#include "card.h"
#include "range.h"

#include <stdio.h>

static Position read_position(void);
static double read_non_negative_double(const char *prompt);
static double read_probability(const char *prompt);
static int read_int_in_range(const char *prompt, int min, int max);
static HoleCards read_hole_cards(void);
static void clear_input_buffer(void);

static Position read_position(void) {
    int choice = 0;

    while (1) {
        printf("Hero position:\n");
        printf("1. UTG\n");
        printf("2. HJ\n");
        printf("3. CO\n");
        printf("4. BTN\n");
        printf("5. SB\n");
        printf("6. BB\n");
        printf("Choose position: ");

        if (scanf("%d", &choice) != 1) {
            clear_input_buffer();
            printf("Invalid input. Please enter a number.\n\n");
            continue;
        }

        if (choice >= 1 && choice <= 6) {
            return (Position)(choice - 1);
        }

        printf("Invalid position. Please choose 1 to 6.\n\n");
    }
}

static double read_non_negative_double(const char *prompt) {
    double value = 0.0;

    while (1) {
        printf("%s", prompt);

        if (scanf("%lf", &value) != 1) {
            clear_input_buffer();
            printf("Invalid input. Please enter a number.\n\n");
            continue;
        }

        if (value >= 0.0) {
            return value;
        }

        printf("Value cannot be negative.\n\n");
    }
}

static double read_probability(const char *prompt) {
    double value = 0.0;

    while (1) {
        printf("%s", prompt);

        if (scanf("%lf", &value) != 1) {
            clear_input_buffer();
            printf("Invalid input. Please enter a number.\n\n");
            continue;
        }

        if (value >= 0.0 && value <= 1.0) {
            return value;
        }

        printf("Probability must be between 0 and 1.\n\n");
    }
}

static int read_int_in_range(const char *prompt, int min, int max) {
    int value = 0;

    while (1) {
        printf("%s", prompt);

        if (scanf("%d", &value) != 1) {
            clear_input_buffer();
            printf("Invalid input. Please enter a number.\n\n");
            continue;
        }

        if (value >= min && value <= max) {
            return value;
        }

        printf("Value must be between %d and %d.\n\n", min, max);
    }
}

static HoleCards read_hole_cards(void) {
    char first_text[8];
    char second_text[8];
    HoleCards hand;

    while (1) {
        printf("Enter hero cards, e.g. Ah Ks: ");

        if (scanf("%7s %7s", first_text, second_text) != 2) {
            clear_input_buffer();
            printf("Invalid input. Please enter two cards.\n\n");
            continue;
        }

        if (!parse_hole_cards(first_text, second_text, &hand)) {
            printf("Invalid cards. Use rank 2-9,T,J,Q,K,A and suit c,d,h,s.\n\n");
            continue;
        }

        return hand;
    }
}

static void clear_input_buffer(void) {
    int ch = 0;

    while ((ch = getchar()) != '\n' && ch != EOF) {
    }
}

void run_main_menu(void) {
    int choice = 0;

    while (1) {
        printf("\nSix-max Preflop Decision System\n");
        printf("1. Solve preflop decision\n");
        printf("2. Input guide\n");
        printf("0. Exit\n");
        printf("Choose an option: ");

        if (scanf("%d", &choice) != 1) {
            clear_input_buffer();
            printf("Invalid input. Please enter a number.\n");
            continue;
        }

        if (choice == 1) {
            SolverInput input = read_solver_input();
            SolverResult result = solve_preflop_decision(input);
            print_solver_result(result);
        } else if (choice == 2) {
            print_input_guide();
        } else if (choice == 0) {
            printf("Goodbye.\n");
            return;
        } else {
            printf("Invalid option.\n");
        }
    }
}

SolverInput read_solver_input(void) {
    SolverInput input;

    printf("\nPreflop input\n");
    input.hero_position = read_position();
    input.hero_hand = read_hole_cards();
    input.pot_size = read_non_negative_double("Current pot size: ");
    input.call_amount = read_non_negative_double("Call amount: ");
    input.raise_amount = read_non_negative_double("Raise amount: ");
    input.fold_probability = read_probability("Estimated fold probability after raise (0-1): ");
    input.opponent_count = read_int_in_range("Opponent count (1-5): ", 1, 5);
    input.simulations = read_int_in_range("Monte Carlo simulations (100-1000000): ", 100, 1000000);

    return input;
}

void print_solver_result(SolverResult result) {
    printf("\nResult\n");
    printf("Equity: %.2f%%\n", result.equity * 100.0);
    printf("EV fold: %.3f\n", result.ev_fold);
    printf("EV call: %.3f\n", result.ev_call);
    printf("EV raise: %.3f\n", result.ev_raise);
    printf("Recommendation: %s\n", action_to_string(result.recommendation));

    if (result.explanation[0] != '\0') {
        printf("Explanation: %s\n", result.explanation);
    }
}

void print_input_guide(void) {
    printf("\nInput guide\n");
    printf("Cards use two characters: rank then suit.\n");
    printf("Ranks: 2 3 4 5 6 7 8 9 T J Q K A\n");
    printf("Suits: c clubs, d diamonds, h hearts, s spades\n");
    printf("Examples: Ah Ks, Td Tc, 7c 2d, As Kd\n");
    printf("Ten must be T, so use Th instead of 10h.\n");
    printf("Positions: UTG, HJ, CO, BTN, SB, BB.\n");
}
