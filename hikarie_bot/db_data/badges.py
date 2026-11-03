"""Module that defines badge types and badges for the 出社登録BOT.

Classes:
    BadgeType: Represents a type of badge with an id, name, and description.
    Badge: Represents a badge with a message, condition, level, score, and badge type id.

Variables:
    BadgeTypes (list): A list of BadgeType instances defining various badge types.
    Badges (list): A list of Badge instances defining various badges and their conditions.
"""

from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise

from hikarie_bot.constants import JST

KIRIBAN_GENERATION_LIMIT = 10000
FIRST_KIRIBAN_ID = 6001  # kiriban badge IDs start here (6000 series to avoid conflicts)


@dataclass
class Kiriban:
    """Represents a kiriban with its properties."""

    id: int
    number: int
    score: int


def kiriban_score(n: int) -> int | None:
    """Return the score of the kiriban n, or None if n is not one.

    The first kind that matches decides the score, in this priority order:
    1. Repetitive (ゾロ目): one digit repeated, like 11 or 7777
    2. Palindrome (回文数): like 121 or 5445
    3. Sequential (階段状): three or more digits ascending or descending, like 123 or 4321
    4. Power of ten multiple (整数x10の累乗): a digit followed by zeros, like 10 or 5000
    """
    digits = str(n)
    if len(digits) < 2:  # noqa: PLR2004
        return None
    if len(set(digits)) == 1:
        return len(digits) * 2
    if digits == digits[::-1]:
        return 5
    steps = {int(next_digit) - int(digit) for digit, next_digit in pairwise(digits)}
    if len(digits) >= 3 and steps in ({1}, {-1}):  # noqa: PLR2004
        return 7
    if set(digits[1:]) == {"0"}:
        return len(digits) * 2
    return None


@dataclass
class BadgeTypeData:
    """Represents a type of badge with an id, name, and description."""

    id: int
    name: str
    description: str
    apply_start: datetime | None = None


@dataclass
class BadgeData:
    """Represents a badge with a message, condition, level, score, and badge type id."""

    id: int
    message: str
    condition: str
    level: int
    score: int
    badge_type_id: int


# every kiriban below the limit, with badge IDs from FIRST_KIRIBAN_ID in order
_KIRIBAN_SCORES = {n: score for n in range(1, KIRIBAN_GENERATION_LIMIT) if (score := kiriban_score(n)) is not None}
KIRIBANS = [
    Kiriban(id=kiriban_id, number=n, score=score)
    for kiriban_id, (n, score) in enumerate(_KIRIBAN_SCORES.items(), start=FIRST_KIRIBAN_ID)
]


# Define the badge types.
BadgeTypes = [
    BadgeTypeData(
        id=1,
        name="welcome",
        description="出社登録BOTを初めて利用した",
    ),
    BadgeTypeData(
        id=2,
        name="fastest_arrival",
        description="最速で出社登録をした",
    ),
    BadgeTypeData(
        id=3,
        name="arrival_count",
        description="たくさん出社登録をした",
    ),
    BadgeTypeData(
        id=4,
        name="straight_flash",
        description="連続して出社した",
    ),
    BadgeTypeData(
        id=5,
        name="time_window",
        description="時間帯による出社登録",
    ),
    BadgeTypeData(
        id=6,
        name="kiriban",
        description="特定の出社登録の回数で付与される",
    ),
    BadgeTypeData(
        id=7,
        name="long_time_no_see",
        description="長期間出社登録がない状態で復帰した",
    ),
    BadgeTypeData(
        id=8,
        name="lucky_you_guys",
        description="同じ時間に出社登録をした",
    ),
    BadgeTypeData(
        id=15,
        name="start_dash",
        description="初回利用から2週間以内に出社登録した",
        apply_start=datetime(2024, 12, 9, tzinfo=JST),
    ),
    BadgeTypeData(
        id=16,
        name="specific_day",
        description="特定の年月日に出社した",
        apply_start=datetime(2024, 12, 26, tzinfo=JST),
    ),
    BadgeTypeData(
        id=17,
        name="yearly_specific_day",
        description="毎年特定の日に出社した",
        apply_start=datetime(2024, 12, 1, tzinfo=JST),
    ),
    BadgeTypeData(
        id=18,
        name="specific_time",
        description="特定の時間に出社した",
        apply_start=datetime(2025, 1, 1, tzinfo=JST),
    ),
    BadgeTypeData(
        id=19,
        name="takanawa_welcome",
        description="高輪オフィスに移転後、初めて出社した",
        apply_start=datetime(2026, 1, 19, tzinfo=JST),
    ),
    BadgeTypeData(
        id=20,
        name="team_goal",
        description="みんなで今週の出社目標を達成した",
        apply_start=datetime(2026, 11, 9, tzinfo=JST),
    ),
]


Badges = [
    # BadgeTypeData id=1, name="welcome", description="出社登録BOTを初めて利用した"
    BadgeData(
        id=101,
        message="はじめての出社登録",
        condition="出社登録BOTを初めて利用した",
        level=1,
        score=2,
        badge_type_id=1,
    ),
    # BadgeTypeData id=2, name="fastest_arrival", description="最速で出社登録をした"
    BadgeData(
        id=201,
        message="最速出社",
        condition="最速で出社登録を行った",
        level=1,
        score=2,
        badge_type_id=2,
    ),
    # BadgeTypeData id=3, name="arrival_count", description="たくさん出社登録をした"
    BadgeData(
        id=301,
        message="出社登録ビギナー",
        condition="5回出社登録した",
        level=1,
        score=3,
        badge_type_id=3,
    ),
    BadgeData(
        id=302,
        message="出社登録マスター",
        condition="20回出社登録した",
        level=2,
        score=5,
        badge_type_id=3,
    ),
    BadgeData(
        id=303,
        message="出社登録フリーク",
        condition="100回出社登録した",
        level=3,
        score=10,
        badge_type_id=3,
    ),
    # BadgeTypeData id=4, name="straight_flash", description="連続して出社した"
    BadgeData(
        id=401,
        message="ストレートフラッ出社",
        condition="5日連続で出社した",
        level=1,
        score=3,
        badge_type_id=4,
    ),
    BadgeData(
        id=402,
        message="ロイヤルストレートフラッ出社",
        condition="異なる時間帯に5日連続で出社した",
        level=2,
        score=5,
        badge_type_id=4,
    ),
    BadgeData(
        id=403,
        message="ウルトラロイヤルストレートフラッ出社",
        condition="異なる連続した時間帯に5日連続で出社した",
        level=3,
        score=8,
        badge_type_id=4,
    ),
    # BadgeTypeData id=5, name="time_window", description="時間帯による出社登録"
    BadgeData(
        id=501,
        message="朝型出社",
        condition="7-9時の間に出社登録をした",
        level=3,
        score=3,
        badge_type_id=5,
    ),
    BadgeData(
        id=502,
        message="出社",
        condition="9-11時の間に出社登録をした",
        level=2,
        score=2,
        badge_type_id=5,
    ),
    BadgeData(
        id=503,
        message="遅めの出社",
        condition="11時以降に出社登録をした",
        level=1,
        score=1,
        badge_type_id=5,
    ),
    BadgeData(
        id=504,
        message="ウルトラ早起き",
        condition="6時台に出社登録をした",
        level=4,
        score=5,
        badge_type_id=5,
    ),
    # BadgeTypeData id=6, name="kiriban", description="特定の出社登録の回数で付与される"
    *(
        BadgeData(
            id=kiriban.id,
            message=f"{kiriban.number}番目のお客様",
            condition=f"{kiriban.number}回目の出社登録をした",
            level=1,
            score=kiriban.score,
            badge_type_id=6,
        )
        for kiriban in KIRIBANS
    ),
    # BadgeTypeData id=7, name="long_time_no_see",
    #           description="長期間出社登録がない状態で復帰した"  # noqa: ERA001
    BadgeData(
        id=701,
        message="2週間ぶりですね、元気にしていましたか？",
        condition="14日以上出社登録がなかったが復帰した",
        level=1,
        score=2,
        badge_type_id=7,
    ),
    BadgeData(
        id=702,
        message="1か月ぶりですね、おかえりなさい。",
        condition="30日以上出社登録がなかったが復帰した",
        level=2,
        score=3,
        badge_type_id=7,
    ),
    BadgeData(
        id=703,
        message="2か月ぶりですね、顔を忘れるところでした。",
        condition="2か月以上出社登録がなかったが復帰した",
        level=3,
        score=4,
        badge_type_id=7,
    ),
    BadgeData(
        id=704,
        message="半年ぶりですね、むしろ初めまして。",
        condition="半年以上出社登録がなかったが復帰した",
        level=4,
        score=6,
        badge_type_id=7,
    ),
    # BadgeTypeData id=8, name="lucky_you_guys", description="同じ時間に出社登録をした"
    BadgeData(
        id=801,
        message="幸運なふたり",
        condition="分単位で同じ時間に出社登録をした2人目になること",
        level=1,
        score=2,
        badge_type_id=8,
    ),
    BadgeData(
        id=802,
        message="豪運なトリオ",
        condition="分単位で同じ時間に出社登録をした3人目になること",
        level=2,
        score=3,
        badge_type_id=8,
    ),
    BadgeData(
        id=803,
        message="激運なカルテット",
        condition="分単位で同じ時間に出社登録をした4人目になること",
        level=3,
        score=4,
        badge_type_id=8,
    ),
    # BadgeTypeData id=15, name="start_dash", description="初回利用から2週間以内に出社登録した"
    BadgeData(
        id=1501,
        message="スタートダッシュ",
        condition="初回利用から2週間以内に出社登録した",
        level=1,
        score=2,
        badge_type_id=15,
    ),
    # BadgeTypeData id=16, name="specific_day", description="特定の年月日に出社した"
    BadgeData(
        id=1601,
        message="2024年お疲れ様です",
        condition="2024年12月27日に出社した",
        level=1,
        score=2,
        badge_type_id=16,
    ),
    BadgeData(
        id=1602,
        message="2025年明けましておめでとうございます",
        condition="2025年1月6日に出社した",
        level=1,
        score=2,
        badge_type_id=16,
    ),
    # BadgeTypeData id=17, name="yearly_specific_day", description="毎年特定の日に出社した"
    BadgeData(
        id=1701,
        message="クリスマス出社",
        condition="12月25日に出社した",
        level=1,
        score=2,
        badge_type_id=17,
    ),
    BadgeData(
        id=1702,
        message="昨年度はお世話になりました",
        condition="年度末に出社した",
        level=1,
        score=2,
        badge_type_id=17,
    ),
    BadgeData(
        id=1703,
        message="今年度もよろしくお願いします",
        condition="年度初めに出社した",
        level=1,
        score=2,
        badge_type_id=17,
    ),
    BadgeData(
        id=1704,
        message="世間はGW",
        condition="4/29~5/5に出社した",
        level=1,
        score=2,
        badge_type_id=17,
    ),
    # BadgeTypeData id=18, name="specific_time", description="特定の時間に出社した"
    BadgeData(
        id=1801,
        message="隣同士",
        condition="時間と分が隣接した数字の時に出社した",
        level=1,
        score=2,
        badge_type_id=18,
    ),
    BadgeData(
        id=1802,
        message="ぞろ目出社",
        condition="時間と分が同じ数字の時に出社した",
        level=2,
        score=3,
        badge_type_id=18,
    ),
    BadgeData(
        id=1803,
        message="階段",
        condition="時間が連続した数字の時に出社した",
        level=3,
        score=4,
        badge_type_id=18,
    ),
    BadgeData(
        id=1804,
        message="せーの...ポッキー!",
        condition="11:11に出社した",
        level=3,
        score=4,
        badge_type_id=18,
    ),
    BadgeData(
        id=1805,
        message="もしやあなたはモフ好きですね",
        condition="11:22に出社した",
        level=3,
        score=4,
        badge_type_id=18,
    ),
    BadgeData(
        id=1806,
        message="今夜は:yakiniku:",
        condition="11:29に出社した",
        level=3,
        score=4,
        badge_type_id=18,
    ),
    BadgeData(
        id=1807,
        message="真実はいつもひとつ",
        condition="9:10に出社した",
        level=3,
        score=4,
        badge_type_id=18,
    ),
    # BadgeTypeData id=19, name="takanawa_welcome", description="高輪オフィスに移転後、初めて出社した"
    BadgeData(
        id=1901,
        message="Welcome to Takanawa",
        condition="高輪オフィス移転後、初めて出社した",
        level=1,
        score=3,
        badge_type_id=19,
    ),
    # BadgeTypeData id=20, name="team_goal", description="みんなで今週の出社目標を達成した"
    BadgeData(
        id=2001,
        message="みんなで達成",
        condition="今週の全員の出社登録が目標（営業日 x 4回）に届いたあとに出社した",
        level=1,
        score=1,
        badge_type_id=20,
    ),
]
