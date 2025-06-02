import zoneinfo
from datetime import datetime, timedelta # Added timedelta
from textwrap import dedent
from unittest import mock

from sqlalchemy.orm import Session, sessionmaker

from hikarie_bot.curd import initially_insert_badge_data, insert_arrival_action
from hikarie_bot.modals import (
    AchievementMessage,
    AlreadyRegisteredMessage,
    FastestArrivalMessage,
    InitialMessage,
    PointGetMessage,
    RegistryMessage,
    WeeklyMessage,      # Added WeeklyMessage
    UserAchievement,    # Added UserAchievement
)
from hikarie_bot.models import User, Badge, UserBadge # Added User, Badge, UserBadge


def test_initial_message() -> None:
    """Test the initial message."""
    message = InitialMessage()
    assert message.to_text() == "ヒカリエに出社してる？"  # noqa: RUF001
    assert message.render() == [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "ヒカリエに出社してる？"},  # noqa: RUF001
        },
        {
            "type": "actions",
            "block_id": "FASTEST_ARRIVAL",
            "elements": [
                {
                    "type": "button",
                    "style": "primary",
                    "text": {
                        "type": "plain_text",
                        "text": "最速出社した",
                        "emoji": True,
                    },
                    "action_id": "FASTEST_ARRIVAL",
                },
                {
                    "action_id": "CHECK_ACHIEVEMENT",
                    "text": {
                        "emoji": True,
                        "text": "実績を確認",
                        "type": "plain_text",
                    },
                    "type": "button",
                },
            ],
        },
    ]


def test_registry_message(temp_db: sessionmaker[Session]) -> None:
    """Test the second arrived user has lower point."""
    session = temp_db()
    initially_insert_badge_data(session=session)

    insert_arrival_action(
        session=session,
        jst_datetime=datetime(2024, 1, 1, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
        user_id="test_user_1st",
    )
    message = RegistryMessage(
        session=session,
        jst_datetime=datetime(2024, 1, 1, 7, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
    )
    assert message.render() == [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "ヒカリエに出社してる？"},  # noqa: RUF001
        },
        {
            "type": "actions",
            "block_id": "ARRIVED_OFFICE",
            "elements": [
                {
                    "type": "button",
                    "action_id": "ARRIVED_OFFICE",
                    "text": {
                        "type": "plain_text",
                        "text": "出社した",
                        "emoji": True,
                    },
                },
                {
                    "action_id": "CHECK_ACHIEVEMENT",
                    "text": {
                        "emoji": True,
                        "text": "実績を確認",
                        "type": "plain_text",
                    },
                    "type": "button",
                },
            ],
        },
        {
            "type": "divider",
        },
        {
            "text": {
                "text": "本日の出社ユーザー :hikarie: :\n*06:00* : <@test_user_1st>",
                "type": "mrkdwn",
            },
            "type": "section",
        },
    ]


def test_registry_message_2(temp_db: sessionmaker[Session]) -> None:
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
        jst_datetime=datetime(2024, 1, 1, 6, 1, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
        user_id="test_user_2nd",
    )
    message = RegistryMessage(
        session=session,
        jst_datetime=datetime(2024, 1, 1, 7, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
    )
    assert message.render() == [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "ヒカリエに出社してる？"},  # noqa: RUF001
        },
        {
            "type": "actions",
            "block_id": "ARRIVED_OFFICE",
            "elements": [
                {
                    "type": "button",
                    "action_id": "ARRIVED_OFFICE",
                    "text": {
                        "type": "plain_text",
                        "text": "出社した",
                        "emoji": True,
                    },
                },
                {
                    "action_id": "CHECK_ACHIEVEMENT",
                    "text": {
                        "emoji": True,
                        "text": "実績を確認",
                        "type": "plain_text",
                    },
                    "type": "button",
                },
            ],
        },
        {
            "type": "divider",
        },
        {
            "text": {
                "text": dedent("""\
                        本日の出社ユーザー :hikarie: :
                        *06:00* : <@test_user_1st>
                        *06:01* : <@test_user_2nd>"""),
                "type": "mrkdwn",
            },
            "type": "section",
        },
    ]


def test_fastest_arrival_message(temp_db: sessionmaker[Session]) -> None:
    """Test the fastest arrival message."""
    session = temp_db()
    initially_insert_badge_data(session=session)

    insert_arrival_action(
        session=session,
        jst_datetime=datetime(2024, 1, 1, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
        user_id="test_user",
    )
    message = FastestArrivalMessage(
        user_id="test_user",
        jst_datetime=datetime(2024, 1, 1, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
    )

    assert message.render() == [
        {
            "type": "section",
            "block_id": "FASTEST_ARRIVAL_REPLY",
            "text": {
                "type": "mrkdwn",
                "text": "ヒカリエは正義 :hikarie:\n本日の最速出社: <@test_user> @ 2024-01-01 06:00:00",
            },
        }
    ]


def test_point_get_message(temp_db: sessionmaker[Session]) -> None:
    """Test the point get message."""
    session = temp_db()
    initially_insert_badge_data(session=session)

    insert_arrival_action(
        session=session,
        jst_datetime=datetime(2024, 1, 1, 7, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
        user_id="test_user",
    )

    message = PointGetMessage(
        session,
        user_id="test_user",
        jst_datetime=datetime(2024, 1, 1, 7, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
        initial_arrival=True,
    )

    assert message.render() == [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*07:00* 最速出社登録しました！ :hikarie:\n"  # noqa: RUF001
                "<@test_user>さんのポイント 0 → *7* (*+7*)",
            },
        },
        {
            "type": "divider",
        },
        {
            "elements": [
                {
                    "text": "かたがき: *かけだしのかいしゃいん* (lv1)\n"
                    "つぎのレベルまで: *13pt*\n"
                    "しんこうど: `████      ` | * 35%* (*+35%*)\n"
                    "うちわけ:\n"
                    " - はじめての出社登録:*+2pt*\n"
                    " - 最速出社:*+2pt*\n"
                    " - 朝型出社:*+3pt*",
                    "type": "mrkdwn",
                },
            ],
            "type": "context",
        },
        {
            "type": "divider",
        },
    ]


def test_already_registered_message(temp_db: sessionmaker[Session]) -> None:
    """Test the already registered message."""
    session = temp_db()
    initially_insert_badge_data(session=session)

    message = AlreadyRegisteredMessage(
        user_id="test_user",
        jst_datetime=datetime(2024, 1, 1, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
    )

    assert message.render() == [
        {
            "type": "section",
            "block_id": "ALREADY_REGISTERED_REPLY",
            "text": {
                "type": "mrkdwn",
                "text": "本日の出社登録はすでに完了しています\n<@test_user> @ 2024-01-01 06:00:00",
            },
        }
    ]


@mock.patch("hikarie_bot.modals.BADGE_TYPES_TO_CHECK", [1])
def test_achievement_message(temp_db: sessionmaker[Session]) -> None:
    """Test the achievement message."""
    session = temp_db()
    initially_insert_badge_data(session=session)

    insert_arrival_action(
        session=session,
        jst_datetime=datetime(2024, 1, 1, 7, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
        user_id="test_user",
    )

    message = AchievementMessage(
        session=session,
        user_id="test_user",
    )

    assert message.render() == [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "<@test_user>が獲得したバッジ:\n",
            },
        },
        {
            "type": "divider",
        },
        {
            "text": {
                "text": "*1* : 出社登録BOTを初めて利用した",
                "type": "mrkdwn",
            },
            "type": "section",
        },
        {
            "elements": [
                {
                    "alt_text": "【はじめての出社登録】出社登録BOTを初めて利用した @ 2024-01-01",
                    "image_url": "https://gist.github.com/user-attachments/assets/d9bddfb0-199c-4252-b821-52a62954811f",
                    "type": "image",
                }
            ],
            "type": "context",
        },
        {
            "type": "divider",
        },
    ]


@mock.patch("hikarie_bot.modals.BADGE_TYPES_TO_CHECK", [6])
def test_achievement_message_type_6(temp_db: sessionmaker[Session]) -> None:
    """Test the achievement message with badge_types_to_check patched to [6]."""
    session = temp_db()
    initially_insert_badge_data(session=session)

    insert_arrival_action(
        session=session,
        jst_datetime=datetime(2024, 1, 1, 7, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
        user_id="test_user",
    )

    message = AchievementMessage(
        session=session,
        user_id="test_user",
    )

    rendered = message.render()
    badge_type_sections = [
        block for block in rendered if block.get("type") == "section" and "*6*" in block.get("text", {}).get("text", "")
    ]
    assert badge_type_sections, "Badge type 6 section should be present"
    badge_type_1_sections = [
        block for block in rendered if block.get("type") == "section" and "*1*" in block.get("text", {}).get("text", "")
    ]
    assert not badge_type_1_sections, "Badge type 1 section should not be present"


@mock.patch("hikarie_bot.modals.BADGE_TYPES_TO_CHECK", [6])
def test_achievement_message_6xx_taken_logic(temp_db: sessionmaker[Session]) -> None:
    """Test 6XX badge logic: taken icon if any user has it, not achieved if none."""
    from hikarie_bot.models import Badge, UserBadge # Local import for this test

    session = temp_db()
    initially_insert_badge_data(session=session)

    badge_6xx = session.query(Badge).filter(Badge.badge_type_id == 6, Badge.id >= 600, Badge.id < 700).first()
    assert badge_6xx is not None, "Test requires a 6XX badge of type 6"

    message = AchievementMessage(session=session, user_id="test_user")
    rendered = message.render()
    found = False
    for block in rendered:
        if block.get("type") == "context":
            for element in block.get("elements", []):
                if element.get("type") == "image" and element.get("alt_text", "").startswith(
                    f"【{badge_6xx.message}】"
                ):
                    from hikarie_bot.constants import NOT_ACHIEVED_BADGE_IMAGE_URL
                    assert element["image_url"] == NOT_ACHIEVED_BADGE_IMAGE_URL
                    found = True
    assert found, "Should find not achieved icon for 6XX badge when no user has it"

    session.add(
        UserBadge(
            user_id="other_user",
            user_info_raw_id="other_user",
            badge_id=badge_6xx.id,
            initially_acquired_datetime=datetime(2024, 1, 1, 8, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
            count=1,
        )
    )
    session.commit()

    message = AchievementMessage(session=session, user_id="test_user")
    rendered = message.render()
    found = False
    for block in rendered:
        if block.get("type") == "context":
            for element in block.get("elements", []):
                if element.get("type") == "image" and element.get("alt_text", "").startswith(
                    f"【{badge_6xx.message}】"
                ):
                    from hikarie_bot.constants import TAKEN_6XX_BADGE_IMAGE_URL
                    assert element["image_url"] == TAKEN_6XX_BADGE_IMAGE_URL
                    found = True
    assert found, "Should find taken icon for 6XX badge when another user has it"


def test_get_new_achievements(temp_db: sessionmaker[Session]) -> None:
    """Test the _get_new_achievements method of WeeklyMessage."""
    session = temp_db()
    initially_insert_badge_data(session=session)

    tokyo_tz = zoneinfo.ZoneInfo("Asia/Tokyo")
    report_date = datetime(2024, 7, 7, 0, 0, 0, tzinfo=tokyo_tz)
    start_of_week = report_date - timedelta(days=7)
    end_of_week = report_date - timedelta(microseconds=1)

    default_user_params = {
        "level": 1, "level_name": "Test Level 1", "level_uped": False,
        "point_to_next_level": 100, "point_range_to_next_level": 200, "current_level_point": 50,
    }
    user1 = User(id="user1", current_score=100, previous_score=50, update_datetime=report_date, **default_user_params)
    user2 = User(id="user2", current_score=200, previous_score=150, update_datetime=report_date, **default_user_params)
    session.add_all([user1, user2])
    session.commit()

    test_badge_ids = [5001, 5002, 5003, 5004, 5005, 5006, 5007]
    badges_to_add = []
    for bid in test_badge_ids:
        badges_to_add.append(
            Badge(id=bid, badge_type_id=1, message=f"Message for Badge {bid}", condition=f"Cond {bid}", score=10, level=1)
        )
    session.add_all(badges_to_add)
    session.commit()

    ub1_time = start_of_week + timedelta(days=1)
    ub1 = UserBadge(user_id="user1", user_info_raw_id="user1_raw1", badge_id=test_badge_ids[0], initially_acquired_datetime=ub1_time, last_acquired_datetime=ub1_time, count=1)
    ub2_time = start_of_week + timedelta(days=2)
    ub2 = UserBadge(user_id="user2", user_info_raw_id="user2_raw1", badge_id=test_badge_ids[1], initially_acquired_datetime=ub2_time, last_acquired_datetime=ub2_time, count=1)

    ub3_time = start_of_week - timedelta(days=1)
    ub3 = UserBadge(user_id="user1", user_info_raw_id="user1_raw2", badge_id=test_badge_ids[2], initially_acquired_datetime=ub3_time, last_acquired_datetime=ub3_time, count=1)
    ub4_time = end_of_week + timedelta(days=1)
    ub4 = UserBadge(user_id="user2", user_info_raw_id="user2_raw2", badge_id=test_badge_ids[0], initially_acquired_datetime=ub4_time, last_acquired_datetime=ub4_time, count=1)

    ub5_initial_time = start_of_week - timedelta(days=5)
    ub5_last_time = start_of_week + timedelta(days=3)
    ub5 = UserBadge(user_id="user1", user_info_raw_id="user1_raw3", badge_id=test_badge_ids[3], initially_acquired_datetime=ub5_initial_time, last_acquired_datetime=ub5_last_time, count=2)

    user_badges_to_add = [ub1, ub2, ub3, ub4, ub5]
    candidate_user_badges = []

    cand3_time = start_of_week + timedelta(days=0, hours=12)
    cand3 = UserBadge(user_id="user1", user_info_raw_id="user1_cand3", badge_id=test_badge_ids[2], initially_acquired_datetime=cand3_time, count=1)
    candidate_user_badges.append(cand3)
    cand4_time = start_of_week + timedelta(days=3, hours=12)
    cand4 = UserBadge(user_id="user2", user_info_raw_id="user2_cand4", badge_id=test_badge_ids[3], initially_acquired_datetime=cand4_time, count=1)
    candidate_user_badges.append(cand4)
    cand5_time = start_of_week + timedelta(days=4, hours=12)
    cand5 = UserBadge(user_id="user1", user_info_raw_id="user1_cand5", badge_id=test_badge_ids[4], initially_acquired_datetime=cand5_time, count=1)
    candidate_user_badges.append(cand5)
    cand6_time = start_of_week + timedelta(days=5, hours=12)
    cand6 = UserBadge(user_id="user2", user_info_raw_id="user2_cand6", badge_id=test_badge_ids[5], initially_acquired_datetime=cand6_time, count=1)
    candidate_user_badges.append(cand6)
    cand7_time = start_of_week + timedelta(days=6, hours=12)
    cand7 = UserBadge(user_id="user1", user_info_raw_id="user1_cand7", badge_id=test_badge_ids[6], initially_acquired_datetime=cand7_time, count=1)
    candidate_user_badges.append(cand7)

    candidate_user_badges.extend([ub1, ub2])
    user_badges_to_add.extend([cand3, cand4, cand5, cand6, cand7])
    session.add_all(user_badges_to_add)
    session.commit()

    weekly_message = WeeklyMessage(session=session, report_date=report_date)
    new_achievements = weekly_message._get_new_achievements(session, start_of_week, end_of_week)

    assert len(new_achievements) == 5, "Should return 5 achievements due to limit"

    utc_zone = zoneinfo.ZoneInfo("UTC") # Define UTC zone for convenience

    for ach in new_achievements:
        assert isinstance(ach, UserAchievement), "All items should be UserAchievement instances"
        ach_time_to_compare = ach.achieved_time # This is naive UTC from DB
        if ach_time_to_compare.tzinfo is None: # Should always be naive
            ach_time_utc_aware = ach_time_to_compare.replace(tzinfo=utc_zone)
            ach_time_to_compare = ach_time_utc_aware.astimezone(tokyo_tz)
        else: # Should not happen based on current _get_new_achievements logic
            ach_time_to_compare = ach_time_to_compare.astimezone(tokyo_tz)

        assert start_of_week <= ach_time_to_compare <= end_of_week, \
            f"Achievement time {ach_time_to_compare} (original: {ach.achieved_time}) should be within the week [{start_of_week}, {end_of_week}]"

    for i in range(len(new_achievements) - 1):
        assert new_achievements[i].achieved_time >= new_achievements[i+1].achieved_time, "Achievements should be sorted descending by time"

    returned_tuples = {(ach.user_id, ach.badge_id) for ach in new_achievements}
    assert ("user1", test_badge_ids[2]) not in returned_tuples or \
           any(ach.user_id == "user1" and ach.badge_id == test_badge_ids[2] and (ach.achieved_time.replace(tzinfo=utc_zone).astimezone(tokyo_tz) if ach.achieved_time.tzinfo is None else ach.achieved_time.astimezone(tokyo_tz)) == cand3_time for ach in new_achievements), \
           "ub3 (before week) should not be returned unless it's the valid cand3"
    assert not any(ach.user_id == "user2" and ach.badge_id == test_badge_ids[0] and (ach.achieved_time.replace(tzinfo=utc_zone).astimezone(tokyo_tz) if ach.achieved_time.tzinfo is None else ach.achieved_time.astimezone(tokyo_tz)) == ub4_time for ach in new_achievements), \
           "ub4 (after week) should not be returned"
    assert not any(ach.user_id == "user1" and ach.badge_id == test_badge_ids[3] and (ach.achieved_time.replace(tzinfo=utc_zone).astimezone(tokyo_tz) if ach.achieved_time.tzinfo is None else ach.achieved_time.astimezone(tokyo_tz)) == ub5_initial_time for ach in new_achievements), \
           "ub5 (initial acquire before week) should not be returned"

    filtered_candidates = []
    # utc_zone is defined above in the first loop
    for ub in candidate_user_badges:
        # Assume ub.initially_acquired_datetime might have been converted to naive UTC by SQLAlchemy upon assignment
        dt_potentially_naive_utc = ub.initially_acquired_datetime

        if dt_potentially_naive_utc.tzinfo is None:
            dt_aware_utc = dt_potentially_naive_utc.replace(tzinfo=utc_zone)
        else: # If it's somehow already aware, ensure it's UTC before converting to Tokyo
            dt_aware_utc = dt_potentially_naive_utc.astimezone(utc_zone)

        dt_tokyo_aware = dt_aware_utc.astimezone(tokyo_tz)

        if start_of_week <= dt_tokyo_aware <= end_of_week:
            filtered_candidates.append(ub)

    all_candidates_in_week = sorted(
        filtered_candidates,
        key=lambda x: (x.initially_acquired_datetime.replace(tzinfo=utc_zone).astimezone(tokyo_tz)
                       if x.initially_acquired_datetime.tzinfo is None
                       else x.initially_acquired_datetime.astimezone(tokyo_tz)),
        reverse=True
    )
    expected_top_5_source = all_candidates_in_week[:5]

    for i in range(5):
        expected_ua_source = expected_top_5_source[i]
        actual_ua = new_achievements[i]

        assert actual_ua.user_id == expected_ua_source.user_id
        assert actual_ua.badge_id == expected_ua_source.badge_id

        badge_msg_obj = session.get(Badge, expected_ua_source.badge_id)
        assert badge_msg_obj is not None
        assert actual_ua.message == badge_msg_obj.message

        # Convert expected datetime (from UserBadge Python object) to tokyo_tz for comparison
        # This assumes it might have become naive UTC due to SQLAlchemy attribute handling
        expected_dt_naive_utc = expected_ua_source.initially_acquired_datetime
        if expected_dt_naive_utc.tzinfo is None:
            expected_dt_aware_utc = expected_dt_naive_utc.replace(tzinfo=utc_zone)
        else: # If it's somehow already aware, ensure it's UTC
            expected_dt_aware_utc = expected_dt_naive_utc.astimezone(utc_zone)
        expected_dt_tokyo_compare = expected_dt_aware_utc.astimezone(tokyo_tz)

        # Convert actual datetime (from UserAchievement, sourced from DB naive UTC) to tokyo_tz
        actual_dt_naive_utc = actual_ua.achieved_time
        if actual_dt_naive_utc.tzinfo is None:
            actual_dt_aware_utc = actual_dt_naive_utc.replace(tzinfo=utc_zone)
        else: # Should not happen based on current _get_new_achievements logic
            actual_dt_aware_utc = actual_dt_naive_utc.astimezone(utc_zone)
        actual_dt_tokyo_compare = actual_dt_aware_utc.astimezone(tokyo_tz)

        assert actual_dt_tokyo_compare == expected_dt_tokyo_compare

    session.close()

# Keep existing tests below this line
