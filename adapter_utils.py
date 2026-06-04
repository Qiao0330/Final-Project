from __future__ import annotations

from card import card_to_string, parse_card, parse_hole_cards
from common import TABLE_POSITIONS, Action, Card, HoleCards, PlayerAction, Position
from range_model import position_to_string


POSITIONS_BY_NAME = {position.name: position for position in TABLE_POSITIONS}

ACTIONS_BY_NAME = {
    "fold": Action.FOLD,
    "call": Action.CALL,
    "raise": Action.RAISE,
    "check": Action.CHECK,
    "all-in": Action.RAISE,
    "allin": Action.RAISE,
}

MIXING_EDGE_BB = 0.35


def parse_position_name(text: str) -> Position:
    position = POSITIONS_BY_NAME.get(str(text).strip().upper())
    if position is None:
        raise ValueError(f"unknown position: {text}")
    return position


def parse_action_name(text: str) -> Action:
    action = ACTIONS_BY_NAME.get(str(text).strip().lower())
    if action is None:
        raise ValueError(f"unknown action: {text}")
    return action


def parse_hand_text(text: str) -> HoleCards:
    value = str(text).strip()
    if len(value) != 4:
        raise ValueError("hero_hand must use four characters, for example AhKs")
    hand = parse_hole_cards(value[:2], value[2:])
    if hand is None:
        raise ValueError(f"invalid hero_hand: {text}")
    return hand


def parse_board_text(text: str, hero_hand: HoleCards | None = None) -> tuple[Card, ...]:
    value = str(text or "").strip().replace(" ", "").replace(",", "")
    if not value:
        return ()
    if len(value) % 2 != 0:
        raise ValueError("board_cards must use two characters per card, for example AhKdQs")
    cards: list[Card] = []
    for index in range(0, len(value), 2):
        card = parse_card(value[index:index + 2])
        if card is None:
            raise ValueError(f"invalid board card: {value[index:index + 2]}")
        cards.append(card)
    if len(cards) > 5:
        raise ValueError("board_cards cannot contain more than five cards")
    known_cards = set(cards)
    if len(known_cards) != len(cards):
        raise ValueError("board_cards contains duplicate cards")
    if hero_hand is not None:
        hero_cards = {hero_hand.card1, hero_hand.card2}
        if known_cards.intersection(hero_cards):
            raise ValueError("board_cards cannot overlap hero_hand")
    return tuple(cards)


def hand_to_text(hand: HoleCards) -> str:
    return f"{card_to_string(hand.card1)}{card_to_string(hand.card2)}"


def cards_to_text(cards: tuple[Card, ...]) -> str:
    return "".join(card_to_string(card) for card in cards)


def action_record_to_dict(record: PlayerAction) -> dict:
    return {
        "position": position_to_string(record.position),
        "action": action_to_wire_label(record.action),
        "amount": record.amount,
    }


def action_history_from_dicts(items: list[dict] | tuple[dict, ...]) -> tuple[PlayerAction, ...]:
    records: list[PlayerAction] = []
    for item in items:
        records.append(
            PlayerAction(
                position=parse_position_name(str(item.get("position", ""))),
                action=parse_action_name(str(item.get("action", ""))),
                amount=float(item.get("amount", 0.0)),
            )
        )
    return tuple(records)


def action_to_label(action: Action, amount: float = 0.0) -> str:
    if action == Action.FOLD:
        return "Fold"
    if action == Action.CALL:
        return "Call"
    if action == Action.CHECK:
        return "Check"
    if action == Action.RAISE and amount >= 99.0:
        return "All-in"
    if action == Action.RAISE:
        return f"Raise {amount:.1f}"
    return "Unknown"


def action_to_wire_label(action: Action) -> str:
    if action == Action.FOLD:
        return "fold"
    if action == Action.CALL:
        return "call"
    if action == Action.CHECK:
        return "check"
    if action == Action.RAISE:
        return "raise"
    return "unknown"


def mixed_frequencies_from_named_evs(evs: dict[str, float]) -> dict[str, float]:
    if not evs:
        return {}
    best_ev = max(evs.values())
    weights = {}
    for name, ev in evs.items():
        gap = max(0.0, best_ev - ev)
        weights[name] = 0.0 if gap >= MIXING_EDGE_BB else (1.0 - gap / MIXING_EDGE_BB) ** 2
    total_weight = sum(weights.values())
    if total_weight <= 0.0:
        best_name = max(evs, key=lambda name: evs[name])
        return {name: 100.0 if name == best_name else 0.0 for name in evs}
    return {name: weight / total_weight * 100.0 for name, weight in weights.items()}


def default_stacks() -> dict:
    return {
        "UTG": 100.0,
        "HJ": 100.0,
        "CO": 100.0,
        "BTN": 100.0,
        "SB": 99.5,
        "BB": 99.0,
    }
