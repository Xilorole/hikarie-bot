from dataclasses import dataclass
from datetime import datetime, timedelta

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


def test_badge_checker_id3_arrival_count(temp_db: sessionmaker) -> None:
    """Test the badge checker."""
    with temp_db() as session:
        initially_insert_badge_data(session)
        badge_5 = BadgeChecker.get_badge(session=session, badge_id=301)
        badge_20 = BadgeChecker.get_badge(session=session, badge_id=302)
        badge_100 = BadgeChecker.get_badge(session=session, badge_id=303)
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
        # 2. user arrived 20 times
        # 3. user arrived 100 times
        # 4. user arrived 4 times

        test_data = (
            *[
                UserData(
                    jst_datetime=datetime.fromisoformat("20200101 06:00:00")
                    + timedelta(days=i),
                    user_id="user",
                )
                for i in range(100)
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
            # scenario 2
            ([], UserData(jst_datetime="2020-01-19", user_id="user")),
            ([badge_20], UserData(jst_datetime="2020-01-20", user_id="user")),
            ([], UserData(jst_datetime="2020-01-21", user_id="user")),
            # scenario 3
            ([], UserData(jst_datetime="2020-04-08", user_id="user")),
            ([badge_100], UserData(jst_datetime="2020-04-09", user_id="user")),
            ([], UserData(jst_datetime="2020-04-10", user_id="user")),
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


def test_badge_checker_id5_time_window(temp_db: sessionmaker) -> None:
    """Test the badge checker."""
    with temp_db() as session:
        initially_insert_badge_data(session)
        badge_lv1 = BadgeChecker.get_badge(session=session, badge_id=503)
        badge_lv2 = BadgeChecker.get_badge(session=session, badge_id=502)
        badge_lv3 = BadgeChecker.get_badge(session=session, badge_id=501)
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
        )
        check_data = (
            ([badge_lv3], UserData(jst_datetime="2024-04-22", user_id="user_1")),
            ([badge_lv2], UserData(jst_datetime="2024-04-22", user_id="user_2")),
            ([badge_lv1], UserData(jst_datetime="2024-04-22", user_id="user_3")),
            ([], UserData(jst_datetime="2024-04-22", user_id="user_4")),
            ([], UserData(jst_datetime="2024-04-22", user_id="user_5")),
        )

        for data in test_data:
            insert_arrival_action(
                session=session,
                jst_datetime=data.jst_datetime,
                user_id=data.user_id,
            )

        for expected, data in check_data:
            assert expected == checker.check_time_window(
                session=session,
                user_id=data.user_id,
                target_date=data.jst_datetime,
            )


def test_badge_checker_id6_kiriban(temp_db: sessionmaker) -> None:
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
                for i in range(99)
            ],
            UserData(
                jst_datetime=datetime.fromisoformat("20200102 06:00:00"),
                user_id="user_kiriban_100",
            ),
        )
        check_data = (
            ([], UserData(jst_datetime="2020-01-01", user_id="user_0")),
            (
                [badge_n100],
                UserData(jst_datetime="2020-01-02", user_id="user_kiriban_100"),
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


def test_badge_checker_id8_lucky_you_guys(temp_db: sessionmaker) -> None:
    """Test the badge checker."""
    with temp_db() as session:
        initially_insert_badge_data(session)
        badge_lv1 = BadgeChecker.get_badge(session=session, badge_id=801)
        badge_lv2 = BadgeChecker.get_badge(session=session, badge_id=802)
        badge_lv3 = BadgeChecker.get_badge(session=session, badge_id=803)
        checker = BadgeChecker([8])

        # > # BadgeTypeData id=8, name="lucky_you_guys", description="同じ時間に出社登録をした"  # noqa: E501
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


def test_badge_checker_id15_start_dash(temp_db: sessionmaker) -> None:
    """Test the start dash badge."""
    with temp_db() as session:
        initially_insert_badge_data(session)
        badge_lv1 = BadgeChecker.get_badge(session=session, badge_id=1501)
        checker = BadgeChecker([15])

        # > # BadgeTypeData id=15, name="start_dash", description="初回利用から2週間以内に出社登録した"  # noqa: E501
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
            UserData(jst_datetime="2024-11-25 07:00:00", user_id="user_1"),
            UserData(jst_datetime="2024-12-09 07:00:00", user_id="user_1"),
            UserData(jst_datetime="2024-12-10 07:00:00", user_id="user_1"),
            # case 2
            UserData(jst_datetime="2024-11-24 07:00:00", user_id="user_2"),
            UserData(jst_datetime="2024-11-26 07:00:00", user_id="user_2"),
            UserData(jst_datetime="2024-12-10 07:00:00", user_id="user_2"),
            UserData(jst_datetime="2024-12-11 07:00:00", user_id="user_2"),
        )

        check_data = (
            ([badge_lv1], UserData(jst_datetime="2024-11-25", user_id="user_1")),
            ([badge_lv1], UserData(jst_datetime="2024-12-09", user_id="user_1")),
            ([], UserData(jst_datetime="2024-12-10", user_id="user_1")),
            ([], UserData(jst_datetime="2024-11-24", user_id="user_2")),
            ([badge_lv1], UserData(jst_datetime="2024-11-26", user_id="user_2")),
            ([badge_lv1], UserData(jst_datetime="2024-12-10", user_id="user_2")),
            ([], UserData(jst_datetime="2024-12-11", user_id="user_2")),
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
