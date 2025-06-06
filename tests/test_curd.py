import zoneinfo
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session, sessionmaker

from hikarie_bot.curd import (
    _update_achievements,
    initially_insert_badge_data,
    insert_arrival_action,
)
from hikarie_bot.exceptions import (
    AchievementAlreadyRegisteredError,
    UserArrivalNotFoundError,
)
from hikarie_bot.models import (
    Achievement,
    Badge,
    BadgeType,
    GuestArrivalInfo,
    GuestArrivalRaw,
    User,
)


def test_update_achievements(temp_db: sessionmaker[Session]) -> None:
    """Test the _update_achievements function."""
    session = temp_db()
    initially_insert_badge_data(session=session)

    # Create a user and arrival info
    user_id = "test_user"
    arrival_id = 1
    jst_datetime = datetime(2024, 1, 1, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo"))

    guest_arrival_info = GuestArrivalInfo(
        user_id=user_id,
        arrival_time=jst_datetime,
        arrival_rank=1,
        acquired_score_sum=0,
    )
    session.add(guest_arrival_info)
    session.commit()
    arrival_id = guest_arrival_info.id

    # assert that the user has no achievements
    assert session.query(Achievement).filter(Achievement.arrival_id == arrival_id).count() == 0

    # Test normal case
    _update_achievements(session, arrival_id)

    assert session.query(Achievement).filter(Achievement.arrival_id == arrival_id).count() > 0

    # Test already registered achievement
    with pytest.raises(AchievementAlreadyRegisteredError):
        _update_achievements(session, arrival_id)

    # Test non-existent arrival_id
    with pytest.raises(UserArrivalNotFoundError):
        _update_achievements(session, 9999)


# 最速出社と時間帯出社の部分をmockする
@patch("hikarie_bot.curd.BADGE_TYPES_TO_CHECK", [2, 5])
def test_temp_db(temp_db: sessionmaker[Session]) -> None:
    """Test temporary database."""
    session: Session = temp_db()
    initially_insert_badge_data(session=session)
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(2024, 1, 1, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
        user_id="test_user",
    )

    assert session.query(GuestArrivalInfo).all() is not None
    assert session.query(GuestArrivalInfo).filter(GuestArrivalInfo.user_id == "test_user").count() == 1
    assert session.query(GuestArrivalInfo).filter(GuestArrivalInfo.user_id == "invalid_user_name").count() == 0
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(2024, 1, 1, 7, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
        user_id="test_user",
    )
    assert session.query(GuestArrivalInfo).filter(GuestArrivalInfo.user_id == "test_user").count() == 1

    user_info = session.query(User).filter(User.id == "test_user").one()

    assert user_info.current_score == 7
    assert user_info.previous_score == 0
    assert user_info.level == 1
    assert user_info.level_name == "かけだしのかいしゃいん"
    assert not user_info.level_uped
    assert user_info.point_to_next_level == 13
    assert user_info.point_range_to_next_level == 20
    assert user_info.current_level_point == 7

    assert session.query(GuestArrivalRaw).filter(GuestArrivalRaw.user_id == "test_user").count() == 2


def test_insert_arrival_action(temp_db: sessionmaker[Session]) -> None:
    """Test insert arrival action."""
    session = temp_db()
    initially_insert_badge_data(session=session)
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(2024, 1, 1, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
        user_id="1st_arrived_user",
    )
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(2024, 1, 1, 6, 1, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
        user_id="2nd_arrived_user",
    )

    # add data for tommorow and yesterday to check the rank is properly calculated

    insert_arrival_action(
        session=session,
        jst_datetime=datetime(2024, 1, 1, 5, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
        user_id="1st_arrived_user",
    )

    insert_arrival_action(
        session=session,
        jst_datetime=datetime(2024, 1, 1, 7, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
        user_id="1st_arrived_user",
    )

    user_1st_info = (
        session.query(GuestArrivalInfo)
        .filter(
            GuestArrivalInfo.user_id == "1st_arrived_user",
            GuestArrivalInfo.arrival_time >= datetime(2024, 1, 1, 0, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
            GuestArrivalInfo.arrival_time < datetime(2024, 1, 2, 0, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
        )
        .one()
    )
    user_2nd_info = session.query(GuestArrivalInfo).filter(GuestArrivalInfo.user_id == "2nd_arrived_user").one()

    assert user_1st_info.arrival_rank == 1
    assert user_2nd_info.arrival_rank == 2

    assert user_1st_info.acquired_score_sum != -1
    assert user_2nd_info.acquired_score_sum != -1


# 最速出社と時間帯出社の部分をmockする
@patch("hikarie_bot.curd.BADGE_TYPES_TO_CHECK", [2, 5])
def test_level_up(temp_db: sessionmaker[Session]) -> None:
    """Test level up."""
    session = temp_db()
    initially_insert_badge_data(session=session)
    for i in range(4):
        insert_arrival_action(
            session=session,
            jst_datetime=datetime(2024, 2, i + 1, 7, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
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


# 最速出社と時間帯出社の部分をmockする
@patch("hikarie_bot.curd.BADGE_TYPES_TO_CHECK", [2, 5])
def test_second_arrived_user_has_lower_point(temp_db: sessionmaker[Session]) -> None:
    """Test the second arrived user has lower point."""
    session = temp_db()

    initially_insert_badge_data(session=session)
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(2024, 1, 1, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
        user_id="test_user_1st",
    )
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(2024, 1, 1, 7, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
        user_id="test_user_2nd",
    )

    user_1st_info = session.query(User).filter(User.id == "test_user_1st").one()
    user_2nd_info = session.query(User).filter(User.id == "test_user_2nd").one()

    assert user_1st_info.current_score == 7
    assert user_1st_info.previous_score == 0

    assert user_2nd_info.current_score == 3
    assert user_2nd_info.previous_score == 0


def test_insert_badge_data(temp_db: sessionmaker[Session]) -> None:
    """Test badge data."""
    session = temp_db()

    initially_insert_badge_data(session=session)

    assert session.query(Badge).count() != 0
    assert session.query(BadgeType).count() == 18

    assert session.query(Badge).filter(Badge.badge_type_id == 1, Badge.level == 1).one().message == "はじめての出社登録"

    assert session.query(BadgeType).filter(BadgeType.id == 1).one().name == "welcome"
