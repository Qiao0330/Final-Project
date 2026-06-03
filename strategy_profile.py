from __future__ import annotations

import json
from pathlib import Path


POSITIONS = ("UTG", "HJ", "CO", "BTN", "SB", "BB")
PROFILE_KEYS = ("unacted", "check", "call", "raise", "large_raise", "all_in")
STRATEGY_PROFILE_PATH = Path(__file__).resolve().parent / "strategy_profiles.json"


def load_strategy_profile(path: Path = STRATEGY_PROFILE_PATH) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return normalize_strategy_profile(json.load(file))


def save_strategy_profile(profile: dict, path: Path = STRATEGY_PROFILE_PATH) -> dict:
    normalized = normalize_strategy_profile(profile)
    with path.open("w", encoding="utf-8") as file:
        json.dump(normalized, file, indent=2)
        file.write("\n")
    return normalized


def normalize_strategy_profile(profile: dict) -> dict:
    default = profile.get("default", {})
    positions = profile.get("positions", {})
    thresholds = profile.get("raise_size_thresholds", {})

    normalized_default = {
        key: _clamp_fraction(default.get(key, _default_fraction(key)))
        for key in PROFILE_KEYS
    }
    normalized_positions = {}
    for position in POSITIONS:
        raw_position = positions.get(position, {})
        normalized_positions[position] = {
            key: _clamp_fraction(raw_position.get(key, normalized_default[key]))
            for key in PROFILE_KEYS
        }

    large_raise = _clamp_amount(thresholds.get("large_raise_total_bb", 12.0), 2.0, 100.0)
    all_in = _clamp_amount(thresholds.get("all_in_total_bb", 99.0), large_raise, 100.0)
    return {
        "default": normalized_default,
        "positions": normalized_positions,
        "raise_size_thresholds": {
            "large_raise_total_bb": large_raise,
            "all_in_total_bb": all_in,
        },
    }


def _default_fraction(key: str) -> float:
    return {
        "unacted": 1.0,
        "check": 1.0,
        "call": 0.7,
        "raise": 0.55,
        "large_raise": 0.28,
        "all_in": 0.1,
    }[key]


def _clamp_fraction(value) -> float:
    return max(0.01, min(1.0, float(value)))


def _clamp_amount(value, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, float(value)))
