# Final Project

Python console program for a simplified GTO-inspired Texas Hold'em preflop
decision system.

## Overview

The program analyzes a preflop situation where action has folded to the hero.
It considers:

- hero position
- hero hole cards
- players behind the hero
- position-based opening range frequency
- automatically estimated opponent fold probability
- Monte Carlo equity estimation
- EV comparison for fold, call, and raise

The project is now Python-first. The previous C source files were removed.

## Files

- `common.py`: shared enums and data classes
- `card.py`: card parsing and card utilities
- `poker_eval.py`: seven-card poker hand evaluation
- `range_model.py`: hand class, position range, and fold probability model
- `equity.py`: Monte Carlo preflop equity simulation
- `solver.py`: EV calculation and action recommendation
- `ui.py`: console user interface
- `main.py`: program entry point
- `test_poker_solver.py`: lightweight tests

## Run

```powershell
python main.py
```

## Test

```powershell
python test_poker_solver.py
```

Expected test output:

```text
All Python tests passed.
```

## Requirements

Python 3.10 or newer is recommended. The project uses only the Python standard
library.
