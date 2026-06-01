# Final Project

Python console program for a simplified GTO-inspired Texas Hold'em preflop
decision system.

## Overview

The program analyzes a preflop situation by entering actions in table order:
UTG, HJ, CO, BTN, SB, and BB. It now uses a full preflop betting loop:

- SB and BB are posted automatically as 0.50 BB and 1.00 BB.
- The pot size is tracked automatically.
- Calls automatically add only the amount needed to match the current highest bet.
- If a player raises, earlier active players receive another decision.
- Hero can receive multiple decision previews, such as facing a 3-bet after opening.
- Hero hole cards and simulation count are entered after the betting action is complete.

It considers:

- hero position
- hero hole cards
- actions before and after hero
- active opponents based on entered call/raise actions
- automatic blind and pot tracking
- position-based opening range frequency
- fold probability based on entered post-hero actions
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
