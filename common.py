from dataclasses import dataclass
from enum import IntEnum


class Suit(IntEnum):
    CLUBS = 0
    DIAMONDS = 1
    HEARTS = 2
    SPADES = 3
    INVALID = 4


class Rank(IntEnum):
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 11
    QUEEN = 12
    KING = 13
    ACE = 14
    INVALID = 15


class Position(IntEnum):
    UTG = 0
    HJ = 1
    CO = 2
    BTN = 3
    SB = 4
    BB = 5
    INVALID = 6


TABLE_POSITIONS = (Position.UTG, Position.HJ, Position.CO, Position.BTN, Position.SB, Position.BB)
TABLE_POSITION_NAMES = tuple(position.name for position in TABLE_POSITIONS)


class Action(IntEnum):
    FOLD = 0
    CALL = 1
    RAISE = 2
    CHECK = 3


@dataclass(frozen=True)
class Card:
    rank: Rank
    suit: Suit


@dataclass(frozen=True)
class HoleCards:
    card1: Card
    card2: Card


@dataclass(frozen=True)
class PlayerAction:
    position: Position
    action: Action
    amount: float
