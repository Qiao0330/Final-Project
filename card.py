from __future__ import annotations

from common import Card, HoleCards, Rank, Suit

BOARD_SIZE = 5
DECK_SIZE = 52
FULL_DECK = tuple(
    Card(rank=Rank(rank), suit=Suit(suit))
    for suit in range(int(Suit.CLUBS), int(Suit.SPADES) + 1)
    for rank in range(int(Rank.TWO), int(Rank.ACE) + 1)
)


_RANK_CHARS = {
    "2": Rank.TWO,
    "3": Rank.THREE,
    "4": Rank.FOUR,
    "5": Rank.FIVE,
    "6": Rank.SIX,
    "7": Rank.SEVEN,
    "8": Rank.EIGHT,
    "9": Rank.NINE,
    "T": Rank.TEN,
    "J": Rank.JACK,
    "Q": Rank.QUEEN,
    "K": Rank.KING,
    "A": Rank.ACE,
}

_SUIT_CHARS = {
    "c": Suit.CLUBS,
    "d": Suit.DIAMONDS,
    "h": Suit.HEARTS,
    "s": Suit.SPADES,
}

_RANK_TO_CHAR = {
    Rank.TWO: "2",
    Rank.THREE: "3",
    Rank.FOUR: "4",
    Rank.FIVE: "5",
    Rank.SIX: "6",
    Rank.SEVEN: "7",
    Rank.EIGHT: "8",
    Rank.NINE: "9",
    Rank.TEN: "T",
    Rank.JACK: "J",
    Rank.QUEEN: "Q",
    Rank.KING: "K",
    Rank.ACE: "A",
}

_SUIT_TO_CHAR = {
    Suit.CLUBS: "c",
    Suit.DIAMONDS: "d",
    Suit.HEARTS: "h",
    Suit.SPADES: "s",
}


def parse_card(text: str) -> Card | None:
    if text is None or len(text) != 2:
        return None

    rank = _RANK_CHARS.get(text[0].upper())
    suit = _SUIT_CHARS.get(text[1].lower())
    if rank is None or suit is None:
        return None

    return Card(rank=rank, suit=suit)


def parse_hole_cards(text1: str, text2: str) -> HoleCards | None:
    card1 = parse_card(text1)
    card2 = parse_card(text2)

    if card1 is None or card2 is None:
        return None
    if is_same_card(card1, card2):
        return None

    return HoleCards(card1=card1, card2=card2)


def is_same_card(a: Card, b: Card) -> bool:
    return a.rank == b.rank and a.suit == b.suit


def card_to_string(card: Card) -> str:
    return f"{_RANK_TO_CHAR.get(card.rank, '?')}{_SUIT_TO_CHAR.get(card.suit, '?')}"
