import zoneinfo
from datetime import datetime

from sqlalchemy.orm import sessionmaker

from hikarie_bot.curd import _check_straight_flash, insert_arrival_action
from hikarie_bot.models import GuestArrivalInfo, GuestArrivalRaw, User


# @temp_db
def test_temp_db(temp_db: sessionmaker) -> None:
    """Test temporary database."""
    session = temp_db()
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 1, 1, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user",
    )

    assert session.query(GuestArrivalInfo).all() is not None
    assert (
        session.query(GuestArrivalInfo)
        .filter(GuestArrivalInfo.user_id == "test_user")
        .count()
        == 1
    )
    assert (
        session.query(GuestArrivalInfo)
        .filter(GuestArrivalInfo.user_id == "invalid_user_name")
        .count()
        == 0
    )
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 1, 1, 7, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user",
    )
    assert (
        session.query(GuestArrivalInfo)
        .filter(GuestArrivalInfo.user_id == "test_user")
        .count()
        == 1
    )
    arrival_info = (
        session.query(GuestArrivalInfo)
        .filter(GuestArrivalInfo.user_id == "test_user")
        .one()
    )

    assert arrival_info.acquired_time_score == 3
    assert arrival_info.acquired_rank_score == 2

    user_info = session.query(User).filter(User.id == "test_user").one()

    assert user_info.current_score == 5
    assert user_info.previous_score == 0
    assert user_info.level == 1
    assert user_info.level_name == "かけだしのかいしゃいん"
    assert not user_info.level_uped
    assert user_info.point_to_next_level == 15
    assert user_info.point_range_to_next_level == 20
    assert user_info.current_level_point == 5

    assert (
        session.query(GuestArrivalRaw)
        .filter(GuestArrivalRaw.user_id == "test_user")
        .count()
        == 2
    )


def test_level_up(temp_db: sessionmaker) -> None:
    """Test level up."""
    session = temp_db()
    for i in range(4):
        insert_arrival_action(
            session=session,
            jst_datetime=datetime(
                2024, 2, i + 1, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
            ),
            user_id="test_user",
        )

    user_info = session.query(User).filter(User.id == "test_user").one()

    assert user_info.current_score == 20
    assert user_info.previous_score == 15
    assert user_info.level == 2
    assert user_info.level_name == "みならいのかいしゃいん"
    assert user_info.level_uped
    assert user_info.point_to_next_level == 22
    assert user_info.point_range_to_next_level == 22
    assert user_info.current_level_point == 0


def test_second_arrived_user_has_lower_point(temp_db: sessionmaker) -> None:
    """Test the second arrived user has lower point."""
    session = temp_db()
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 1, 1, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user_1st",
    )
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 1, 1, 7, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user_2nd",
    )

    user_1st_info = session.query(User).filter(User.id == "test_user_1st").one()
    user_2nd_info = session.query(User).filter(User.id == "test_user_2nd").one()

    assert user_1st_info.current_score == 5
    assert user_1st_info.previous_score == 0

    assert user_2nd_info.current_score == 3
    assert user_2nd_info.previous_score == 0


def test__check_straight_flash(temp_db: sessionmaker) -> None:
    """Test straight flash."""
    session = temp_db()

    # sample straight flash
    # 2024-04-22, 2024-04-23, 2024-04-24, 2024-04-25, 2024-04-26
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 4, 22, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user",
    )
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 4, 23, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user",
    )
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 4, 24, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user",
    )
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 4, 25, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user",
    )
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 4, 26, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user",
    )

    assert _check_straight_flash(
        session=session,
        user_id="test_user",
        last_date=datetime(
            2024, 4, 26, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
    )

    user_info = session.query(User).filter(User.id == "test_user").one()

    assert user_info.current_score == 28

    # longest straight flash
    # 2024-04-26, 2024-04-30, 2024-05-01, 2024-05-02, 2024-05-07
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 4, 26, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user_longest",
    )
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 4, 30, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user_longest",
    )
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 5, 1, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user_longest",
    )
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 5, 2, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user_longest",
    )
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 5, 7, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user_longest",
    )

    assert _check_straight_flash(
        session=session,
        user_id="test_user_longest",
        last_date=datetime(2024, 5, 7, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
    )

    # sample failing straight flash
    # 2024-04-22, 2024-04-23, 2024-04-24, 2024-04-25, 2024-04-30
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 4, 22, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user_fail",
    )
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 4, 23, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user_fail",
    )
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 4, 24, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user_fail",
    )
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 4, 25, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user_fail",
    )
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 4, 30, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user_fail",
    )
    assert not _check_straight_flash(
        session=session,
        user_id="test_user_fail",
        last_date=datetime(
            2024, 4, 30, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
    )
