from dataclasses import dataclass
from datetime import datetime, timedelta
from unittest import mock

from loguru import logger
from sqlalchemy.orm import sessionmaker

from hikarie_bot.curd import initially_insert_badge_data, insert_arrival_action
from hikarie_bot.db_data.badges import BadgeChecker


@dataclass
class UserData:
    """Test data class."""

    user_id: str
    jst_datetime: datetime

    def __init__(self, user_id: str, jst_datetime: str | datetime) -> None:
        """Initialize the TestData class."""
        self.user_id = user_id
        if isinstance(jst_datetime, str):
            self.jst_datetime = datetime.fromisoformat(jst_datetime)
        else:
            self.jst_datetime = jst_datetime


@mock.patch("hikarie_bot.curd.BADGE_TYPES_TO_CHECK", [1])
def test_badge_checker_id1_welcome(temp_db: sessionmaker) -> None:
    """Test the badge checker."""
    with temp_db() as session:
        initially_insert_badge_data(session)
        badge = BadgeChecker.get_badge(session=session, badge_id=101)
        checker = BadgeChecker(badge_type_to_check=[1])

        # test scenario
        # 1. test_user:
        #   2024-01-01 06:00:00 (o:fastest, o:initial)<- [check]
        # 2. test_user_already_arrived:
        #   2024-01-02 06:00:00
        #   2024-01-03 06:00:00 (o:fastest, x:initial) <- [check]
        # 3. test_user_not_fastest:
        #   2024-01-03 07:00:00 (x:fastest, o:initial) <- [check]

        test_data = (
            UserData(jst_datetime="2024-01-01 06:00:00", user_id="user"),
            UserData(jst_datetime="2024-01-02 06:00:00", user_id="already_arrived"),
            UserData(jst_datetime="2024-01-03 06:00:00", user_id="already_arrived"),
            UserData(jst_datetime="2024-01-03 07:00:00", user_id="not_fastest"),
        )
        check_data = (
            ([badge], UserData(jst_datetime="2024-01-01", user_id="user")),
            ([], UserData(jst_datetime="2024-01-03", user_id="already_arrived")),
            ([badge], UserData(jst_datetime="2024-01-03", user_id="not_fastest")),
            ([], UserData(jst_datetime="2024-01-03", user_id="not_arrived")),
        )

        for data in test_data:
            insert_arrival_action(
                session=session,
                jst_datetime=data.jst_datetime,
                user_id=data.user_id,
            )

        for expected, data in check_data:
            assert expected == checker.check_welcome(
                session=session,
                user_id=data.user_id,
                target_date=data.jst_datetime,
            )
            assert expected == checker.check(
                session=session,
                user_id=data.user_id,
                target_date=data.jst_datetime,
            )


@mock.patch("hikarie_bot.curd.BADGE_TYPES_TO_CHECK", [2])
def test_badge_checker_id2_fastest_arrival(temp_db: sessionmaker) -> None:
    """Test the badge checker."""
    with temp_db() as session:
        initially_insert_badge_data(session)
        badge = BadgeChecker.get_badge(session=session, badge_id=201)
        checker = BadgeChecker([2])

        # test scenario
        # 1. test_user:
        #   2024-01-01 06:00:00 (o:fastest, o:initial)<- [check]
        # 2. test_user_already_arrived:
        #   2024-01-02 06:00:00
        #   2024-01-03 06:00:00 (o:fastest, x:initial) <- [check]
        # 3. test_user_not_fastest:
        #   2024-01-03 07:00:00 (x:fastest, o:initial) <- [check]

        test_data = (
            UserData(jst_datetime="2024-01-01 06:00:00", user_id="user"),
            UserData(jst_datetime="2024-01-02 06:00:00", user_id="already_arrived"),
            UserData(jst_datetime="2024-01-03 06:00:00", user_id="already_arrived"),
            UserData(jst_datetime="2024-01-03 07:00:00", user_id="not_fastest"),
        )
        check_data = (
            ([badge], UserData(jst_datetime="2024-01-01", user_id="user")),
            ([badge], UserData(jst_datetime="2024-01-03", user_id="already_arrived")),
            ([], UserData(jst_datetime="2024-01-03", user_id="not_fastest")),
            ([], UserData(jst_datetime="2024-01-03", user_id="not_arrived")),
        )

        for data in test_data:
            insert_arrival_action(
                session=session,
                jst_datetime=data.jst_datetime,
                user_id=data.user_id,
            )

        for expected, data in check_data:
            assert expected == checker.check_fastest_arrival(
                session=session,
                user_id=data.user_id,
                target_date=data.jst_datetime,
            )


@mock.patch("hikarie_bot.curd.BADGE_TYPES_TO_CHECK", [3])
@mock.patch("hikarie_bot.db_data.badges.KIRIBAN_ID_COUNTS", [(601, 10)])
def test_badge_checker_id3_arrival_count(temp_db: sessionmaker) -> None:
    """Test the badge checker."""
    with temp_db() as session:
        initially_insert_badge_data(session)
        badge_5 = BadgeChecker.get_badge(session=session, badge_id=301)
        checker = BadgeChecker([3])

        # Badge types are below:
        # > # BadgeType id=3, name="arrival_count", description="たくさん出社登録をした"
        # > Badge(
        # >     id=3,
        # >     message="出社登録ビギナー",
        # >     condition="5回出社登録した",
        # >     level=1,
        # >     score=1,
        # >     badge_type_id=3,
        # > ),
        # > Badge(
        # >     id=4,
        # >     message="出社登録ユーザー",
        # >     condition="20回出社登録した",
        # >     level=2,
        # >     score=1,
        # >     badge_type_id=3,
        # > ),
        # > Badge(
        # >     id=5,
        # >     message="出社登録マスター",
        # >     condition="100回出社登録した",
        # >     level=3,
        # >     score=1,
        # >     badge_type_id=3,
        # > ),

        # test scenario
        # 1. user arrived 5 times
        # 4. user arrived 4 times

        test_data = (
            *[
                UserData(
                    jst_datetime=datetime.fromisoformat("20200101 06:00:00")
                    + timedelta(days=i),
                    user_id="user",
                )
                for i in range(5)
            ],
            *[
                UserData(
                    jst_datetime=datetime.fromisoformat("20200101 06:00:00")
                    + timedelta(days=i),
                    user_id="user_4",
                )
                for i in range(4)
            ],
        )
        check_data = (
            # scenario 1
            ([], UserData(jst_datetime="2020-01-04", user_id="user")),
            ([badge_5], UserData(jst_datetime="2020-01-05", user_id="user")),
            ([], UserData(jst_datetime="2020-01-06", user_id="user")),
            # scenario 4
            ([], UserData(jst_datetime="2020-01-04", user_id="user_4")),
            ([], UserData(jst_datetime="2020-01-05", user_id="user_4")),
            # fail because the user has not arrived 5 times
        )

        for data in test_data:
            insert_arrival_action(
                session=session,
                jst_datetime=data.jst_datetime,
                user_id=data.user_id,
            )

        for expected, data in check_data:
            assert expected == checker.check_arrival_count(
                session=session,
                user_id=data.user_id,
                target_date=data.jst_datetime,
            )


@mock.patch("hikarie_bot.curd.BADGE_TYPES_TO_CHECK", [4])
def test_badge_checker_id4_straight_flash(temp_db: sessionmaker) -> None:
    """Test the badge checker."""
    with temp_db() as session:
        initially_insert_badge_data(session)
        badge_lv1 = BadgeChecker.get_badge(session=session, badge_id=401)
        badge_lv2 = BadgeChecker.get_badge(session=session, badge_id=402)
        badge_lv3 = BadgeChecker.get_badge(session=session, badge_id=403)
        checker = BadgeChecker([4])

        # > # BadgeTypeData id=4, name="straight_flash", description="連続して出社した"
        # > BadgeData(
        # >     id=6,
        # >     message="ストレートフラッ出社",
        # >     condition="5日連続で出社した",
        # >     level=1,
        # >     score=1,
        # >     badge_type_id=4,
        # > ),
        # > BadgeData(
        # >     id=7,
        # >     message="ロイヤルストレートフラッ出社",
        # >     condition="異なる時間帯に5日連続で出社した",
        # >     level=2,
        # >     score=1,
        # >     badge_type_id=4,
        # > ),
        # > BadgeData(
        # >     id=8,
        # >     message="ウルトラロイヤルストレートフラッ出社",
        # >     condition="異なる連続した時間帯に5日連続で出社した",
        # >     level=3,
        # >     score=1,
        # >     badge_type_id=4,
        # > ),

        # test scenario
        # 1. sample straight flash
        # 2024-04-22, 2024-04-23, 2024-04-24, 2024-04-25, 2024-04-26 @ 7x5
        # 2. longest straight flash
        # 2024-04-26, 2024-04-30, 2024-05-01, 2024-05-02, 2024-05-07 @ 7x5
        # 3. sample failing straight flash
        # 2024-04-22, 2024-04-23, 2024-04-24, 2024-04-25, 2024-04-30 @ 7x5
        # 4. loyal straight flash
        # 2024-04-22, 2024-04-23, 2024-04-24, 2024-04-25, 2024-04-26 @ 7,8,10,12,14
        # 5. ultra loyal straight flash
        # 2024-04-22, 2024-04-23, 2024-04-24, 2024-04-25, 2024-04-26 @ 7,8,9,10,11
        # 6. acquire all badges
        # 2024-04-22, 04-23, 04-24, 04-25, 04-26, 04-30, 05-01
        # @ 7, 7, 8, 9, 10, 12, 11
        # 7. cooltime = 5 days
        # 2024/4/22, 23, 24, 25, 26(5), 30, 5/1, 2, 7, 8(10)  # noqa: ERA001

        test_data = (
            # 1
            UserData(jst_datetime="2024-04-22 07:00:00", user_id="user_1"),
            UserData(jst_datetime="2024-04-23 07:00:00", user_id="user_1"),
            UserData(jst_datetime="2024-04-24 07:00:00", user_id="user_1"),
            UserData(jst_datetime="2024-04-25 07:00:00", user_id="user_1"),
            UserData(jst_datetime="2024-04-26 07:00:00", user_id="user_1"),
            # 2
            UserData(jst_datetime="2024-04-26 07:00:00", user_id="user_2"),
            UserData(jst_datetime="2024-04-30 07:00:00", user_id="user_2"),
            UserData(jst_datetime="2024-05-01 07:00:00", user_id="user_2"),
            UserData(jst_datetime="2024-05-02 07:00:00", user_id="user_2"),
            UserData(jst_datetime="2024-05-07 07:00:00", user_id="user_2"),
            # 3
            UserData(jst_datetime="2024-04-22 07:00:00", user_id="user_3"),
            UserData(jst_datetime="2024-04-23 07:00:00", user_id="user_3"),
            UserData(jst_datetime="2024-04-24 07:00:00", user_id="user_3"),
            UserData(jst_datetime="2024-04-25 07:00:00", user_id="user_3"),
            UserData(jst_datetime="2024-04-30 07:00:00", user_id="user_3"),
            # 4
            UserData(jst_datetime="2024-04-22 07:00:00", user_id="user_4"),
            UserData(jst_datetime="2024-04-23 08:00:00", user_id="user_4"),
            UserData(jst_datetime="2024-04-24 10:00:00", user_id="user_4"),
            UserData(jst_datetime="2024-04-25 12:00:00", user_id="user_4"),
            UserData(jst_datetime="2024-04-26 14:00:00", user_id="user_4"),
            # 5
            UserData(jst_datetime="2024-04-22 07:00:00", user_id="user_5"),
            UserData(jst_datetime="2024-04-23 08:00:00", user_id="user_5"),
            UserData(jst_datetime="2024-04-24 09:00:00", user_id="user_5"),
            UserData(jst_datetime="2024-04-25 10:00:00", user_id="user_5"),
            UserData(jst_datetime="2024-04-26 11:00:00", user_id="user_5"),
            # 6
            UserData(jst_datetime="2024-04-22 07:00:00", user_id="user_6"),
            UserData(jst_datetime="2024-04-23 07:00:00", user_id="user_6"),
            UserData(jst_datetime="2024-04-24 08:00:00", user_id="user_6"),
            UserData(jst_datetime="2024-04-25 09:00:00", user_id="user_6"),
            UserData(jst_datetime="2024-04-26 10:00:00", user_id="user_6"),
            UserData(jst_datetime="2024-04-30 12:00:00", user_id="user_6"),
            UserData(jst_datetime="2024-05-01 11:00:00", user_id="user_6"),
            # 7
            UserData(jst_datetime="2024-04-22 07:00:00", user_id="user_7"),
            UserData(jst_datetime="2024-04-23 07:00:00", user_id="user_7"),
            UserData(jst_datetime="2024-04-24 07:00:00", user_id="user_7"),
            UserData(jst_datetime="2024-04-25 07:00:00", user_id="user_7"),
            UserData(jst_datetime="2024-04-26 07:00:00", user_id="user_7"),
            UserData(jst_datetime="2024-04-30 07:00:00", user_id="user_7"),
            UserData(jst_datetime="2024-05-01 07:00:00", user_id="user_7"),
            UserData(jst_datetime="2024-05-02 07:00:00", user_id="user_7"),
            UserData(jst_datetime="2024-05-07 07:00:00", user_id="user_7"),
            UserData(jst_datetime="2024-05-08 07:00:00", user_id="user_7"),
        )
        check_data = (
            # 1
            ([], UserData(jst_datetime="2024-04-25", user_id="user_1")),
            ([badge_lv1], UserData(jst_datetime="2024-04-26", user_id="user_1")),
            ([], UserData(jst_datetime="2024-05-01", user_id="user_1")),
            # 2
            ([], UserData(jst_datetime="2024-05-02", user_id="user_2")),
            ([badge_lv1], UserData(jst_datetime="2024-05-07", user_id="user_2")),
            ([], UserData(jst_datetime="2024-05-08", user_id="user_2")),
            # 3
            ([], UserData(jst_datetime="2024-04-26", user_id="user_3")),
            ([], UserData(jst_datetime="2024-04-30", user_id="user_3")),
            ([], UserData(jst_datetime="2024-05-01", user_id="user_3")),
            # 4
            ([], UserData(jst_datetime="2024-04-25", user_id="user_4")),
            (
                [badge_lv1, badge_lv2],
                UserData(jst_datetime="2024-04-26", user_id="user_4"),
            ),
            ([], UserData(jst_datetime="2024-04-27", user_id="user_4")),
            # 5
            ([], UserData(jst_datetime="2024-04-25", user_id="user_5")),
            (
                [badge_lv1, badge_lv2, badge_lv3],
                UserData(jst_datetime="2024-04-26", user_id="user_5"),
            ),
            ([], UserData(jst_datetime="2024-04-27", user_id="user_5")),
            # 6
            ([], UserData(jst_datetime="2024-04-25", user_id="user_6")),
            ([badge_lv1], UserData(jst_datetime="2024-04-26", user_id="user_6")),
            ([badge_lv2], UserData(jst_datetime="2024-04-30", user_id="user_6")),
            ([badge_lv3], UserData(jst_datetime="2024-05-01", user_id="user_6")),
            # 7
            ([], UserData(jst_datetime="2024-04-25", user_id="user_7")),
            ([badge_lv1], UserData(jst_datetime="2024-04-26", user_id="user_7")),
            ([], UserData(jst_datetime="2024-05-07", user_id="user_7")),
            ([badge_lv1], UserData(jst_datetime="2024-05-08", user_id="user_7")),
        )

        for data in test_data:
            insert_arrival_action(
                session=session,
                jst_datetime=data.jst_datetime,
                user_id=data.user_id,
            )

        for expected, data in check_data:
            logger.info(f"expected: {expected}, data: {data}")
            assert expected == checker.check_straight_flash(
                session=session,
                user_id=data.user_id,
                target_date=data.jst_datetime,
            )


@mock.patch("hikarie_bot.curd.BADGE_TYPES_TO_CHECK", [5])
def test_badge_checker_id5_time_window(temp_db: sessionmaker) -> None:
    """Test the badge checker."""
    with temp_db() as session:
        initially_insert_badge_data(session)
        badge_lv1 = BadgeChecker.get_badge(session=session, badge_id=503)
        badge_lv2 = BadgeChecker.get_badge(session=session, badge_id=502)
        badge_lv3 = BadgeChecker.get_badge(session=session, badge_id=501)
        badge_lv4 = BadgeChecker.get_badge(session=session, badge_id=504)
        checker = BadgeChecker([5])

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

        # test scenario
        # success
        # 1. @ 06:00:00 -> lv3
        # 2. @ 09:00:00 -> lv2
        # 3. @ 11:00:00 -> lv1
        # fail
        # 4. @ 05:59:59
        # 5. @ 18:00:00

        test_data = (
            UserData(jst_datetime="2024-04-22 06:00:00", user_id="user_1"),
            UserData(jst_datetime="2024-04-22 09:00:00", user_id="user_2"),
            UserData(jst_datetime="2024-04-22 11:00:00", user_id="user_3"),
            UserData(jst_datetime="2024-04-22 05:59:59", user_id="user_4"),
            UserData(jst_datetime="2024-04-22 18:00:00", user_id="user_5"),
            UserData(jst_datetime="2024-04-22 07:00:00", user_id="user_6"),
        )
        check_data = (
            ([badge_lv4], UserData(jst_datetime="2024-04-22", user_id="user_1")),
            ([badge_lv2], UserData(jst_datetime="2024-04-22", user_id="user_2")),
            ([badge_lv1], UserData(jst_datetime="2024-04-22", user_id="user_3")),
            ([], UserData(jst_datetime="2024-04-22", user_id="user_4")),
            ([], UserData(jst_datetime="2024-04-22", user_id="user_5")),
            ([badge_lv3], UserData(jst_datetime="2024-04-22", user_id="user_6")),
        )

        for data in test_data:
            insert_arrival_action(
                session=session,
                jst_datetime=data.jst_datetime,
                user_id=data.user_id,
            )

        for idx, (expected, data) in enumerate(check_data):
            assert expected == checker.check_time_window(
                session=session,
                user_id=data.user_id,
                target_date=data.jst_datetime,
            ), f"failed: {idx}"


@mock.patch("hikarie_bot.db_data.badges.KIRIBAN_ID_COUNTS", [(601, 10)])
@mock.patch("hikarie_bot.curd.BADGE_TYPES_TO_CHECK", [6])
def test_badge_checker_id6_kiriban(
    temp_db: sessionmaker,
) -> None:
    """Test the badge checker."""
    with temp_db() as session:
        initially_insert_badge_data(session)
        badge_n100 = BadgeChecker.get_badge(session=session, badge_id=601)
        checker = BadgeChecker([6])

        test_data = (
            *[
                UserData(
                    jst_datetime=datetime.fromisoformat("20200101 06:00:00")
                    + timedelta(seconds=i),
                    user_id=f"user_{i}",
                )
                for i in range(9)
            ],
            UserData(
                jst_datetime=datetime.fromisoformat("20200102 06:00:00"),
                user_id="user_kiriban_10",
            ),
        )
        check_data = (
            ([], UserData(jst_datetime="2020-01-01", user_id="user_0")),
            (
                [badge_n100],
                UserData(jst_datetime="2020-01-02", user_id="user_kiriban_10"),
            ),
        )

        for data in test_data:
            insert_arrival_action(
                session=session,
                jst_datetime=data.jst_datetime,
                user_id=data.user_id,
            )

        for expected, data in check_data:
            assert expected == checker.check_kiriban(
                session=session,
                user_id=data.user_id,
                target_date=data.jst_datetime,
            )


@mock.patch("hikarie_bot.curd.BADGE_TYPES_TO_CHECK", [7])
def test_badge_checker_id7_long_time_no_see(temp_db: sessionmaker) -> None:
    """Test the badge checker."""
    with temp_db() as session:
        initially_insert_badge_data(session)
        # > # BadgeTypeData id=7, name="long_time_no_see",
        # > #           description="長期間出社登録がない状態で復帰した"
        # > BadgeData(
        # >     id=13,
        # >     message="2週間ぶりですね、元気にしていましたか？",  # noqa: RUF003
        # >     condition="14日以上出社登録がなかったが復帰した",
        # >     level=1,
        # >     score=1,
        # >     badge_type_id=7,
        # > ),
        # > BadgeData(
        # >     id=14,
        # >     message="1か月ぶりですね、おかえりなさい。",
        # >     condition="30日以上出社登録がなかったが復帰した",
        # >     level=2,
        # >     score=1,
        # >     badge_type_id=7,
        # > ),
        # > BadgeData(
        # >     id=15,
        # >     message="2か月ぶりですね、顔を忘れるところでした。",
        # >     condition="2か月以上出社登録がなかったが復帰した",
        # >     level=3,
        # >     score=1,
        # >     badge_type_id=7,
        # > ),
        # > BadgeData(
        # >     id=16,
        # >     message="半年ぶりですね、むしろ初めまして。",
        # >     condition="半年以上出社登録がなかったが復帰した",
        # >     level=4,
        # >     score=1,
        # >     badge_type_id=7,
        # > ),

        badge_lv1 = BadgeChecker.get_badge(session=session, badge_id=701)
        badge_lv2 = BadgeChecker.get_badge(session=session, badge_id=702)
        badge_lv3 = BadgeChecker.get_badge(session=session, badge_id=703)
        badge_lv4 = BadgeChecker.get_badge(session=session, badge_id=704)

        checker = BadgeChecker([7])

        # test scenario: all users arriveld at 2024-01-01 07:00:00 initially
        # 1. 2 weeks no see (+15 days)
        # 2. 1 month no see
        # 3. 2 months no see
        # 4. 6 months no see
        # 5. 14 days no see (+14 days: fail)

        test_data = (
            UserData(jst_datetime="2024-01-01 07:00:01", user_id="user_1"),
            UserData(jst_datetime="2024-01-01 07:00:02", user_id="user_2"),
            UserData(jst_datetime="2024-01-01 07:00:03", user_id="user_3"),
            UserData(jst_datetime="2024-01-01 07:00:04", user_id="user_4"),
            UserData(jst_datetime="2024-01-01 07:00:05", user_id="user_5"),
            UserData(jst_datetime="2024-01-16 06:00:01", user_id="user_1"),
            UserData(jst_datetime="2024-02-02 06:00:02", user_id="user_2"),
            UserData(jst_datetime="2024-03-02 06:00:03", user_id="user_3"),
            UserData(jst_datetime="2024-07-02 06:00:04", user_id="user_4"),
            UserData(jst_datetime="2024-01-15 06:00:05", user_id="user_5"),
        )

        check_data = (
            ([badge_lv1], UserData(jst_datetime="2024-01-16", user_id="user_1")),
            ([badge_lv2], UserData(jst_datetime="2024-02-02", user_id="user_2")),
            ([badge_lv3], UserData(jst_datetime="2024-03-02", user_id="user_3")),
            ([badge_lv4], UserData(jst_datetime="2024-07-02", user_id="user_4")),
            ([], UserData(jst_datetime="2024-01-15", user_id="user_5")),
        )

        for data in test_data:
            insert_arrival_action(
                session=session,
                jst_datetime=data.jst_datetime,
                user_id=data.user_id,
            )

        for expected, data in check_data:
            logger.info(f"expected: {expected}, data: {data}")
            assert expected == checker.check_long_time_no_see(
                session=session,
                user_id=data.user_id,
                target_date=data.jst_datetime,
            )


@mock.patch("hikarie_bot.curd.BADGE_TYPES_TO_CHECK", [8])
def test_badge_checker_id8_lucky_you_guys(temp_db: sessionmaker) -> None:
    """Test the badge checker."""
    with temp_db() as session:
        initially_insert_badge_data(session)
        badge_lv1 = BadgeChecker.get_badge(session=session, badge_id=801)
        badge_lv2 = BadgeChecker.get_badge(session=session, badge_id=802)
        badge_lv3 = BadgeChecker.get_badge(session=session, badge_id=803)
        checker = BadgeChecker([8])

        # > # BadgeTypeData id=8, name="lucky_you_guys", description="同じ時間に出社登録をした"
        # > BadgeData(
        # >     id=17,
        # >     message="幸運なふたり",
        # >     condition="分単位で同じ時間に出社登録をした",
        # >     level=1,
        # >     score=1,
        # >     badge_type_id=8,
        # > ),
        # > BadgeData(
        # >     id=18,
        # >     message="幸運なトリオ",
        # >     condition="分単位で同じ時間に出社登録をした",
        # >     level=2,
        # >     score=1,
        # >     badge_type_id=8,
        # > ),

        # test scenario
        # 1. 1st user arrived at 2024-01-01 07:00:00
        # 2. 2nd user arrived at 2024-01-01 07:00:00 (lv1)
        # 3. 3rd user arrived at 2024-01-01 07:00:00 (lv2)
        # 4. 4th user arrived at 2024-01-01 07:00:00 (lv2)
        # 5. 5th user arrived at 2024-01-01 07:01:00
        # 5. 6th user arrived at 2024-01-01 07:01:00 (lv1)

        test_data = (
            UserData(jst_datetime="2024-01-01 07:00:00", user_id="user_1"),
            UserData(jst_datetime="2024-01-01 07:00:00", user_id="user_2"),
            UserData(jst_datetime="2024-01-01 07:00:00", user_id="user_3"),
            UserData(jst_datetime="2024-01-01 07:00:00", user_id="user_4"),
            UserData(jst_datetime="2024-01-01 07:01:00", user_id="user_5"),
            UserData(jst_datetime="2024-01-01 07:01:00", user_id="user_6"),
        )

        check_data = (
            ([], UserData(jst_datetime="2024-01-01", user_id="user_1")),
            ([badge_lv1], UserData(jst_datetime="2024-01-01", user_id="user_2")),
            (
                [badge_lv2],
                UserData(jst_datetime="2024-01-01", user_id="user_3"),
            ),
            (
                [badge_lv3],
                UserData(jst_datetime="2024-01-01", user_id="user_4"),
            ),
            ([], UserData(jst_datetime="2024-01-01", user_id="user_5")),
            ([badge_lv1], UserData(jst_datetime="2024-01-01", user_id="user_6")),
        )

        for data in test_data:
            insert_arrival_action(
                session=session,
                jst_datetime=data.jst_datetime,
                user_id=data.user_id,
            )

        for expected, data in check_data:
            logger.info(f"expected: {expected}, data: {data}")
            assert expected == checker.check_lucky_you_guys(
                session=session,
                user_id=data.user_id,
                target_date=data.jst_datetime,
            )


@mock.patch("hikarie_bot.curd.BADGE_TYPES_TO_CHECK", [1, 2, 3])
def test_badge_checker_complex_id1_id2(temp_db: sessionmaker) -> None:
    """Test the badge checker with complex condition."""
    with temp_db() as session:
        initially_insert_badge_data(session)
        badge_id1 = BadgeChecker.get_badge(session=session, badge_id=101)
        badge_id2 = BadgeChecker.get_badge(session=session, badge_id=201)
        badge_id3 = BadgeChecker.get_badge(session=session, badge_id=301)
        checker = BadgeChecker(badge_type_to_check=[1, 2, 3])

        # test scenario
        # A: always comes fastest, arrive from 1/1,
        #    get arrival count lv1(5times) badge at 2024-01-05
        # B: start to come at 1/4, get the fastest at 1/6

        test_data = (
            # A
            UserData(jst_datetime="2024-01-01 06:00:00", user_id="user_A"),
            UserData(jst_datetime="2024-01-02 06:00:00", user_id="user_A"),
            UserData(jst_datetime="2024-01-03 06:00:00", user_id="user_A"),
            UserData(jst_datetime="2024-01-04 06:00:00", user_id="user_A"),
            UserData(jst_datetime="2024-01-05 06:00:00", user_id="user_A"),
            UserData(jst_datetime="2024-01-06 07:00:00", user_id="user_A"),
            # B
            UserData(jst_datetime="2024-01-04 07:00:00", user_id="user_B"),
            UserData(jst_datetime="2024-01-05 07:00:00", user_id="user_B"),
            UserData(jst_datetime="2024-01-06 06:00:00", user_id="user_B"),
        )

        check_data = (
            # A
            (
                [badge_id1, badge_id2],
                UserData(jst_datetime="2024-01-01", user_id="user_A"),
            ),
            (
                [badge_id2, badge_id3],
                UserData(jst_datetime="2024-01-05", user_id="user_A"),
            ),
            ([], UserData(jst_datetime="2024-01-06", user_id="user_A")),
            # B
            ([badge_id1], UserData(jst_datetime="2024-01-04", user_id="user_B")),
            ([badge_id2], UserData(jst_datetime="2024-01-06", user_id="user_B")),
        )

        for data in test_data:
            insert_arrival_action(
                session=session,
                jst_datetime=data.jst_datetime,
                user_id=data.user_id,
            )

        for expected, data in check_data:
            assert expected == checker.check(
                session=session,
                user_id=data.user_id,
                target_date=data.jst_datetime,
            )


@mock.patch("hikarie_bot.curd.BADGE_TYPES_TO_CHECK", [15])
def test_badge_checker_id15_start_dash(temp_db: sessionmaker) -> None:
    """Test the start dash badge."""
    with temp_db() as session:
        initially_insert_badge_data(session)
        badge_lv1 = BadgeChecker.get_badge(session=session, badge_id=1501)
        checker = BadgeChecker([15])

        # > # BadgeTypeData id=15, name="start_dash", description="初回利用から2週間以内に出社登録した"
        # > BadgeData(
        # >     id=1501,
        # >     message="スタートダッシュ",
        # >     condition="初回利用から2週間以内に出社登録した",
        # >     level=1,
        # >     score=2,
        # >     badge_type_id=15,
        # > ),

        # test scenario
        # not applied before 2024-11-25
        # case 1. user initially arrived at 2024-11-25
        #     1. arrives at 2024-11-25 (applied, starts here)
        #     2. arrives at 2024-12-09 (applied)
        #     3. arrives at 2024-12-10 (not applied)
        # case 2. user initially arrived at 2024-11-24 (before 11-25)
        #     0. arrives at 2024-11-24 (not applied)
        #     1. arrives at 2024-11-26 (applied, starts here)
        #     2. arrives at 2024-12-10 (applied)
        #     3. arrives at 2024-12-11 (not applied)

        test_data = (
            # case 1
            UserData(jst_datetime="2024-12-09 07:00:00", user_id="user_1"),
            UserData(jst_datetime="2024-12-23 07:00:00", user_id="user_1"),
            UserData(jst_datetime="2024-12-24 07:00:00", user_id="user_1"),
            # case 2
            UserData(jst_datetime="2024-12-08 07:00:00", user_id="user_2"),
            UserData(jst_datetime="2024-12-10 07:00:00", user_id="user_2"),
            UserData(jst_datetime="2024-12-24 07:00:00", user_id="user_2"),
            UserData(jst_datetime="2024-12-25 07:00:00", user_id="user_2"),
        )

        check_data = (
            ([badge_lv1], UserData(jst_datetime="2024-12-09", user_id="user_1")),
            ([badge_lv1], UserData(jst_datetime="2024-12-23", user_id="user_1")),
            ([], UserData(jst_datetime="2024-12-24", user_id="user_1")),
            ([], UserData(jst_datetime="2024-12-08", user_id="user_2")),
            ([badge_lv1], UserData(jst_datetime="2024-12-10", user_id="user_2")),
            ([badge_lv1], UserData(jst_datetime="2024-12-24", user_id="user_2")),
            ([], UserData(jst_datetime="2024-12-25", user_id="user_2")),
        )

        for data in test_data:
            insert_arrival_action(
                session=session,
                jst_datetime=data.jst_datetime,
                user_id=data.user_id,
            )

        for expected, data in check_data:
            logger.info(f"expected: {expected}, data: {data}")
            assert expected == checker.check_start_dash(
                session=session,
                user_id=data.user_id,
                target_date=data.jst_datetime,
            )


@mock.patch("hikarie_bot.curd.BADGE_TYPES_TO_CHECK", [16])
def test_badge_checker_id16_specific_day(temp_db: sessionmaker) -> None:
    """Test the specific day badge."""
    with temp_db() as session:
        initially_insert_badge_data(session)

        # > # BadgeTypeData id=16, name="specific_day", description="特定の年月日に出社した"
        # > BadgeData(
        # >     id=1601,
        # >     message="2024年お疲れ様です",
        # >     condition="2024年12月27日に出社した",
        # >     level=1,
        # >     score=2,
        # >     badge_type_id=16,
        # > ),
        # > BadgeData(
        # >     id=1602,
        # >     message="2025年明けましておめでとうございます",
        # >     condition="2025年1月6日に出社した",
        # >     level=1,
        # >     score=2,
        # >     badge_type_id=16,
        # > ),

        badge_2024_end = BadgeChecker.get_badge(session=session, badge_id=1601)
        badge_2025_start = BadgeChecker.get_badge(session=session, badge_id=1602)
        checker = BadgeChecker([16])

        # test scenario
        # 1. 2024-12-27
        # 2. 2025-01-06
        # 3. 2024-12-26
        # 4. 2025-01-05

        test_data = (
            UserData(jst_datetime="2024-12-27 07:00:00", user_id="user_1"),
            UserData(jst_datetime="2025-01-06 07:00:00", user_id="user_2"),
            UserData(jst_datetime="2024-12-26 07:00:00", user_id="user_3"),
            UserData(jst_datetime="2025-01-05 07:00:00", user_id="user_4"),
        )

        check_data = (
            ([badge_2024_end], UserData(jst_datetime="2024-12-27", user_id="user_1")),
            ([badge_2025_start], UserData(jst_datetime="2025-01-06", user_id="user_2")),
            ([], UserData(jst_datetime="2024-12-26", user_id="user_3")),
            ([], UserData(jst_datetime="2025-01-05", user_id="user_4")),
        )

        for data in test_data:
            insert_arrival_action(
                session=session,
                jst_datetime=data.jst_datetime,
                user_id=data.user_id,
            )

        for expected, data in check_data:
            logger.info(f"expected: {expected}, data: {data}")
            assert expected == checker.check_specific_day(
                session=session,
                user_id=data.user_id,
                target_date=data.jst_datetime,
            )


@mock.patch("hikarie_bot.curd.BADGE_TYPES_TO_CHECK", [17])
def test_badge_checker_id17_yearly_specific_day(temp_db: sessionmaker) -> None:
    """Test the yearly specific day badge."""
    with temp_db() as session:
        initially_insert_badge_data(session)

        # > # BadgeTypeData id=17, name="yearly_specific_day", description="毎年特定の日に出社した"
        # > BadgeData(
        # >     id=1701,
        # >     message="クリスマス出社",
        # >     condition="12月25日に出社した",
        # >     level=1,
        # >     score=2,
        # >     badge_type_id=17,
        # > ),
        # > BadgeData(
        # >     id=1702,
        # >     message="昨年度はお世話になりました",
        # >     condition="年度末に出社した",
        # >     level=1,
        # >     score=2,
        # >     badge_type_id=17,
        # > ),
        # > BadgeData(
        # >     id=1703,
        # >     message="今年度もよろしくお願いします",
        # >     condition="年度初めに出社した",
        # >     level=1,
        # >     score=2,
        # >     badge_type_id=17,
        # > ),

        badge_christmas = BadgeChecker.get_badge(session=session, badge_id=1701)
        badge_workyear_end = BadgeChecker.get_badge(session=session, badge_id=1702)
        badge_workyear_start = BadgeChecker.get_badge(session=session, badge_id=1703)
        checker = BadgeChecker([17])

        # test scenario
        # クリスマス出社は12/25に出社した場合のみもらえる
        # 年度末出社は3/25-3/31の間に出社した場合に同じ年は1度のみもらえる
        # 年度初め出社は4/1-4/7の間に出社した場合に同じ年は1度のみもらえる

        # 下記にテスト観点を列挙する
        # クリスマス出社は当日のみもらえていること、前日や翌日はもらえないこと、次の歳になったらもらえていること
        # 年度末出社は期間中1度のみもらえること、期間外はもらえないこと、次の年度になったらもらえていること
        # 年度初め出社は期間中1度のみもらえること、期間外はもらえないこと、次の年度になったらもらえていること

        # テストシナリオ
        # ユーザー1: 正常系: クリスマス出社、年度末出社、年度初め出社
        #   -  2024-12-25: クリスマス出社 ok
        #   -  2024-03-25: 年度末出社 ok
        #   -  2024-03-31: 年度末出社 ng (年度末出社は1度のみ)
        #   -  2024-04-01: 年度初め出社 ok
        #   -  2024-04-08: 年度初め出社 ng (年度初め出社は1度のみ)
        #   -  2025-12-25: クリスマス出社 ok
        #   -  2025-03-24: 年度末出社 ok
        #   -  2025-04-01: 年度初め出社 ok
        # ユーザー2: 異常系: クリスマス出社、年度末出社、年度初め出社
        #   -  2024-12-24: クリスマス出社 ng
        #   -  2024-12-26: クリスマス出社 ng
        #   -  2024-03-23: 年度末出社 ng
        #   -  2024-03-31: 年度末出社 ok, 年度初め出社 ng
        #   -  2024-04-08: 年度初め出社 ng

        test_data = (
            # ユーザー1
            UserData(jst_datetime="2024-12-25 07:00:00", user_id="user_1"),
            UserData(jst_datetime="2025-03-25 07:00:00", user_id="user_1"),
            UserData(jst_datetime="2025-03-31 07:00:00", user_id="user_1"),
            UserData(jst_datetime="2025-04-01 07:00:00", user_id="user_1"),
            UserData(jst_datetime="2025-04-08 07:00:00", user_id="user_1"),
            UserData(jst_datetime="2026-12-25 07:00:00", user_id="user_1"),
            UserData(jst_datetime="2026-03-25 07:00:00", user_id="user_1"),
            UserData(jst_datetime="2026-04-01 07:00:00", user_id="user_1"),
            # ユーザー2
            UserData(jst_datetime="2025-12-24 07:00:00", user_id="user_2"),
            UserData(jst_datetime="2025-12-26 07:00:00", user_id="user_2"),
            UserData(jst_datetime="2025-03-24 07:00:00", user_id="user_2"),
            UserData(jst_datetime="2025-03-31 07:00:00", user_id="user_2"),
            UserData(jst_datetime="2025-04-08 07:00:00", user_id="user_2"),
        )

        check_data = (
            ([badge_christmas], UserData(jst_datetime="2024-12-25", user_id="user_1")),
            (
                [badge_workyear_end],
                UserData(jst_datetime="2025-03-25", user_id="user_1"),
            ),
            ([], UserData(jst_datetime="2025-03-31", user_id="user_1")),
            (
                [badge_workyear_start],
                UserData(jst_datetime="2025-04-01", user_id="user_1"),
            ),
            ([], UserData(jst_datetime="2025-04-08", user_id="user_1")),
            ([badge_christmas], UserData(jst_datetime="2026-12-25", user_id="user_1")),
            (
                [badge_workyear_end],
                UserData(jst_datetime="2026-03-25", user_id="user_1"),
            ),
            (
                [badge_workyear_start],
                UserData(jst_datetime="2026-04-01", user_id="user_1"),
            ),
            ([], UserData(jst_datetime="2025-12-24", user_id="user_2")),
            ([], UserData(jst_datetime="2025-12-26", user_id="user_2")),
            ([], UserData(jst_datetime="2025-03-24", user_id="user_2")),
            (
                [badge_workyear_end],
                UserData(jst_datetime="2025-03-31", user_id="user_2"),
            ),
            ([], UserData(jst_datetime="2025-04-08", user_id="user_2")),
        )

        for data in test_data:
            insert_arrival_action(
                session=session,
                jst_datetime=data.jst_datetime,
                user_id=data.user_id,
            )

        for expected, data in check_data:
            logger.info(f"expected: {expected}, data: {data}")
            actual = checker.check_yearly_specific_day(
                session=session,
                user_id=data.user_id,
                target_date=data.jst_datetime,
            )
            logger.info(f"actual: {actual}")
            assert expected == checker.check_yearly_specific_day(
                session=session,
                user_id=data.user_id,
                target_date=data.jst_datetime,
            )


def test_badge_checker_id18_specific_time(temp_db: sessionmaker) -> None:
    """Test the specific time badge."""
    with temp_db() as session:
        initially_insert_badge_data(session)

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

        badge_adjacent = BadgeChecker.get_badge(session=session, badge_id=1801)
        badge_repeater = BadgeChecker.get_badge(session=session, badge_id=1802)
        badge_stairs = BadgeChecker.get_badge(session=session, badge_id=1803)
        badge_pocky = BadgeChecker.get_badge(session=session, badge_id=1804)

        checker = BadgeChecker([18])

        # test scenario
        # 1. 2025-12-27 07:08:00 -> adjacent
        # 2. 2025-12-27 07:07:00 -> repeater
        # 3. 2025-12-27 07:06:00 -> adjacent
        # 4. 2025-12-27 12:33:00 -> x
        # 5. 2025-12-27 12:34:00 -> stairs
        # 6. 2025-12-27 11:11:00 -> pocky
        # 7. 2025-12-27 11:12:00 -> adjacent
        # 8. 2025-12-27 11:10:00 -> adjacent

        test_data = (
            UserData(jst_datetime="2025-12-27 07:08:00", user_id="user_1"),
            UserData(jst_datetime="2025-12-27 07:07:00", user_id="user_2"),
            UserData(jst_datetime="2025-12-27 07:06:00", user_id="user_3"),
            UserData(jst_datetime="2025-12-27 12:33:00", user_id="user_4"),
            UserData(jst_datetime="2025-12-27 12:34:00", user_id="user_5"),
            UserData(jst_datetime="2025-12-27 11:11:00", user_id="user_6"),
            UserData(jst_datetime="2025-12-27 11:12:00", user_id="user_7"),
            UserData(jst_datetime="2025-12-27 11:10:00", user_id="user_8"),
        )

        check_data = (
            ([badge_adjacent], UserData(jst_datetime="2025-12-27", user_id="user_1")),
            ([badge_repeater], UserData(jst_datetime="2025-12-27", user_id="user_2")),
            ([badge_adjacent], UserData(jst_datetime="2025-12-27", user_id="user_3")),
            ([], UserData(jst_datetime="2025-12-27", user_id="user_4")),
            ([badge_stairs], UserData(jst_datetime="2025-12-27", user_id="user_5")),
            ([badge_pocky], UserData(jst_datetime="2025-12-27", user_id="user_6")),
            ([badge_adjacent], UserData(jst_datetime="2025-12-27", user_id="user_7")),
            ([badge_adjacent], UserData(jst_datetime="2025-12-27", user_id="user_8")),
        )

        for data in test_data:
            insert_arrival_action(
                session=session,
                jst_datetime=data.jst_datetime,
                user_id=data.user_id,
            )

        for expected, data in check_data:
            actual = checker.check_specific_time(
                session=session,
                user_id=data.user_id,
                target_date=data.jst_datetime,
            )
            logger.info(f"expected: {expected}, data: {data}, actual: {actual}")

            assert expected == actual
