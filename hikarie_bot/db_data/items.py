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
    """An item: its stable ID (stored in item_pick_event), how it is shown and how long it lasts.

    flavor is the item's story shown in the modal; effect states the rule in one line.
    """

    id: str
    name: str
    emoji: str
    flavor: str
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
        flavor="高輪の路地裏の小さな社で授かった、四つ葉が縫い込まれたお守り。かすかな加護が、休んでしまった一日をなかったことにしてくれる。",
        emoji=":four_leaf_clover:",
        effect="次の出社で、ストレートフラッ出社が1日の休みを許す",
    ),
    ItemData(
        id=NAME_TAG,
        name="名札",
        flavor="入社初日から胸に留めている、少し色あせた名札。裏に刻まれた古い紋章が光り、身に着けているあいだは出社一覧であなたの名前が目立つ。",
        emoji=":name_badge:",
        effect="5営業日のあいだ、出社一覧の名前に名札が付く",
        duration_bizdays=5,
    ),
    ItemData(
        id=ALARM_CLOCK,
        name="目覚まし時計",
        flavor="二つのベルを持つ、年季の入った真鍮の目覚まし時計。その音は眠りの呪いを打ち破り、朝の弱いかいしゃいんでも9時前の改札をくぐらせる。",
        emoji=":alarm_clock:",
        effect="次の出社が9時前なら +3pt",
    ),
    ItemData(
        id=DASH_SHOES,
        name="スタートダッシュシューズ",
        flavor="靴底に厚いクッションがついているシューズ。独特のバネが高輪への足取りを軽くし、誰よりも早く着いた朝にだけ真価を発揮する。",
        emoji=":athletic_shoe:",
        effect="次の出社が最速なら +2pt",
    ),
    ItemData(
        id=WEEKLY_PASS,
        name="週間パス",
        flavor="5日分の改札印が並ぶ、古びた紙の通行証。一日も欠かさず通うほど、刻まれた印がひとつずつ力に変わっていく。",
        emoji=":ticket:",
        effect="5営業日のあいだ、前の営業日に続けて出社するたびに +1pt (最大 +3pt)",
        duration_bizdays=5,
    ),
    ItemData(
        id=DICE,
        name="サイコロ",
        flavor="休憩室の引き出しの奥で見つかった、角の欠けた骨のサイコロ。次の出社の運勢を、この一振りに預ける。",
        emoji=":game_die:",
        effect="次の出社で 0〜3pt",
    ),
    ItemData(
        id=TREAT,
        name="差し入れ",
        flavor="駅前の老舗で買った、甘い香りのドーナツの箱。あとから来た仲間に配ると、オフィスに小さな祝福が満ちる。",
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
