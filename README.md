# Final Project

Python console program and browser UI for a simplified GTO-inspired Texas
Hold'em decision system.

## Overview

The console program analyzes a preflop situation by entering actions in table order:
UTG, HJ, CO, BTN, SB, and BB. The console analysis flow now asks for Hero's
position and hole cards first, then asks for the current decision point:

- current pot size
- amount Hero must call, or 0 if checking is available
- candidate raise sizes to compare
- active opponent count
- optional prior action history
- simulation count

It considers:

- hero position
- hero hole cards
- actions before and after hero
- active opponents based on entered call/raise actions
- current pot size and call amount
- position-based opening range frequency
- fold probability based on entered post-hero actions
- Monte Carlo equity estimation
- EV comparison for fold, check, call, and one or more raise sizes

The project also exposes UI-facing adapter functions:

- `study_adapter.get_study_view_data(request)`: returns a stable Study Mode dict.
- `trainer_adapter.get_trainer_question(settings)`: returns one Trainer Mode question.
- `trainer_adapter.grade_trainer_answer(question_id, user_action)`: grades a Trainer Mode answer.

It also includes a browser UI served by `web_app.py`. The UI provides:

- simplified Study Mode spot builder focused on Hero position, Hero hand, and table actions
- automatic preflop candidate raise sizes, so users do not need to enter sizing manually
- visual six-max table where seats can be clicked to append fold/call/raise/check actions
- automatic preflop state derivation from action history, including pot, current bet, Hero call amount, active opponents, and next player to act
- legal action gating, so only the next player to act is clickable and only valid fold/call/raise/check options are enabled
- raise sizing guidance with minimum raise total, 100 BB effective stack cap, all-in shortcut, and validation warnings
- closed-node locking after the preflop betting round is complete, while keeping the 169-hand analysis visible for that node
- 13x13 range matrix covering all 169 hand classes, with each class using a representative hand and Monte Carlo equity estimate
- stable preflop strategy-table frequencies, so weak hands are not promoted by Monte Carlo noise
- opponent range inference from action history, so active opponents are weighted by simplified raise/call/check ranges instead of always being random hands
- JSON-backed strategy profiles for action-based range fractions by position and raise size
- opponent range summary cards showing source, profile key, continue fraction, candidate count, and total weight
- per-hand action frequency and EV table
- Trainer Mode question generation and answer grading

The project is now Python-first. The previous C source files were removed.

## Files

- `common.py`: shared enums and data classes
- `card.py`: card parsing and card utilities
- `poker_eval.py`: seven-card poker hand evaluation
- `range_model.py`: hand class, position range, and fold probability model
- `equity.py`: Monte Carlo preflop equity simulation
- `range_equity.py`: range-aware opponent sampling and equity estimation
- `strategy_profile.py`: strategy profile loading, validation, clamping, and saving
- `strategy_profiles.json`: configurable simplified strategy profile data
- `solver.py`: EV calculation and action recommendation
- `ui.py`: console user interface
- `study_adapter.py`: Study Mode dict API for UI integration
- `trainer_adapter.py`: Trainer Mode dict API for UI integration
- `adapter_utils.py`: shared adapter parsing and formatting helpers
- `web_app.py`: local browser UI server
- `web_static/`: HTML, CSS, and JavaScript for the browser UI
- `main.py`: program entry point
- `test_poker_solver.py`: lightweight tests

## Run

```powershell
python main.py
```

## Browser UI

```powershell
python web_app.py
```

Then open:

```text
http://127.0.0.1:8000
```

In Study Mode, choose Hero position and Hero hand, then choose the current action
near the table and click the seat that is next to act. The app derives pot size,
call amount, active opponents, current bet, and next player to act from the
preflop action history. Raise sizes are recommended automatically from the
current preflop node, so users do not need to enter pot, call amount, opponent
count, simulations, or sizing manually in the default UI. The table disables
seats that are not next to act and disables actions that are not legal for the
current preflop bet.
When the betting round is closed, the table marks the node as closed, disables
seat actions, and keeps the current range matrix and EV table fixed on that node.
Each hand row exposes action frequencies and per-action EVs. The current
preflop frequency model is strategy-table driven by position, action history,
and hand class strength. This is still a simplified model, not a full
CFR-trained GTO solution. The summary action list and each hand detail/table row
show automatically generated raise sizing options with per-sizing frequency and
EV.
When action history identifies active opponents, the matrix estimates equity
against simplified weighted opponent ranges derived from their latest action.
Those range fractions are defined in `strategy_profiles.json`, so position/action
profiles can be tuned without changing Python code.
The Study UI displays those inferred opponent ranges below the matrix so the
current node's assumptions are visible.

The web server exposes these JSON endpoints:

- `POST /api/study`: returns the full Study Mode analysis payload.
- `POST /api/trainer/question`: creates a Trainer Mode question.
- `POST /api/trainer/grade`: grades a Trainer Mode answer.
- `GET /api/strategy-profiles`: reads the normalized strategy profile.
- `POST /api/strategy-profiles`: validates, saves, and returns the strategy profile.

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
