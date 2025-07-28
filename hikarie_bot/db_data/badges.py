"""Module that defines badge types and badges for the 出社登録BOT.

Classes:
    BadgeType: Represents a type of badge with an id, name, and description.
    Badge: Represents a badge with a message, condition, level, score, and badge type id.

Variables:
    BadgeTypes (list): A list of BadgeType instances defining various badge types.
    Badges (list): A list of Badge instances defining various badges and their conditions.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy.orm import Session

from hikarie_bot.constants import KIRIBAN_ID_COUNTS
from hikarie_bot.exceptions import CheckerFunctionNotSpecifiedError
from hikarie_bot.models import Badge, BadgeType, GuestArrivalInfo
from hikarie_bot.utils import list_bizdays


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
        self.checkers = [checker_map[badge_type_id] for badge_type_id in self.badge_type_to_check]

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
            15: cls.check_start_dash,
            16: cls.check_specific_day,
            17: cls.check_yearly_specific_day,
            18: cls.check_specific_time,
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

        """
        return [badge for checker in self.checkers for badge in checker(session, user_id, target_date)]

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

        """
        ID = 101  # noqa: N806
        if cls._arrived_check(session, user_id, target_date) is None:
            return []
        # check if the user has acquired the welcome badge
        start_of_the_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
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

        """
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

        """
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

        """
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
            recently_achieved_badges = cls.check_straight_flash(session, user_id, user_arrival.arrival_time)
            logger.debug(f"recently_achieved_badges: {recently_achieved_badges}")

            recently_achieved_badge_ids |= {badge.id for badge in recently_achieved_badges}
        logger.debug(f"recently_achieved_badge_ids: {recently_achieved_badge_ids}")

        _achieved_badges = []
        if ID_lv1 not in recently_achieved_badge_ids:
            _achieved_badges.append(cls.get_badge(session, ID_lv1))

        arrival_hours = {user_arrival.arrival_time.hour for user_arrival in user_arrivals}
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

        """
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
        ID_lv4 = 504  # noqa: N806

        @dataclass
        class _TimeWindow:
            start: int
            end: int

        lv1_time_window = _TimeWindow(11, 18)
        lv2_time_window = _TimeWindow(9, 11)
        lv3_time_window = _TimeWindow(7, 9)
        lv4_time_window = _TimeWindow(6, 7)

        user_arrival = cls._arrived_check(session, user_id, target_date)
        if user_arrival is None:
            return []

        arrival_hour = user_arrival.arrival_time.hour

        if lv4_time_window.start <= arrival_hour < lv4_time_window.end:
            return [session.query(Badge).filter(Badge.id == ID_lv4).one()]
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

        """
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

        """
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
            if last_arrival.arrival_time.date() + time_span < user_arrival.arrival_time.date():
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

        """
        ID_lv1 = 801  # noqa: N806
        ID_lv2 = 802  # noqa: N806
        ID_lv3 = 803  # noqa: N806

        user_arrival = cls._arrived_check(session, user_id, target_date)
        if user_arrival is None:
            return []

        arrived_minute_start = user_arrival.arrival_time.replace(second=0, microsecond=0)

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

    @classmethod
    def check_start_dash(
        cls,
        session: Session,
        user_id: str,
        target_date: datetime,
    ) -> list[Badge]:
        """Check if the user has acquired the start dash badge.

        Args:
        ----
            session (Session): The session factory to interact with the database.
            user_id (str): The ID of the user to check for badge acquisition.
            target_date (datetime): The date and time in JST to check for badge acquisition.

        Returns:
        -------
            list[Badge]: A tuple of badges acquired by the user, or [] if no badge is acquired.
        """
        BADGE_TYPE_ID = 15  # noqa: N806
        ID = 1501  # noqa: N806
        user_arrival = cls._arrived_check(session, user_id, target_date)
        if user_arrival is None:
            return []

        # get the apply start date of the BadgeType

        badge_type = session.query(BadgeType).filter(BadgeType.id == BADGE_TYPE_ID).one()
        initial_arrival = (
            session.query(GuestArrivalInfo)
            .filter(
                GuestArrivalInfo.user_id == user_id,
                GuestArrivalInfo.arrival_time >= badge_type.apply_start,
                GuestArrivalInfo.arrival_time <= user_arrival.arrival_time,
            )
            .first()
        )

        # if there is initial arrival and the current arrival is within 2 weekds
        if initial_arrival and user_arrival.arrival_time - initial_arrival.arrival_time <= timedelta(days=14):
            return [session.query(Badge).filter(Badge.id == ID).one()]
        return []

    @classmethod
    def check_specific_day(
        cls,
        session: Session,
        user_id: str,
        target_date: datetime,
    ) -> list[Badge]:
        """Check if the user has acquired the specific day badge.

        Args:
        ----
            session (Session): The session factory to interact with the database.
            user_id (str): The ID of the user to check for badge acquisition.
            target_date (datetime): The date and time in JST to check for badge acquisition.

        Returns:
        -------
            list[Badge]: A tuple of badges acquired by the user, or [] if no badge is acquired.

        """
        ID_2024_end = 1601  # noqa: N806
        ID_2025_start = 1602  # noqa: N806

        if not cls.apply_start_check(session=session, target_date=target_date, badge_type_id=16):
            return []

        user_arrival = cls._arrived_check(session, user_id, target_date)
        if user_arrival is None:
            return []

        if user_arrival.arrival_time.date() == datetime(2024, 12, 27, tzinfo=ZoneInfo("Asia/Tokyo")).date():
            return [session.query(Badge).filter(Badge.id == ID_2024_end).one()]
        if user_arrival.arrival_time.date() == datetime(2025, 1, 6, tzinfo=ZoneInfo("Asia/Tokyo")).date():
            return [session.query(Badge).filter(Badge.id == ID_2025_start).one()]
        return []

    @classmethod
    def check_yearly_specific_day(  # noqa: PLR0911
        cls,
        session: Session,
        user_id: str,
        target_date: datetime,
    ) -> list[Badge]:
        """Check if the user has acquired the yearly specific day badge.

        Args:
        ----
            session (Session): The session factory to interact with the database.
            user_id (str): The ID of the user to check for badge acquisition.
            target_date (datetime): The date and time in JST to check for badge acquisition.

        Returns:
        -------
            list[Badge]: A tuple of badges acquired by the user, or [] if no badge is acquired.

        """
        ID_christmas = 1701  # noqa: N806
        ID_workyear_end = 1702  # noqa: N806
        ID_new_workyear_start = 1703  # noqa: N806
        ID_golden_week = 1704  # noqa: N806

        if not cls.apply_start_check(session=session, target_date=target_date, badge_type_id=17):
            return []

        user_arrival = cls._arrived_check(session, user_id, target_date)
        if user_arrival is None:
            return []
        month = user_arrival.arrival_time.date().month
        day = user_arrival.arrival_time.date().day
        if (month, day) == (12, 25):
            return [session.query(Badge).filter(Badge.id == ID_christmas).one()]

        logger.info(f"month: {month}, day: {day}")
        if month == 3 and (24 < day <= 31):  # noqa: PLR2004
            # check if the user has not achieved this badge within the last 7 days
            year = user_arrival.arrival_time.date().year
            date_3_25 = datetime(year, 3, 25, tzinfo=ZoneInfo("Asia/Tokyo"))
            recent_arrival_count = (
                session.query(GuestArrivalInfo)
                .filter(
                    GuestArrivalInfo.user_id == user_id,
                    GuestArrivalInfo.arrival_time >= date_3_25,
                    GuestArrivalInfo.arrival_time < target_date,
                )
                .count()
            )
            if recent_arrival_count == 0:
                return [session.query(Badge).filter(Badge.id == ID_workyear_end).one()]

        if month == 4 and (1 <= day < 8):  # noqa: PLR2004
            # check if the user has not achieved this badge within the last 7 days
            year = user_arrival.arrival_time.date().year
            date_4_1 = datetime(year, 4, 1, tzinfo=ZoneInfo("Asia/Tokyo"))
            recent_arrival_count = (
                session.query(GuestArrivalInfo)
                .filter(
                    GuestArrivalInfo.user_id == user_id,
                    GuestArrivalInfo.arrival_time >= date_4_1,
                    GuestArrivalInfo.arrival_time < target_date,
                )
                .count()
            )
            if recent_arrival_count == 0:
                return [session.query(Badge).filter(Badge.id == ID_new_workyear_start).one()]

        if (month, day) in {(4, 29), (4, 30), (5, 1), (5, 2), (5, 3), (5, 4), (5, 5)}:
            return [session.query(Badge).filter(Badge.id == ID_golden_week).one()]

        return []

    @classmethod
    def check_specific_time(  # noqa: PLR0911
        cls,
        session: Session,
        user_id: str,
        target_date: datetime,
    ) -> list[Badge]:
        """Check if the user has acquired the specific time badge.

        Args:
        ----
            session (Session): The session factory to interact with the database.
            user_id (str): The ID of the user to check for badge acquisition.
            target_date (datetime): The date and time in JST to check for badge acquisition.

        Returns:
        -------
            list[Badge]: A tuple of badges acquired by the user, or [] if no badge is acquired.

        """
        # > # BadgeTypeData id=18, name="specific_time", description="特定の時間に出社した"
        # > BadgeData(
        # >     id=1801,
        # >     message="隣同士",
        # >     condition="時間と分が隣接した数字の時に出社した",
        # >     level=1,
        # >     score=2,
        # >     badge_type_id=18,
        # > ),
        # > BadgeData(
        # >     id=1802,
        # >     message="ぞろ目出社",
        # >     condition="時間と分が同じ数字の時に出社した",
        # >     level=2,
        # >     score=3,
        # >     badge_type_id=18,
        # > ),
        # > BadgeData(
        # >     id=1803,
        # >     message="階段",
        # >     condition="時間が連続した数字の時に出社した",
        # >     level=3,
        # >     score=4,
        # >     badge_type_id=18,
        # > ),
        # > BadgeData(
        # >     id=1804,
        # >     message="せーの...ポッキー!",
        # >     condition="11:11に出社した",
        # >     level=4,
        # >     score=5,
        # >     badge_type_id=18,
        # > ),
        # > BadgeData(
        # >     id=1805,
        # >     message="もしやあなたはモフ好きですね",
        # >     condition="11:22に出社した",
        # >     level=4,
        # >     score=5,
        # >     badge_type_id=18,
        # > ),
        # > BadgeData(
        # >     id=1806,
        # >     message="今夜は:yakiniku:",
        # >     condition="11:29に出社した",
        # >     level=4,
        # >     score=5,
        # >     badge_type_id=18,
        # > ),
        # > BadgeData(
        # >     id=1807,
        # >     message="真実はいつもひとつ",
        # >     condition="9:10に出社した",
        # >     level=4,
        # >     score=5,
        # >     badge_type_id=18,
        # > ),

        ID_lv1 = 1801  # noqa: N806
        ID_lv2 = 1802  # noqa: N806
        ID_lv3_1234 = 1803  # noqa: N806
        ID_lv3_1111 = 1804  # noqa: N806
        ID_lv3_1122 = 1805  # noqa: N806
        ID_lv3_1129 = 1806  # noqa: N806
        ID_lv3_0910 = 1807  # noqa: N806

        if not cls.apply_start_check(session=session, target_date=target_date, badge_type_id=18):
            return []

        user_arrival = cls._arrived_check(session, user_id, target_date)
        if user_arrival is None:
            return []

        arrival_time = user_arrival.arrival_time
        hour, minute = arrival_time.hour, arrival_time.minute

        if hour == minute == 11:  # noqa: PLR2004
            return [session.query(Badge).filter(Badge.id == ID_lv3_1111).one()]

        if (hour, minute) == (11, 22):
            return [session.query(Badge).filter(Badge.id == ID_lv3_1122).one()]

        if (hour, minute) == (11, 29):
            return [session.query(Badge).filter(Badge.id == ID_lv3_1129).one()]

        if (hour, minute) == (9, 10):
            return [session.query(Badge).filter(Badge.id == ID_lv3_0910).one()]

        if (hour, minute) == (12, 34):
            return [session.query(Badge).filter(Badge.id == ID_lv3_1234).one()]

        if hour == minute:
            return [session.query(Badge).filter(Badge.id == ID_lv2).one()]

        if abs(hour - minute) == 1:
            return [session.query(Badge).filter(Badge.id == ID_lv1).one()]

        return []

    @classmethod
    def apply_start_check(cls, session: Session, target_date: datetime, badge_type_id: int) -> bool:
        """Check if the badge can be applied.

        Args:
        ----
            session (Session): The session factory to interact with the database.
            target_date (datetime): The date and time in JST to check for badge acquisition.
            badge_type_id (int): The ID of the badge type to check for badge acquisition.

        Returns:
        -------
            bool: True if the badge can be applied, False otherwise.

        """
        badge_type = session.query(BadgeType).filter(BadgeType.id == badge_type_id).one()
        return target_date >= badge_type.apply_start


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
        message="1100番目のお客様",
        condition="1100回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=621,
        message="1111番目のお客様",
        condition="1111回目の出社登録をした",
        level=1,
        score=10,
        badge_type_id=6,
    ),
    BadgeData(
        id=622,
        message="1200番目のお客様",
        condition="1200回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=623,
        message="1222番目のお客様",
        condition="1222回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=624,
        message="1234番目のお客様",
        condition="1234回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=625,
        message="1300番目のお客様",
        condition="1300回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=626,
        message="1333番目のお客様",
        condition="1333回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=627,
        message="1400番目のお客様",
        condition="1400回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=628,
        message="1444番目のお客様",
        condition="1444回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=629,
        message="1500番目のお客様",
        condition="1500回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=630,
        message="1555番目のお客様",
        condition="1555回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=631,
        message="1600番目のお客様",
        condition="1600回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=632,
        message="1666番目のお客様",
        condition="1666回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=633,
        message="1700番目のお客様",
        condition="1700回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=634,
        message="1777番目のお客様",
        condition="1777回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=635,
        message="1800番目のお客様",
        condition="1800回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=636,
        message="1888番目のお客様",
        condition="1888回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=637,
        message="1900番目のお客様",
        condition="1900回目の出社登録をした",
        level=1,
        score=5,
        badge_type_id=6,
    ),
    BadgeData(
        id=638,
        message="1999番目のお客様",
        condition="1999回目の出社登録をした",
        level=1,
        score=10,
        badge_type_id=6,
    ),
    BadgeData(
        id=639,
        message="2000番目のお客様",
        condition="2000回目の出社登録をした",
        level=1,
        score=10,
        badge_type_id=6,
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
]
