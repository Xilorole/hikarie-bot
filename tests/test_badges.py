import zoneinfo
from datetime import datetime

from sqlalchemy.orm import sessionmaker

from hikarie_bot.curd import insert_arrival_action
from hikarie_bot.db_data.badges import BadgeChecker


def test_badge_checker(temp_db: sessionmaker) -> None:
    """Test the badge checker."""
    session = temp_db()
    checker = BadgeChecker()

    # test scenario
    # 1. test_user:
    #   2024-01-01 06:00:00 (o:fastest, o:initial)<- [check]
    # 2. test_user_already_arrived:
    #   2024-01-02 06:00:00
    #   2024-01-03 06:00:00 (o:fastest, x:initial) <- [check]
    # 3. test_user_not_fastest:
    #   2024-01-03 07:00:00 (x:fastest, o:initial) <- [check]

    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 1, 1, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user",
    )

    assert checker.check_welcome(
        session=session,
        user_id="test_user",
        target_date=datetime(2024, 1, 1, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
    )

    assert checker.check_fastest_arrival(
        session=session,
        user_id="test_user",
        target_date=datetime(2024, 1, 1, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
    )

    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 1, 2, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user_already_arrived",
    )
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 1, 3, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user_already_arrived",
    )

    assert not checker.check_welcome(
        session=session,
        user_id="test_user_already_arrived",
        target_date=datetime(2024, 1, 3, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
    )

    assert checker.check_fastest_arrival(
        session=session,
        user_id="test_user_already_arrived",
        target_date=datetime(2024, 1, 3, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
    )

    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 1, 3, 7, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user_not_fastest",
    )

    assert checker.check_welcome(
        session=session,
        user_id="test_user_not_fastest",
        target_date=datetime(2024, 1, 3, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
    )

    assert not checker.check_fastest_arrival(
        session=session,
        user_id="test_user_not_fastest",
        target_date=datetime(2024, 1, 3, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
    )
