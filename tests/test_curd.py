from unittest.mock import patch

from sqlalchemy.orm import Session, sessionmaker

from hikarie_bot.curd import initially_insert_badge_data
from hikarie_bot.models import Badge, BadgeType, GuestArrivalInfo, GuestArrivalRaw, User
from tests.helpers import arrive


# 最速出社と時間帯出社の部分をmockする
@patch("hikarie_bot.curd.BADGE_TYPES_TO_CHECK", [2, 5])
def test_temp_db(session: Session) -> None:
    """Test temporary database."""
    arrive(session, "2024-01-01 06:00:00", "test_user")

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
    arrive(session, "2024-01-01 07:00:00", "test_user")
    assert (
        session.query(GuestArrivalInfo)
        .filter(GuestArrivalInfo.user_id == "test_user")
        .count()
        == 1
    )

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


# 最速出社と時間帯出社の部分をmockする
@patch("hikarie_bot.curd.BADGE_TYPES_TO_CHECK", [2, 5])
def test_level_up(session: Session) -> None:
    """Test level up."""
    for i in range(4):
        arrive(session, f"2024-02-{i + 1:02d} 06:00:00", "test_user")

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
def test_second_arrived_user_has_lower_point(session: Session) -> None:
    """Test the second arrived user has lower point."""
    arrive(session, "2024-01-01 06:00:00", "test_user_1st")
    arrive(session, "2024-01-01 07:00:00", "test_user_2nd")

    user_1st_info = session.query(User).filter(User.id == "test_user_1st").one()
    user_2nd_info = session.query(User).filter(User.id == "test_user_2nd").one()

    assert user_1st_info.current_score == 5
    assert user_1st_info.previous_score == 0

    assert user_2nd_info.current_score == 3
    assert user_2nd_info.previous_score == 0


def test_insert_badge_data(temp_db: sessionmaker[Session]) -> None:
    """Test badge data."""
    session = temp_db()

    initially_insert_badge_data(session=session)

    assert session.query(Badge).count() != 0
    assert session.query(BadgeType).count() == 14

    assert (
        session.query(Badge)
        .filter(Badge.badge_type_id == 1, Badge.level == 1)
        .one()
        .message
        == "はじめての出社登録"
    )

    assert session.query(BadgeType).filter(BadgeType.id == 1).one().name == "welcome"
