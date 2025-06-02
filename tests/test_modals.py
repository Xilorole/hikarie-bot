import zoneinfo
from datetime import datetime
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
    WeeklyMessage,
    UserAchievement,
)


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

    # The expected output will depend on the badge data for type 6.
    # We expect a section for badge type 6, and context blocks for its badges.
    # Since badge data is seeded by initially_insert_badge_data, we expect at least the section header and badge type 6 description.
    # The badge images will be "not achieved" unless test_user has a badge of type 6.

    rendered = message.render()
    # Check that only badge type 6 is present in the output
    badge_type_sections = [
        block for block in rendered if block.get("type") == "section" and "*6*" in block.get("text", {}).get("text", "")
    ]
    assert badge_type_sections, "Badge type 6 section should be present"
    # There should be no badge type 1 section
    badge_type_1_sections = [
        block for block in rendered if block.get("type") == "section" and "*1*" in block.get("text", {}).get("text", "")
    ]
    assert not badge_type_1_sections, "Badge type 1 section should not be present"


@mock.patch("hikarie_bot.modals.BADGE_TYPES_TO_CHECK", [6])
def test_achievement_message_6xx_taken_logic(temp_db: sessionmaker[Session]) -> None:
    """Test 6XX badge logic: taken icon if any user has it, not achieved if none."""
    from hikarie_bot.models import Badge, UserBadge

    session = temp_db()
    initially_insert_badge_data(session=session)

    # Find a badge with id in 600-699 and type 6
    badge_6xx = session.query(Badge).filter(Badge.badge_type_id == 6, Badge.id >= 600, Badge.id < 700).first()
    assert badge_6xx is not None, "Test requires a 6XX badge of type 6"

    # Case 1: No user has the badge
    message = AchievementMessage(session=session, user_id="test_user")
    rendered = message.render()
    # Find the context block for this badge
    found = False
    for block in rendered:
        if block.get("type") == "context":
            for element in block.get("elements", []):
                if element.get("type") == "image" and element.get("alt_text", "").startswith(
                    f"【{badge_6xx.message}】"
                ):
                    # Should be NOT_ACHIEVED_BADGE_IMAGE_URL
                    from hikarie_bot.constants import NOT_ACHIEVED_BADGE_IMAGE_URL

                    assert element["image_url"] == NOT_ACHIEVED_BADGE_IMAGE_URL
                    found = True
    assert found, "Should find not achieved icon for 6XX badge when no user has it"

    # Case 2: Another user has the badge
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


class TestWeeklyMessage:
    def test_get_new_achievements_no_achievements(self, temp_db: sessionmaker[Session]) -> None:
        """Test _get_new_achievements when there are no new achievements."""
        session = temp_db()
        initially_insert_badge_data(session=session)
        report_date = datetime(2024, 1, 8, 0, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo"))
        weekly_message = WeeklyMessage(session=session, report_date=report_date)

        new_achievements = weekly_message._get_new_achievements(
            session,
            weekly_message.start_of_week,
            weekly_message.end_of_week
        )
        assert new_achievements == []

    def test_get_new_achievements_first_time_achievement_in_week(self, temp_db: sessionmaker[Session]) -> None:
        """Test _get_new_achievements when a user gets an achievement for the first time within the week."""
        session = temp_db()
        initially_insert_badge_data(session=session)

        user_id = "test_user_new_achieve"
        # This arrival will trigger a "welcome" badge (ID 101) and others.
        achievement_time = datetime(2024, 1, 2, 10, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")) # Report week: Jan 1 to Jan 7

        insert_arrival_action(
            session=session,
            jst_datetime=achievement_time,
            user_id=user_id,
        )

        report_date = datetime(2024, 1, 8, 0, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo"))
        weekly_message = WeeklyMessage(session=session, report_date=report_date) # Covers Jan 1 to Jan 7

        new_achievements = weekly_message._get_new_achievements(
            session,
            weekly_message.start_of_week, # Jan 1, 00:00
            weekly_message.end_of_week    # Jan 8, 00:00
        )

        assert len(new_achievements) > 0

        found_welcome_badge = False
        for ach in new_achievements:
            if ach.user_id == user_id and ach.badge_id == 101: # welcome badge
                # The achieved_time in UserAchievement should be the time of the Achievement record
                assert ach.achieved_time == achievement_time
                found_welcome_badge = True
                break
        assert found_welcome_badge, "Welcome badge should be in new achievements for the user"

    def test_get_new_achievements_already_achieved_badge_in_week(self, temp_db: sessionmaker[Session]) -> None:
        """Test _get_new_achievements when a user gets an already achieved badge again within the week."""
        session = temp_db()
        initially_insert_badge_data(session=session)

        user_id = "test_user_re_achieve"
        # First achievement (e.g., welcome badge) in the previous week
        first_achievement_time = datetime(2023, 12, 26, 10, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo"))
        insert_arrival_action(
            session=session,
            jst_datetime=first_achievement_time,
            user_id=user_id,
        )

        # Second achievement (same badge type) within the current report week
        second_achievement_time = datetime(2024, 1, 2, 10, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo"))
        insert_arrival_action(
            session=session,
            jst_datetime=second_achievement_time,
            user_id=user_id,
        )

        report_date = datetime(2024, 1, 8, 0, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo"))
        weekly_message = WeeklyMessage(session=session, report_date=report_date)

        new_achievements = weekly_message._get_new_achievements(
            session,
            weekly_message.start_of_week, # Jan 1, 00:00
            weekly_message.end_of_week    # Jan 8, 00:00
        )

        # The welcome badge (ID 101) was first achieved on Dec 26, so it's not "new" in Jan 1-7 report
        is_welcome_badge_present_as_new = any(ach.badge_id == 101 and ach.user_id == user_id for ach in new_achievements)
        assert not is_welcome_badge_present_as_new, "Previously achieved welcome badge should not be in new achievements list"

    def test_get_new_achievements_multiple_users(self, temp_db: sessionmaker[Session]) -> None:
        """Test _get_new_achievements with multiple users and mixed new/old achievements."""
        session = temp_db()
        initially_insert_badge_data(session=session)

        user1_id = "user1_new_in_week"       # New user, gets welcome badge (101) this week
        user2_id = "user2_old_re_achieve" # Old user, got welcome badge last week, re-achieves this week
        user3_id = "user3_new_fastest"    # New user, gets welcome (101) and fastest (201) this week

        # User1: New achievement (welcome badge) in the current week
        user1_achieve_time = datetime(2024, 1, 2, 9, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo"))
        insert_arrival_action(session=session, jst_datetime=user1_achieve_time, user_id=user1_id)

        # User2: Achieved welcome badge last week, and again this week
        user2_past_achieve_time = datetime(2023, 12, 25, 9, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")) # Last week
        insert_arrival_action(session=session, jst_datetime=user2_past_achieve_time, user_id=user2_id)
        user2_current_achieve_time = datetime(2024, 1, 3, 9, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")) # This week
        insert_arrival_action(session=session, jst_datetime=user2_current_achieve_time, user_id=user2_id)

        # User3: New user, gets welcome (101) and fastest arrival (201) this week.
        # To ensure fastest, make their arrival earliest on a day.
        user3_achieve_time = datetime(2024, 1, 1, 8, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")) # Earliest on Jan 1
        insert_arrival_action(session=session, jst_datetime=user3_achieve_time, user_id=user3_id)

        report_date = datetime(2024, 1, 8, 0, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")) # Report for Jan 1 - Jan 7
        weekly_message = WeeklyMessage(session=session, report_date=report_date)

        new_achievements = weekly_message._get_new_achievements(
            session,
            weekly_message.start_of_week,
            weekly_message.end_of_week
        )

        user1_new_unlocks = [ach for ach in new_achievements if ach.user_id == user1_id]
        user2_new_unlocks = [ach for ach in new_achievements if ach.user_id == user2_id]
        user3_new_unlocks = [ach for ach in new_achievements if ach.user_id == user3_id]

        assert any(ach.badge_id == 101 for ach in user1_new_unlocks), "User1 should have new welcome badge"
        assert len(user2_new_unlocks) == 0, "User2 should have no new unlocks as welcome badge was from past"

        assert any(ach.badge_id == 101 for ach in user3_new_unlocks), "User3 should have new welcome badge"
        assert any(ach.badge_id == 201 for ach in user3_new_unlocks), "User3 should have new fastest arrival badge"
        # Check total number of new unlocks for user3, could be more depending on other badges triggered
        assert len(user3_new_unlocks) >= 2


    def test_get_new_achievements_limit_five(self, temp_db: sessionmaker[Session]) -> None:
        """Test that _get_new_achievements returns a maximum of 5 achievements if many new ones exist."""
        session = temp_db()
        initially_insert_badge_data(session=session)

        # Create 6 users, each getting a new "welcome" badge on different days within the week
        for i in range(6):
            user_id = f"new_user_for_limit_test_{i}"
            # Stagger achievement times to ensure distinct Achievement records
            achievement_time = datetime(2024, 1, 1 + i, 10, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo"))
            insert_arrival_action(
                session=session,
                jst_datetime=achievement_time,
                user_id=user_id,
            )

        # Report date covers the week these achievements happened
        report_date = datetime(2024, 1, 8, 0, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo"))
        weekly_message = WeeklyMessage(session=session, report_date=report_date)

        new_achievements = weekly_message._get_new_achievements(
            session,
            weekly_message.start_of_week, # Jan 1
            weekly_message.end_of_week    # Jan 8
        )
        # Even if more than 5 new unlocks occurred, the function should limit the output.
        assert len(new_achievements) <= 5
