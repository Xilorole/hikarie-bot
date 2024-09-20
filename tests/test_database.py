import zoneinfo
from datetime import datetime

from hikarie_bot.__main__ import get_db
from hikarie_bot.curd import insert_arrival_action
from hikarie_bot.models import GuestArrivalInfo, GuestArrivalRaw, User


# @temp_db
def test_temp_db() -> None:
    """Test temporary database."""
    session = get_db().__next__()
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

    assert (
        session.query(GuestArrivalRaw)
        .filter(GuestArrivalRaw.user_id == "test_user")
        .count()
        == 2
    )
