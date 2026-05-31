CC = gcc
CFLAGS = -Wall -Wextra -std=c11 -O2
TARGET = poker_solver
SOURCES = main.c card.c poker_eval.c equity.c range.c solver.c ui.c
OBJECTS = $(SOURCES:.c=.o)
TEST_TARGET = tests
TEST_SOURCES = tests.c card.c poker_eval.c range.c

all: $(TARGET)

$(TARGET): $(OBJECTS)
	$(CC) $(CFLAGS) -o $(TARGET) $(OBJECTS)

%.o: %.c
	$(CC) $(CFLAGS) -c $<

clean:
	del /Q $(OBJECTS) $(TARGET).exe $(TEST_TARGET).exe 2>NUL || exit 0

test: $(TEST_TARGET)
	./$(TEST_TARGET)

$(TEST_TARGET): $(TEST_SOURCES)
	$(CC) $(CFLAGS) -o $(TEST_TARGET) $(TEST_SOURCES)

.PHONY: all clean test
