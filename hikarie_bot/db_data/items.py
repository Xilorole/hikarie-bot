"""Items a user picks once a day after arriving; each one changes their later arrivals.

Like the badges, items are defined only in code. A pick is stored as an item_pick_event and the
engine applies it to the user's arrivals after the day it was picked:

- one-shot items (duration_bizdays is None) act on the next arrival, however many days later;
- items with a duration act on every arrival in the next `duration_bizdays` business days.

A user holds at most one item: a one-shot item until the arrival that uses it, an item with a
duration until its last day. The points an arrival gets from items are capped (ITEM_POINT_CAP).
"""

import hashlib
import random
from dataclasses import dataclass
from datetime import date

ITEM_POINT_CAP = 3  # the most points one arrival can get from items
OFFER_COUNT = 3


@dataclass(frozen=True)
class ItemData:
    """An item: its stable ID (stored in item_pick_event), how it is shown and how long it lasts."""

    id: str
    name: str
    emoji: str
    effect: str
    duration_bizdays: int | None = None

    @property
    def label(self) -> str:
        """Return the emoji and the name."""
        return f"{self.emoji} {self.name}"


OMAMORI = "omamori"
NAME_TAG = "name_tag"
ALARM_CLOCK = "alarm_clock"
DASH_SHOES = "dash_shoes"
WEEKLY_PASS = "weekly_pass"  # noqa: S105  # an item ID, not a password
DICE = "dice"
TREAT = "treat"

Items = [
    ItemData(
        id=OMAMORI,
        name="おまもり",
        emoji=":four_leaf_clover:",
        effect="次の出社で、ストレートフラッ出社が1日の休みを許す",
    ),
    ItemData(
        id=NAME_TAG,
        name="名札",
        emoji=":name_badge:",
        effect="5営業日のあいだ、出社一覧の名前に名札が付く",
        duration_bizdays=5,
    ),
    ItemData(
        id=ALARM_CLOCK,
        name="目覚まし時計",
        emoji=":alarm_clock:",
        effect="次の出社が9時前なら +3pt",
    ),
    ItemData(
        id=DASH_SHOES,
        name="スタートダッシュシューズ",
        emoji=":athletic_shoe:",
        effect="次の出社が最速なら +2pt",
    ),
    ItemData(
        id=WEEKLY_PASS,
        name="週間パス",
        emoji=":ticket:",
        effect="5営業日のあいだ、前の営業日に続けて出社するたびに +1pt (最大 +3pt)",
        duration_bizdays=5,
    ),
    ItemData(
        id=DICE,
        name="サイコロ",
        emoji=":game_die:",
        effect="次の出社で 0〜3pt",
    ),
    ItemData(
        id=TREAT,
        name="差し入れ",
        emoji=":doughnut:",
        effect="次の出社の日、あとから出社した3人まで +1pt ずつ",
    ),
]
ITEMS = {item.id: item for item in Items}


def _seed(*parts: object) -> int:
    """Return a seed that is the same in every process (unlike hash())."""
    return int.from_bytes(hashlib.sha256(":".join(map(str, parts)).encode()).digest()[:8])


def offers(user_id: str, day: date) -> list[ItemData]:
    """Return the items offered to the user on a JST day: the same three every time it is asked."""
    return random.Random(_seed("offer", user_id, day)).sample(Items, OFFER_COUNT)  # noqa: S311


def dice_roll(user_id: str, day: date) -> int:
    """Return the dice points (0-3) of the user's arrival on a JST day: the same on every computation."""
    return _seed("dice", user_id, day) % 4
