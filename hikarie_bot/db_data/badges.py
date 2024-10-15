"""Module that defines badge types and badges for the 出社登録BOT.

Classes:
    BadgeType: Represents a type of badge with an id, name, and description.
    Badge: Represents a badge with a message, condition, level, score, and badge type id.

Variables:
    BadgeTypes (list): A list of BadgeType instances defining various badge types.
    Badges (list): A list of Badge instances defining various badges and their conditions.
"""  # noqa: E501

from datetime import datetime, timedelta
from typing import Self

from sqlalchemy.orm import Session

from hikarie_bot.models import Achievement, Badge, BadgeType, GuestArrivalInfo


class BadgeChecker:
    """Class for checking if a user has acquired a badge."""

    def __init__(self) -> Self:
        """Initialize the BadgeChecker with an empty list of badges."""
        checkers = {
            1: self.check_welcome,
            2: self.check_fastest_arrival,
            # 3: self.check_arrival_count,
            # 4: self.check_straight_flash,
            # 5: self.check_time_window,
            # 6: self.check_kiriban,
            # 7: self.check_long_time_no_see,
            # 8: self.check_lucky_you_guys,
            # 9: self.check_reincarnation,
            # 10: self.check_item_shop,
            # 11: self.check_used_log_report,
            # 12: self.check_seasonal_rank,
            # 13: self.check_reactioner,
            # 14: self.check_advance_notice_success,
        }

        # select badge types to check
        self.badge_type_to_check = [
            1,
            2,
        ]

        # define active checker functions
        self.checkers = [
            checkers[badge_type_id] for badge_type_id in self.badge_type_to_check
        ]

    def check(
        self,
        session: Session,
        user_id: str,
        jst_date: datetime,
        *,
        inline: bool = False,
    ) -> None:
        """Check if a user has acquired a badge.

        Args:
        ----
            session (Session): The session factory to interact with the database.
            user_id (str): The ID of the user to check for badge acquisition.
            jst_date (datetime): The date and time in JST to check for badge acquisition.
            inline (bool): Whether to update the badge information directly in the database.

        Returns:
        -------
            None

        """  # noqa: E501
        for checker in self.checkers:
            checker(session, user_id, jst_date, inline=inline)

    @classmethod
    def check_welcome(
        cls,
        session: Session,
        user_id: str,
        target_date: datetime,
        *,
        inline: bool = False,
    ) -> None:
        """Check if the user has acquired the welcome badge.

        Args:
        ----
            session (Session): The session factory to interact with the database.
            user_id (str): The ID of the user to check for badge acquisition.
            target_date (datetime): The date and time in JST to check for badge acquisition.
            inline (bool): Whether to update the badge information directly in the database.

        Returns:
        -------
            None

        """  # noqa: E501
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
        acquire_welcome_badge = previous_arrival_count == 0
        if inline and acquire_welcome_badge:
            first_arrival = (
                session.query(GuestArrivalInfo)
                .filter(
                    GuestArrivalInfo.user_id == user_id,
                    GuestArrivalInfo.arrival_time < start_of_the_day,
                )
                .one()
            )

            # update the badge information in the database
            session.add(
                Achievement(
                    user_id=user_id,
                    arrival_id=first_arrival.arrival_id,
                    badge_id=1,
                    achievement_time=first_arrival.arrival_time,
                )
            )
            session.commit()

        return acquire_welcome_badge

    @classmethod
    def check_fastest_arrival(
        cls,
        session: Session,
        user_id: str,
        target_date: datetime,
        *,
        inline: bool = False,
    ) -> None:
        """Check if the user has acquired the fastest arrival badge.

        Args:
        ----
            session (Session): The session factory to interact with the database.
            user_id (str): The ID of the user to check for badge acquisition.
            target_date (datetime): The date and time in JST to check for badge acquisition.
            inline (bool): Whether to update the badge information directly in the database.

        Returns:
        -------
            None

        """  # noqa: E501
        start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        # check if there is user before the current user

        user_arrival = (
            session.query(GuestArrivalInfo)
            .filter(
                GuestArrivalInfo.user_id == user_id,
                GuestArrivalInfo.arrival_time >= start_of_day,
                GuestArrivalInfo.arrival_time < end_of_day,
            )
            .one()
        )

        faster_arrival = (
            session.query(GuestArrivalInfo)
            .filter(
                GuestArrivalInfo.arrival_time >= start_of_day,
                GuestArrivalInfo.arrival_time < user_arrival.arrival_time,
            )
            .count()
        )

        user_is_fastest = faster_arrival == 0

        if inline and user_is_fastest:
            # update the badge information in the database
            session.add(
                Achievement(
                    user_id=user_id,
                    arrival_id=user_arrival.id,
                    badge_id=2,
                    achievement_time=user_arrival.arrival_time,
                )
            )
            session.commit()

        return user_is_fastest


# Define the badge types.
BadgeTypes = [
    BadgeType(
        id=1,
        name="welcome",
        description="出社登録BOTを初めて利用した",
    ),
    BadgeType(
        id=2,
        name="fastest_arrival",
        description="最速で出社登録をした",
    ),
    BadgeType(
        id=3,
        name="arrival_count",
        description="たくさん出社登録をした",
    ),
    BadgeType(
        id=4,
        name="straight_flash",
        description="連続して出社した",
    ),
    BadgeType(
        id=5,
        name="time_window",
        description="時間帯による出社登録",
    ),
    BadgeType(
        id=6,
        name="kiriban",
        description="特定の出社登録の回数で付与される",
    ),
    BadgeType(
        id=7,
        name="long_time_no_see",
        description="長期間出社登録がない状態で復帰した",
    ),
    BadgeType(
        id=8,
        name="lucky_you_guys",
        description="同じ時間に出社登録をした",
    ),
    BadgeType(
        id=9,
        name="reincarnation",
        description="転生した",
    ),
    BadgeType(
        id=10,
        name="item_shop",
        description="道具屋を利用した",
    ),
    BadgeType(
        id=11,
        name="used_log_report",
        description="ログ分析レポートを利用した",
    ),
    BadgeType(
        id=12, name="seasonal_rank", description="特定のシーズンでランクインした"
    ),
    BadgeType(
        id=13,
        name="reactioner",
        description="リアクションをした",
    ),
    BadgeType(
        id=14,
        name="advance_notice_success",
        description="予告出社を成功させた",
    ),
]


Badges = [
    # BadgeType id=1, name="welcome", description="出社登録BOTを初めて利用した"
    Badge(
        id=1,
        message="はじめての出社登録",
        condition="出社登録BOTを初めて利用した",
        level=1,
        score=1,
        badge_type_id=1,
    ),
    # BadgeType id=2, name="fastest_arrival", description="最速で出社登録をした"
    Badge(
        id=2,
        message="光の速さの出社",
        condition="最速で出社登録を行った",
        level=1,
        score=1,
        badge_type_id=2,
    ),
    # BadgeType id=3, name="arrival_count", description="たくさん出社登録をした"
    Badge(
        id=3,
        message="出社登録ビギナー",
        condition="5回出社登録した",
        level=1,
        score=1,
        badge_type_id=3,
    ),
    Badge(
        id=4,
        message="出社登録ユーザー",
        condition="20回出社登録した",
        level=2,
        score=1,
        badge_type_id=3,
    ),
    Badge(
        id=5,
        message="出社登録マスター",
        condition="100回出社登録した",
        level=3,
        score=1,
        badge_type_id=3,
    ),
    # BadgeType id=4, name="straight_flash", description="連続して出社した"
    Badge(
        id=6,
        message="ストレートフラッ出社",
        condition="5日連続で出社した",
        level=1,
        score=1,
        badge_type_id=4,
    ),
    Badge(
        id=7,
        message="ロイヤルストレートフラッ出社",
        condition="異なる時間帯に5日連続で出社した",
        level=2,
        score=1,
        badge_type_id=4,
    ),
    Badge(
        id=8,
        message="ウルトラロイヤルストレートフラッ出社",
        condition="異なる連続した時間帯に5日連続で出社した",
        level=3,
        score=1,
        badge_type_id=4,
    ),
    # BadgeType id=5, name="time_window", description="時間帯による出社登録"
    Badge(
        id=9,
        message="朝型出社",
        condition="6-9時の間に出社登録をした",
        level=3,
        score=1,
        badge_type_id=5,
    ),
    Badge(
        id=10,
        message="出社",
        condition="9-11時の間に出社登録をした",
        level=2,
        score=1,
        badge_type_id=5,
    ),
    Badge(
        id=11,
        message="遅めの出社",
        condition="11時以降に出社登録をした",
        level=1,
        score=1,
        badge_type_id=5,
    ),
    # BadgeType id=6, name="kiriban", description="特定の出社登録の回数で付与される"
    Badge(
        id=12,
        message="100番目のお客様",
        condition="100回目の出社登録をした",
        level=1,
        score=1,
        badge_type_id=6,
    ),
    # BadgeType id=7, name="long_time_no_see",
    #           description="長期間出社登録がない状態で復帰した"  # noqa: ERA001
    Badge(
        id=13,
        message="2週間ぶりですね、元気にしていましたか？",  # noqa: RUF001
        condition="14日以上出社登録がなかったが復帰した",
        level=1,
        score=1,
        badge_type_id=7,
    ),
    Badge(
        id=14,
        message="1か月ぶりですね、おかえりなさい。",
        condition="30日以上出社登録がなかったが復帰した",
        level=2,
        score=1,
        badge_type_id=7,
    ),
    Badge(
        id=15,
        message="2か月ぶりですね、顔を忘れるところでした。",
        condition="2か月以上出社登録がなかったが復帰した",
        level=4,
        score=1,
        badge_type_id=7,
    ),
    Badge(
        id=16,
        message="半年ぶりですね、むしろ初めまして。",
        condition="半年以上出社登録がなかったが復帰した",
        level=4,
        score=1,
        badge_type_id=7,
    ),
    # BadgeType id=8, name="lucky_you_guys", description="同じ時間に出社登録をした"
    Badge(
        id=17,
        message="幸運なふたり",
        condition="分単位で同じ時間に出社登録をした",
        level=1,
        score=1,
        badge_type_id=8,
    ),
    Badge(
        id=18,
        message="幸運なトリオ",
        condition="分単位で同じ時間に出社登録をした",
        level=2,
        score=1,
        badge_type_id=8,
    ),
    # BadgeType id=9, name="reincarnation", description="転生した"
    Badge(
        id=19,
        message="新しくなったあなた",
        condition="1回目の転生をした",
        level=1,
        score=1,
        badge_type_id=9,
    ),
    Badge(
        id=20,
        message="2回目の目覚め",
        condition="2回目の転生をした",
        level=2,
        score=1,
        badge_type_id=9,
    ),
    # BadgeType id=10, name="item_shop", description="道具屋を利用した"
    Badge(
        id=21,
        message="道具屋利用",
        condition="道具屋を利用した",
        level=1,
        score=1,
        badge_type_id=10,
    ),
    # BadgeType id=11, name="used_log_report", description="ログ分析レポートを利用した"
    Badge(
        id=22,
        message="ログ分析レポート利用",
        condition="ログ分析レポートを利用した",
        level=1,
        score=1,
        badge_type_id=11,
    ),
    # BadgeType id=12, name="seasonal_rank",
    #           description="特定のシーズンでランクインした" # noqa: ERA001
    Badge(
        id=23,
        message="Top of Top",
        condition="特定のシーズンで首位になった",
        level=2,
        score=1,
        badge_type_id=12,
    ),
    Badge(
        id=24,
        message="Seasonal Ranker",
        condition="特定のシーズンで3位以内になった",
        level=1,
        score=1,
        badge_type_id=12,
    ),
    # BadgeType id=13, name="reactioner", description="リアクションをした"
    Badge(
        id=25,
        message="盛り上げ役",
        condition="10回リアクションをした",
        level=1,
        score=1,
        badge_type_id=13,
    ),
    Badge(
        id=26,
        message="大衆の扇動者",
        condition="50回リアクションをした",
        level=2,
        score=1,
        badge_type_id=13,
    ),
    # BadgeType id=14, name="advance_notice_success", description="予告出社を成功させた"
    Badge(
        id=27,
        message="予告出社成功",
        condition="予告出社を成功させた",
        level=1,
        score=1,
        badge_type_id=14,
    ),
]
