#include "ui.h"

#include "card.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define BUFFER_SIZE 128

static void trim_newline(char *text) {
    size_t length;

    if (text == NULL) {
        return;
    }

    length = strlen(text);
    if (length > 0 && text[length - 1] == '\n') {
        text[length - 1] = '\0';
    }
}

static void read_line(const char *prompt, char *buffer, size_t size) {
    printf("%s", prompt);
    if (fgets(buffer, (int)size, stdin) == NULL) {
        buffer[0] = '\0';
        return;
    }
    trim_newline(buffer);
}

static int read_int_range(const char *prompt, int min, int max) {
    char buffer[BUFFER_SIZE];
    char *end;
    long value;

    while (1) {
        read_line(prompt, buffer, sizeof(buffer));
        value = strtol(buffer, &end, 10);

        if (end != buffer && *end == '\0' && value >= min && value <= max) {
            return (int)value;
        }

        printf("Invalid input. Please enter an integer from %d to %d.\n", min, max);
    }
}

static double read_double_min(const char *prompt, double min) {
    char buffer[BUFFER_SIZE];
    char *end;
    double value;

    while (1) {
        read_line(prompt, buffer, sizeof(buffer));
        value = strtod(buffer, &end);

        if (end != buffer && *end == '\0' && value >= min) {
            return value;
        }

        printf("Invalid input. Please enter a number greater than or equal to %.2f.\n", min);
    }
}

static HoleCards read_hole_cards(void) {
    char first[BUFFER_SIZE];
    char second[BUFFER_SIZE];
    HoleCards hand;

    while (1) {
        read_line("Hero first card  (example Ah): ", first, sizeof(first));
        read_line("Hero second card (example Ks): ", second, sizeof(second));

        if (parse_hole_cards(first, second, &hand)) {
            return hand;
        }

        printf("Invalid cards. Use rank-suit format like Ah, Ks, Tc. Duplicates and 10h are invalid.\n");
    }
}

static Position read_position(void) {
    int choice;

    printf("\nHero position\n");
    printf("1. UTG\n");
    printf("2. HJ\n");
    printf("3. CO\n");
    printf("4. BTN\n");
    printf("5. SB\n");
    printf("6. BB\n");

    choice = read_int_range("Choose hero position: ", 1, 6);
    return (Position)(choice - 1);
}

static void print_opening_ranges(void) {
    int pos;

    printf("\nPosition opening range model\n");
    printf("----------------------------\n");
    for (pos = POS_UTG; pos <= POS_BB; pos++) {
        printf("%s: %s\n", position_to_string((Position)pos), opening_range_summary((Position)pos));
    }
}

void run_main_menu(void) {
    int running = 1;

    while (running) {
        int choice;

        printf("\n");
        printf("============================================\n");
        printf("Texas Hold'em Preflop Decision System\n");
        printf("============================================\n");
        printf("1. New analysis\n");
        printf("2. Input guide\n");
        printf("3. Exit\n");

        choice = read_int_range("Choose an option: ", 1, 3);

        if (choice == 1) {
            SolverInput input = read_solver_input();
            SolverResult result = solve_preflop_decision(input);
            print_solver_result(result);
        } else if (choice == 2) {
            print_input_guide();
        } else {
            running = 0;
        }
    }
}

SolverInput read_solver_input(void) {
    SolverInput input;

    printf("\nNew decision analysis\n");
    printf("---------------------\n");

    input.hero_position = read_position();
    input.hero_hand = read_hole_cards();
    input.pot_size = read_double_min("Current pot size: ", 0.0);
    input.call_amount = read_double_min("Call amount: ", 0.0);
    input.raise_amount = read_double_min("Raise amount: ", 0.0);
    input.simulations = read_int_range("Simulation count (1-1000000): ", 1, 1000000);

    return input;
}

void print_solver_result(SolverResult result) {
    printf("\nResult\n");
    printf("------\n");
    printf("Hero position: %s\n", position_to_string(result.hero_position));
    printf("Players behind: %d\n", result.opponent_count);
    printf("Hand class:    %s\n", result.hand_class.name);
    printf("In open range: %s\n", result.range_frequency.open_frequency > 0.0 ? "yes" : "no");
    printf("Open freq:     %.0f%%\n", result.range_frequency.open_frequency * 100.0);
    printf("Call freq:     %.0f%%\n", result.range_frequency.call_frequency * 100.0);
    printf("Raise freq:    %.0f%%\n", result.range_frequency.raise_frequency * 100.0);
    printf("Auto fold prob: %.2f%%\n", result.fold_probability * 100.0);
    printf("\n");
    printf("Simulations: %d\n", result.equity_result.simulations);
    printf("Wins:        %d (%.2f%%)\n", result.equity_result.wins, result.equity_result.win_rate * 100.0);
    printf("Ties:        %d (%.2f%%)\n", result.equity_result.ties, result.equity_result.tie_rate * 100.0);
    printf("Losses:      %d (%.2f%%)\n", result.equity_result.losses, result.equity_result.loss_rate * 100.0);
    printf("Equity:      %.4f\n", result.equity);
    printf("\n");
    printf("EV fold:     %.4f\n", result.ev_fold);
    printf("EV call:     %.4f\n", result.ev_call);
    printf("EV raise:    %.4f\n", result.ev_raise);
    printf("\n");
    printf("Recommendation: %s\n", action_to_string(result.recommendation));
    printf("Explanation:    %s\n", result.explanation);
}

void print_input_guide(void) {
    printf("\nInput guide\n");
    printf("-----------\n");
    printf("Card format: rank followed by suit.\n");
    printf("Ranks: 2 3 4 5 6 7 8 9 T J Q K A\n");
    printf("Suits: c=clubs, d=diamonds, h=hearts, s=spades\n");
    printf("Valid examples: Ah, Ks, Qd, Tc, 7c\n");
    printf("Invalid examples: 10h, Kx, ZZ, duplicated cards like Ah Ah\n");
    printf("\n");
    printf("Players before hero are treated as folded.\n");
    printf("Players behind hero are derived from position: BTN has SB and BB only.\n");
    printf("Pot size, call amount, and raise amount cannot be negative.\n");
    printf("Fold probability is estimated automatically from opponent EV versus hero open range.\n");
    print_opening_ranges();
}
