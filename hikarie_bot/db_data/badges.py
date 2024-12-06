"""Module that defines badge types and badges for the 出社登録BOT.

Classes:
    BadgeType: Represents a type of badge with an id, name, and description.
    Badge: Represents a badge with a message, condition, level, score, and badge type id.

Variables:
    BadgeTypes (list): A list of BadgeType instances defining various badge types.
    Badges (list): A list of Badge instances defining various badges and their conditions.
"""  # noqa: E501

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache

from loguru import logger
from sqlalchemy.orm import Session

from hikarie_bot.constants import KIRIBAN_ID_COUNTS
from hikarie_bot.exceptions import CheckerFunctionNotSpecifiedError
from hikarie_bot.models import Badge, GuestArrivalInfo
from hikarie_bot.utils import list_bizdays


@dataclass
class BadgeTypeData:
    """Represents a type of badge with an id, name, and description."""

    id: int
    name: str
    description: str


@dataclass
class BadgeData:
    """Represents a badge with a message, condition, level, score, and badge type id."""

    id: int
    message: str
    condition: str
    level: int
    score: int
    badge_type_id: int


class BadgeChecker:
    """Class for checking if a user has acquired a badge."""

    def __init__(self, badge_type_to_check: list[int] | None) -> None:
        """Initialize the BadgeChecker with an empty list of badges."""
        if badge_type_to_check is None:
            raise CheckerFunctionNotSpecifiedError

        # select badge types to check
        self.badge_type_to_check = badge_type_to_check

        logger.info(f"badge_type_to_check: {self.badge_type_to_check}")

        checker_map = self.get_checker_map()

        # define active checker functions
        self.checkers = [
            checker_map[badge_type_id] for badge_type_id in self.badge_type_to_check
        ]

    @classmethod
    def get_checker_map(cls) -> dict[int, Callable]:
        """Return the checker map."""
        return {
            1: cls.check_welcome,
            2: cls.check_fastest_arrival,
            3: cls.check_arrival_count,
            4: cls.check_straight_flash,
            5: cls.check_time_window,
            6: cls.check_kiriban,
            7: cls.check_long_time_no_see,
            8: cls.check_lucky_you_guys,
            # 9: cls.check_reincarnation,
            # 10: cls.check_item_shop,
            # 11: cls.check_used_log_report,
            # 12: cls.check_seasonal_rank,
            # 13: cls.check_reactioner,
            # 14: cls.check_advance_notice_success,
        }

    @classmethod
    def get_available_badge_types(cls) -> list[int]:
        """Return the available badge types."""
        return list(cls.get_checker_map().keys())

    @classmethod
    def get_badge(cls, session: Session, badge_id: int) -> Badge:
        """Get a badge by its ID.

        Args:
        ----
            session (Session): The session factory to interact with the database.
            badge_id (int): The ID of the badge to get.

        Returns:
        -------
            Badge: The badge with the specified ID.

        """
        return session.query(Badge).filter(Badge.id == badge_id).one()

    @classmethod
    def _arrived_check(
        cls,
        session: Session,
        user_id: str,
        jst_date: datetime,
    ) -> GuestArrivalInfo | None:
        start_of_day = jst_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        # check if there is user before the current user
        return (
            session.query(GuestArrivalInfo)
            .filter(
                GuestArrivalInfo.user_id == user_id,
                GuestArrivalInfo.arrival_time >= start_of_day,
                GuestArrivalInfo.arrival_time < end_of_day,
            )
            .one_or_none()
        )

    def check(
        self,
        session: Session,
        user_id: str,
        target_date: datetime,
    ) -> list[Badge]:
        """Check if a user has acquired a badge.

        Args:
        ----
            session (Session): The session factory to interact with the database.
            user_id (str): The ID of the user to check for badge acquisition.
            target_date (datetime): The date and time in JST to check for badge acquisition.

        Returns:
        -------
            list[Badge]: A tuple of badges acquired by the user, or [] if no badge is acquired.

        """  # noqa: E501
        return [
            badge
            for checker in self.checkers
            for badge in checker(session, user_id, target_date)
        ]

    @classmethod
    def check_welcome(
        cls,
        session: Session,
        user_id: str,
        target_date: datetime,
    ) -> list[Badge]:
        """Check if the user has acquired the welcome badge.

        Args:
        ----
            session (Session): The session factory to interact with the database.
            user_id (str): The ID of the user to check for badge acquisition.
            target_date (datetime): The date and time in JST to check for badge acquisition.

        Returns:
        -------
            list[Badge]: A tuple of badges acquired by the user, or [] if no badge is acquired.

        """  # noqa: E501
        ID = 101  # noqa: N806
        if cls._arrived_check(session, user_id, target_date) is None:
            return []
        # check if the user has acquired the welcome badge
        start_of_the_day = target_date.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        previous_arrival_count = (
            session.query(GuestArrivalInfo)
            .filter(
                GuestArrivalInfo.user_id == user_id,
                GuestArrivalInfo.arrival_time < start_of_the_day,
            )
            .count()
        )

        # if the user had a previous arrival, they won't acquire the welcome badge
        if previous_arrival_count == 0:
            logger.info(session.query(Badge).all())
            return [session.query(Badge).filter(Badge.id == ID).one()]
        return []

    @classmethod
    def check_fastest_arrival(
        cls,
        session: Session,
        user_id: str,
        target_date: datetime,
    ) -> list[Badge]:
        """Check if the user has acquired the fastest arrival badge.

        Args:
        ----
            session (Session): The session factory to interact with the database.
            user_id (str): The ID of the user to check for badge acquisition.
            target_date (datetime): The date and time in JST to check for badge acquisition.

        Returns:
        -------
            list[Badge]: A tuple of badges acquired by the user, or [] if no badge is acquired.

        """  # noqa: E501
        ID = 201  # noqa: N806

        user_arrival = cls._arrived_check(session, user_id, target_date)
        if user_arrival is None:
            return []
        start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)

        faster_arrival = (
            session.query(GuestArrivalInfo)
            .filter(
                GuestArrivalInfo.arrival_time >= start_of_day,
                GuestArrivalInfo.arrival_time < user_arrival.arrival_time,
            )
            .count()
        )

        if faster_arrival == 0:
            return [cls.get_badge(session, ID)]
        return []

    @classmethod
    def check_arrival_count(
        cls,
        session: Session,
        user_id: str,
        target_date: datetime,
    ) -> list[Badge]:
        """Check if the user has acquired the arrival count badge.

        Args:
        ----
            session (Session): The session factory to interact with the database.
            user_id (str): The ID of the user to check for badge acquisition.
            target_date (datetime): The date and time in JST to check for badge acquisition.

        Returns:
        -------
            list[Badge]: A tuple of badges acquired by the user, or [] if no badge is acquired.

        """  # noqa: E501
        ID_lv1 = 301  # noqa: N806
        ID_lv2 = 302  # noqa: N806
        ID_lv3 = 303  # noqa: N806

        if cls._arrived_check(session, user_id, target_date) is None:
            return []

        start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        arrival_count = (
            session.query(GuestArrivalInfo)
            .filter(
                GuestArrivalInfo.user_id == user_id,
                GuestArrivalInfo.arrival_time < end_of_day,
            )
            .count()
        )

        match arrival_count:
            case 5:
                return [cls.get_badge(session, ID_lv1)]
            case 20:
                return [cls.get_badge(session, ID_lv2)]
            case 100:
                return [cls.get_badge(session, ID_lv3)]
            case _:
                return []

    @classmethod
    @lru_cache(maxsize=128)
    def check_straight_flash(
        cls,
        session: Session,
        user_id: str,
        target_date: datetime,
        flash_length: int = 5,
    ) -> list[Badge]:
        """Check if the user has acquired the straight flash badge.

        Args:
        ----
            session (Session): The session factory to interact with the database.
            user_id (str): The ID of the user to check for badge acquisition.
            target_date (datetime): The date and time in JST to check for badge acquisition.
            flash_length (int): The number of days to check for straight flash.

        Returns:
        -------
            list[Badge]: A tuple of badges acquired by the user, or [] if no badge is acquired.

        """  # noqa: E501
        ID_lv1 = 401  # noqa: N806
        ID_lv2 = 402  # noqa: N806
        ID_lv3 = 403  # noqa: N806

        if cls._arrived_check(session, user_id, target_date) is None:
            return []

        start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        # Get the user's arrival information including the current day
        user_arrivals = (
            session.query(GuestArrivalInfo)
            .filter(GuestArrivalInfo.user_id == user_id)
            .filter(GuestArrivalInfo.arrival_time < end_of_day)
            .order_by(GuestArrivalInfo.arrival_time.desc())
            .limit(flash_length)
            .all()
        )

        # Check if the user has at least 5 arrivals
        if len(user_arrivals) < flash_length:
            logger.info(f"not enough arrivals: {len(user_arrivals)}")
            return []

        # Check if the user has a straight flash

        valid_bizdays = list_bizdays(start_of_day, flash_length)

        conds = [
            bizday != user_arrival.arrival_time.date()
            for bizday, user_arrival in zip(valid_bizdays, user_arrivals, strict=True)
        ]
        if any(conds):
            logger.info("not straight flash.")
            return []

        # Check if the user has straight flash within last 5 arrivals
        recently_achieved_badge_ids: set[int] = set()

        # check if the user has already acquired the straight flash badge recently
        for user_arrival in user_arrivals[1:]:
            recently_achieved_badges = cls.check_straight_flash(
                session, user_id, user_arrival.arrival_time
            )
            logger.debug(f"recently_achieved_badges: {recently_achieved_badges}")

            recently_achieved_badge_ids |= {
                badge.id for badge in recently_achieved_badges
            }
        logger.debug(f"recently_achieved_badge_ids: {recently_achieved_badge_ids}")

        _achieved_badges = []
        if ID_lv1 not in recently_achieved_badge_ids:
            _achieved_badges.append(cls.get_badge(session, ID_lv1))

        arrival_hours = {
            user_arrival.arrival_time.hour for user_arrival in user_arrivals
        }
        if len(set(arrival_hours)) == flash_length:
            if ID_lv2 not in recently_achieved_badge_ids:
                _achieved_badges.append(cls.get_badge(session, ID_lv2))
            if ID_lv3 not in recently_achieved_badge_ids:
                sorted_arrival_hours = sorted(arrival_hours)
                max_hour = max(sorted_arrival_hours)
                min_hour = min(sorted_arrival_hours)
                if max_hour - min_hour == flash_length - 1:
                    _achieved_badges.append(cls.get_badge(session, ID_lv3))
        return _achieved_badges

    @classmethod
    def check_time_window(
        cls,
        session: Session,
        user_id: str,
        target_date: datetime,
    ) -> list[Badge]:
        """Check if the user has acquired the time window badge.

        Args:
        ----
            session (Session): The session factory to interact with the database.
            user_id (str): The ID of the user to check for badge acquisition.
            target_date (datetime): The date and time in JST to check for badge acquisition.

        Returns:
        -------
            list[Badge]: A tuple of badges acquired by the user, or [] if no badge is acquired.

        """  # noqa: E501
        # > # BadgeTypeData id=5, name="time_window", description="時間帯による出社登録"
        # > BadgeData(
        # >     id=9,
        # >     message="朝型出社",
        # >     condition="6-9時の間に出社登録をした",
        # >     level=3,
        # >     score=1,
        # >     badge_type_id=5,
        # > ),
        # > BadgeData(
        # >     id=10,
        # >     message="出社",
        # >     condition="9-11時の間に出社登録をした",
        # >     level=2,
        # >     score=1,
        # >     badge_type_id=5,
        # > ),
        # > BadgeData(
        # >     id=11,
        # >     message="遅めの出社",
        # >     condition="11時以降に出社登録をした",
        # >     level=1,
        # >     score=1,
        # >     badge_type_id=5,
        # > ),

        ID_lv1 = 503  # noqa: N806
        ID_lv2 = 502  # noqa: N806
        ID_lv3 = 501  # noqa: N806

        @dataclass
        class _TimeWindow:
            start: int
            end: int

        lv1_time_window = _TimeWindow(11, 18)
        lv2_time_window = _TimeWindow(9, 11)
        lv3_time_window = _TimeWindow(6, 9)

        user_arrival = cls._arrived_check(session, user_id, target_date)
        if user_arrival is None:
            return []

        arrival_hour = user_arrival.arrival_time.hour

        if lv3_time_window.start <= arrival_hour < lv3_time_window.end:
            return [session.query(Badge).filter(Badge.id == ID_lv3).one()]
        if lv2_time_window.start <= arrival_hour < lv2_time_window.end:
            return [session.query(Badge).filter(Badge.id == ID_lv2).one()]
        if lv1_time_window.start <= arrival_hour < lv1_time_window.end:
            return [session.query(Badge).filter(Badge.id == ID_lv1).one()]
        return []

    @classmethod
    def check_kiriban(
        cls,
        session: Session,
        user_id: str,
        target_date: datetime,
    ) -> list[Badge]:
        """Check if the user has acquired the kiriban badge.

        Args:
        ----
            session (Session): The session factory to interact with the database.
            user_id (str): The ID of the user to check for badge acquisition.
            target_date (datetime): The date and time in JST to check for badge acquisition.

        Returns:
        -------
            list[Badge]: A tuple of badges acquired by the user, or [] if no badge is acquired.

        """  # noqa: E501
        user_arrival = cls._arrived_check(session, user_id, target_date)
        if user_arrival is None:
            return []

        previous_arrival_count = (
            session.query(GuestArrivalInfo)
            .filter(
                GuestArrivalInfo.arrival_time < user_arrival.arrival_time,
            )
            .count()
        )
        for ID, kiriban_count in KIRIBAN_ID_COUNTS:  # noqa: N806
            if previous_arrival_count == kiriban_count - 1:
                return [session.query(Badge).filter(Badge.id == ID).one()]
        return []

    @classmethod
    def check_long_time_no_see(
        cls,
        session: Session,
        user_id: str,
        target_date: datetime,
    ) -> list[Badge]:
        """Check if the user has acquired the long time no see badge.

        Args:
        ----
            session (Session): The session factory to interact with the database.
            user_id (str): The ID of the user to check for badge acquisition.
            target_date (datetime): The date and time in JST to check for badge acquisition.
            no_see_days (int): The number of days to check for long time no see.

        Returns:
        -------
            list[Badge]: A tuple of badges acquired by the user, or [] if no badge is acquired.

        """  # noqa: E501
        ID_lv1 = 701  # noqa: N806
        ID_lv2 = 702  # noqa: N806
        ID_lv3 = 703  # noqa: N806
        ID_lv4 = 704  # noqa: N806

        from dateutil.relativedelta import relativedelta

        no_see_days_lv1 = timedelta(days=14)
        no_see_days_lv2 = timedelta(days=30)
        no_see_days_lv3 = relativedelta(months=2)
        no_see_days_lv4 = relativedelta(months=6)

        user_arrival = cls._arrived_check(session, user_id, target_date)
        if user_arrival is None:
            return []

        last_arrival = (
            session.query(GuestArrivalInfo)
            .filter(
                GuestArrivalInfo.user_id == user_id,
                GuestArrivalInfo.arrival_time < user_arrival.arrival_time,
            )
            .order_by(GuestArrivalInfo.arrival_time.desc())
            .first()
        )
        if last_arrival is None:
            return []

        for badge_id, time_span in zip(
            [ID_lv4, ID_lv3, ID_lv2, ID_lv1],
            [no_see_days_lv4, no_see_days_lv3, no_see_days_lv2, no_see_days_lv1],
            strict=False,
        ):
            if (
                last_arrival.arrival_time.date() + time_span
                < user_arrival.arrival_time.date()
            ):
                return [session.query(Badge).filter(Badge.id == badge_id).one()]

        return []

    @classmethod
    def check_lucky_you_guys(
        cls,
        session: Session,
        user_id: str,
        target_date: datetime,
    ) -> list[Badge]:
        """Check if the user has acquired the lucky you guys badge.

        Args:
        ----
            session (Session): The session factory to interact with the database.
            user_id (str): The ID of the user to check for badge acquisition.
            target_date (datetime): The date and time in JST to check for badge acquisition.

        Returns:
        -------
            list[Badge]: A tuple of badges acquired by the user, or [] if no badge is acquired.

        """  # noqa: E501
        ID_lv1 = 801  # noqa: N806
        ID_lv2 = 802  # noqa: N806
        ID_lv3 = 803  # noqa: N806

        user_arrival = cls._arrived_check(session, user_id, target_date)
        if user_arrival is None:
            return []

        arrived_minute_start = user_arrival.arrival_time.replace(
            second=0, microsecond=0
        )

        logger.info(f"arrived_minute_start: {arrived_minute_start}")
        logger.info(f"user_arrival.arrival_time: {user_arrival.arrival_time}")

        same_minute_arrivals = (
            session.query(GuestArrivalInfo)
            .filter(
                GuestArrivalInfo.arrival_time >= arrived_minute_start,
                GuestArrivalInfo.arrival_time <= user_arrival.arrival_time,
                GuestArrivalInfo.id <= user_arrival.id,
            )
            .count()
        )
        logger.info(f"same_minute_arrivals: {same_minute_arrivals}")

        if same_minute_arrivals == 2:  # noqa: PLR2004
            return [session.query(Badge).filter(Badge.id == ID_lv1).one()]
        if same_minute_arrivals == 3:  # noqa: PLR2004
            return [session.query(Badge).filter(Badge.id == ID_lv2).one()]
        if same_minute_arrivals == 4:  # noqa: PLR2004
            return [session.query(Badge).filter(Badge.id == ID_lv3).one()]
        return []


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
    BadgeTypeData(
        id=12, name="seasonal_rank", description="特定のシーズンでランクインした"
    ),
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
        condition="6-9時の間に出社登録をした",
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
    # BadgeTypeData id=6, name="kiriban", description="特定の出社登録の回数で付与される"
    BadgeData(
        id=601,
        message="100番目のお客様",
        condition="100回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=602,
        message="111番目のお客様",
        condition="111回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=603,
        message="200番目のお客様",
        condition="200回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=604,
        message="222番目のお客様",
        condition="222回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=605,
        message="300番目のお客様",
        condition="300回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=606,
        message="333番目のお客様",
        condition="333回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=607,
        message="400番目のお客様",
        condition="400回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=608,
        message="444番目のお客様",
        condition="444回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=609,
        message="500番目のお客様",
        condition="500回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=610,
        message="555番目のお客様",
        condition="555回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=611,
        message="600番目のお客様",
        condition="600回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=612,
        message="666番目のお客様",
        condition="666回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=613,
        message="700番目のお客様",
        condition="700回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=614,
        message="777番目のお客様",
        condition="777回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=615,
        message="800番目のお客様",
        condition="800回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=616,
        message="888番目のお客様",
        condition="888回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=617,
        message="900番目のお客様",
        condition="900回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=618,
        message="999番目のお客様",
        condition="999回目の出社登録をした",
        level=1,
        score=10,
        badge_type_id=6,
    ),
    BadgeData(
        id=619,
        message="1000番目のお客様",
        condition="1000回目の出社登録をした",
        level=1,
        score=10,
        badge_type_id=6,
    ),
    BadgeData(
        id=620,
        message="1111番目のお客様",
        condition="1111回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    # BadgeTypeData id=7, name="long_time_no_see",
    #           description="長期間出社登録がない状態で復帰した"  # noqa: ERA001
    BadgeData(
        id=701,
        message="2週間ぶりですね、元気にしていましたか？",  # noqa: RUF001
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
        level=2,
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
    # BadgeTypeData id=11, name="used_log_report", description="ログ分析レポートを利用した"  # noqa: E501
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
    # BadgeTypeData id=14, name="advance_notice_success", description="予告出社を成功させた"  # noqa: E501
    BadgeData(
        id=1401,
        message="予告出社成功",
        condition="予告出社を成功させた",
        level=1,
        score=1,
        badge_type_id=14,
    ),
]
