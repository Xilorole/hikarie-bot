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

from hikarie_bot.constants import ITEM_IMAGE_BASE_URL

ITEM_POINT_CAP = 3  # the most points one arrival can get from items
OFFER_COUNT = 3


@dataclass(frozen=True)
class ItemData:
    """An item: its stable ID (stored in item_pick_event), how it is shown and how long it lasts.

    flavor is the item's story on its card, hinting at what it does; effect states exactly what it does
    (in points, or that it gives none) and is shown with it, in the thread announcement and in notices.
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
ID_CARD = "id_card"
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
        flavor="高輪築堤の石垣のそばで見つけた、四つ葉が縫い込まれたお守り。かすかな加護が、休んでしまった一日をなかったことにしてくれる。",
        effect="次の出社で、直近6営業日のうち休みが1日だけならストレートフラッ出社（+3pt）を獲得",
    ),
    ItemData(
        id=ID_CARD,
        name="社員証",
        emoji=":identification_card:",
        flavor="高輪の新しいオフィスで最初に受け取った、ICチップ入りの社員証。胸に下げているあいだは、出社一覧であなたの名前が少しだけ目立つ。",
        effect="5営業日のあいだ、出社一覧の名前の横に社員証が付く（ポイントは増えない）",
        duration_bizdays=5,
    ),
    ItemData(
        id=ALARM_CLOCK,
        name="目覚まし時計",
        emoji=":alarm_clock:",
        flavor="二つのベルを持つ、年季の入った真鍮の目覚まし時計。その音は眠りの呪いを打ち破り、朝の弱いかいしゃいんでも9時前の改札をくぐらせる。",
        effect="次の出社が9時より前なら +3pt",
    ),
    ItemData(
        id=DASH_SHOES,
        name="スタートダッシュシューズ",
        emoji=":athletic_shoe:",
        flavor="靴底に厚いクッションがついているシューズ。独特のバネが高輪への足取りを軽くし、誰よりも早く着いた朝にだけ真価を発揮する。",
        effect="次の出社でその日の一番乗りになれば +2pt",
    ),
    ItemData(
        id=WEEKLY_PASS,
        name="週間パス",
        emoji=":ticket:",
        flavor="5日分の改札印が並ぶ、古びた紙の通行証。一日も欠かさず通うほど、刻まれた印がひとつずつ力に変わっていく。",
        effect="5営業日のあいだ、前の営業日にも出社していれば出社ごとに +1pt（合計で最大 +3pt）",
        duration_bizdays=5,
    ),
    ItemData(
        id=DICE,
        name="サイコロ",
        emoji=":game_die:",
        flavor="備品ロッカーの中で見つけた、ボードゲーム用の四面のサイコロ。"
        "三角の山が止まるまで、次の出社の運勢はだれにもわからない。",
        effect="次の出社で 0〜3pt のどれか（四面のサイコロを1回振る）",
    ),
    ItemData(
        id=TREAT,
        name="差し入れ",
        emoji=":bread:",
        flavor="鋳物の鍋でひとつずつ焼き上げる、駅ビルのパン屋の焼きたての包み。あとから来た仲間に配ると、オフィスに小さな祝福が満ちる。",
        effect="次に出社した日、あとから出社した先着3人がそれぞれ +1pt（あなた自身は増えない）",
    ),
]
ITEMS = {item.id: item for item in Items}
# the image on each item's card (cut from a generated sheet by scripts/cut_item_icons.py)
ITEM_IMAGE_URLS = {item.id: f"{ITEM_IMAGE_BASE_URL}/{item.id}.png" for item in Items}


def _seed(*parts: object) -> int:
    """Return a seed that is the same in every process (unlike hash())."""
    return int.from_bytes(hashlib.sha256(":".join(map(str, parts)).encode()).digest()[:8])


def offers(user_id: str, day: date) -> list[ItemData]:
    """Return the items offered to the user on a JST day: the same three every time it is asked."""
    return random.Random(_seed("offer", user_id, day)).sample(Items, OFFER_COUNT)  # noqa: S311


def dice_roll(user_id: str, day: date) -> int:
    """Return the dice points (0-3) of the user's arrival on a JST day: the same on every computation."""
    return _seed("dice", user_id, day) % 4
