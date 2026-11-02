"""Module that defines badge types and badges for the 出社登録BOT.

Classes:
    BadgeType: Represents a type of badge with an id, name, and description.
    Badge: Represents a badge with a message, condition, level, score, and badge type id.

Variables:
    BadgeTypes (list): A list of BadgeType instances defining various badge types.
    Badges (list): A list of Badge instances defining various badges and their conditions.
"""

from collections.abc import Generator
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from hikarie_bot.constants import KIRIBAN_GENERATION_LIMIT


@dataclass
class Kiriban:
    """Represents a kiriban with its properties."""

    id: int
    number: int
    score: int
    kiriban_type: str


class KiribanGenerator:
    """Generator for kiriban numbers with appropriate scoring."""

    def _is_power_of_ten_multiple(self, n: int) -> bool:
        """Check if a number is a multiple of power of 10 with first digit non-zero.

        Examples: 10, 20, 100, 300, 1000, 5000, etc.
        """
        if n < 10:  # noqa: PLR2004
            return False

        str_n = str(n)
        # Check if all digits except the first are zeros
        return str_n[0] != "0" and all(digit == "0" for digit in str_n[1:])

    def _is_repetitive(self, n: int) -> bool:
        """Check if a number consists of the same digit repeated.

        Examples: 11, 222, 1111, 7777, etc.
        """
        str_n = str(n)
        return len(str_n) >= 2 and len(set(str_n)) == 1  # noqa: PLR2004

    def _is_sequential(self, n: int) -> bool:
        """Check if a number has digits in sequential order (ascending or descending).

        Examples: 123, 1234, 4321, 987, etc.
        """
        str_n = str(n)
        if len(str_n) < 3:  # Need at least 3 digits for a meaningful sequence  # noqa: PLR2004
            return False

        digits = [int(d) for d in str_n]

        # Check ascending sequence
        is_ascending = all(digits[i] + 1 == digits[i + 1] for i in range(len(digits) - 1))

        # Check descending sequence
        is_descending = all(digits[i] - 1 == digits[i + 1] for i in range(len(digits) - 1))

        return is_ascending or is_descending

    def _is_palindrome(self, n: int) -> bool:
        """Check if a number is a palindrome (reads the same forwards and backwards).

        Examples: 121, 1221, 5445, 12321, etc.
        """
        str_n = str(n)
        return len(str_n) >= 2 and str_n == str_n[::-1]  # noqa: PLR2004

    def _calculate_score(self, number: int, kiriban_type: str) -> int:
        """Calculate the score for a kiriban based on its type and characteristics.

        Args:
            number: The kiriban number
            kiriban_type: Type of kiriban

        Returns:
            Calculated score
        """
        digit_count = len(str(number))

        if kiriban_type == "repetitive":  # ゾロ目
            return digit_count * 2
        if kiriban_type == "palindrome":  # 回文
            return 5
        if kiriban_type == "sequential":  # 階段状
            return 7
        if kiriban_type == "power_of_ten":  # 累乗
            return digit_count * 2
        return 1  # Default score

    def _get_kiriban_type(self, n: int) -> str | None:
        """Get the type of kiriban for a given number.

        Priority order (highest to lowest):
        1. Repetitive (ゾロ目)
        2. Palindrome (回文数)
        3. Sequential (階段状)
        4. Power of ten multiple (整数x10の累乗)
        """
        if self._is_repetitive(n):
            return "repetitive"
        if self._is_palindrome(n):
            return "palindrome"
        if self._is_sequential(n):
            return "sequential"
        if self._is_power_of_ten_multiple(n):
            return "power_of_ten"
        return None

    def generate_kiriban(self, under: int) -> Generator[Kiriban, None, None]:
        """Generate kiriban instances up to a specified limit.

        Args:
            under: Maximum number to generate (exclusive)

        Yields:
            Kiriban instances with appropriate scores
        """
        kiriban_id = 6001  # Starting ID for kiriban badges (6000 series to avoid conflicts)

        for n in range(1, under):
            kiriban_type = self._get_kiriban_type(n)
            if kiriban_type:
                score = self._calculate_score(n, kiriban_type)
                yield Kiriban(id=kiriban_id, number=n, score=score, kiriban_type=kiriban_type)
                kiriban_id += 1


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


def generate_kiriban_badges(under: int) -> list[BadgeData]:
    """Generate kiriban BadgeData dynamically using KiribanGenerator.

    Args:
        under: Maximum kiriban number to generate (exclusive)

    Returns:
        List of BadgeData for kiriban badges starting from id=6001
    """
    generator = KiribanGenerator()
    return [
        BadgeData(
            id=kiriban.id,
            message=f"{kiriban.number}番目のお客様",
            condition=f"{kiriban.number}回目の出社登録をした",
            level=1,
            score=kiriban.score,  # Use calculated score based on kiriban type
            badge_type_id=6,
        )
        for kiriban in generator.generate_kiriban(under=under)
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
        id=9,
        name="reincarnation",
        description="転生した",
    ),
    BadgeTypeData(
        id=10,
        name="item_shop",
        description="道具屋を利用した",
    ),
    BadgeTypeData(
        id=11,
        name="used_log_report",
        description="ログ分析レポートを利用した",
    ),
    BadgeTypeData(id=12, name="seasonal_rank", description="特定のシーズンでランクインした"),
    BadgeTypeData(
        id=13,
        name="reactioner",
        description="リアクションをした",
    ),
    BadgeTypeData(
        id=14,
        name="advance_notice_success",
        description="予告出社を成功させた",
    ),
    BadgeTypeData(
        id=15,
        name="start_dash",
        description="初回利用から2週間以内に出社登録した",
        apply_start=datetime(2024, 12, 9, tzinfo=ZoneInfo("Asia/Tokyo")),
    ),
    BadgeTypeData(
        id=16,
        name="specific_day",
        description="特定の年月日に出社した",
        apply_start=datetime(2024, 12, 26, tzinfo=ZoneInfo("Asia/Tokyo")),
    ),
    BadgeTypeData(
        id=17,
        name="yearly_specific_day",
        description="毎年特定の日に出社した",
        apply_start=datetime(2024, 12, 1, tzinfo=ZoneInfo("Asia/Tokyo")),
    ),
    BadgeTypeData(
        id=18,
        name="specific_time",
        description="特定の時間に出社した",
        apply_start=datetime(2025, 1, 1, tzinfo=ZoneInfo("Asia/Tokyo")),
    ),
    BadgeTypeData(
        id=19,
        name="takanawa_welcome",
        description="高輪オフィスに移転後、初めて出社した",
        apply_start=datetime(2026, 1, 19, tzinfo=ZoneInfo("Asia/Tokyo")),
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
    # Dynamically generated kiriban badges are inserted here
    *generate_kiriban_badges(under=KIRIBAN_GENERATION_LIMIT),
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
    # BadgeTypeData id=9, name="reincarnation", description="転生した"
    BadgeData(
        id=901,
        message="新しくなったあなた",
        condition="1回目の転生をした",
        level=1,
        score=1,
        badge_type_id=9,
    ),
    BadgeData(
        id=902,
        message="2回目の目覚め",
        condition="2回目の転生をした",
        level=2,
        score=1,
        badge_type_id=9,
    ),
    # BadgeTypeData id=10, name="item_shop", description="道具屋を利用した"
    BadgeData(
        id=1001,
        message="道具屋利用",
        condition="道具屋を利用した",
        level=1,
        score=1,
        badge_type_id=10,
    ),
    # BadgeTypeData id=11, name="used_log_report", description="ログ分析レポートを利用した"
    BadgeData(
        id=1101,
        message="ログ分析レポート利用",
        condition="ログ分析レポートを利用した",
        level=1,
        score=1,
        badge_type_id=11,
    ),
    # BadgeTypeData id=12, name="seasonal_rank",
    #           description="特定のシーズンでランクインした" # noqa: ERA001
    BadgeData(
        id=1201,
        message="Top of Top",
        condition="特定のシーズンで首位になった",
        level=2,
        score=1,
        badge_type_id=12,
    ),
    BadgeData(
        id=1202,
        message="Seasonal Ranker",
        condition="特定のシーズンで3位以内になった",
        level=1,
        score=1,
        badge_type_id=12,
    ),
    # BadgeTypeData id=13, name="reactioner", description="リアクションをした"
    BadgeData(
        id=1301,
        message="盛り上げ役",
        condition="10回リアクションをした",
        level=1,
        score=1,
        badge_type_id=13,
    ),
    BadgeData(
        id=1302,
        message="大衆の扇動者",
        condition="50回リアクションをした",
        level=2,
        score=1,
        badge_type_id=13,
    ),
    # BadgeTypeData id=14, name="advance_notice_success", description="予告出社を成功させた"
    BadgeData(
        id=1401,
        message="予告出社成功",
        condition="予告出社を成功させた",
        level=1,
        score=1,
        badge_type_id=14,
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
]
