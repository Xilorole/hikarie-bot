import zoneinfo
from datetime import date, datetime, timedelta  # Added date back
from textwrap import dedent
from unittest import mock

from sqlalchemy.orm import Session, sessionmaker

from hikarie_bot.curd import initially_insert_badge_data, insert_arrival_action
from hikarie_bot.modals import (
    AchievementView,
    AlreadyRegisteredMessage,
    FastestArrivalMessage,
    InitialMessage,
    PointGetMessage,
    RegistryMessage,
)
from hikarie_bot.models import Badge, User


def test_initial_message() -> None:
    """Test the initial message."""
    message = InitialMessage()
    assert message.to_text() == "ヒカリエに出社してる？"
    assert message.render() == [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "ヒカリエに出社してる？"},
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
            "text": {"type": "mrkdwn", "text": "ヒカリエに出社してる？"},
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
            "text": {"type": "mrkdwn", "text": "ヒカリエに出社してる？"},
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
                "text": "*07:00* 最速出社登録しました！ :hikarie:\n<@test_user>さんのポイント 0 → *7* (*+7*)",
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


def test_point_get_message_max_level(temp_db: sessionmaker[Session]) -> None:
    """Test the point get message says the upper limit is reached."""
    session = temp_db()
    initially_insert_badge_data(session=session)
    jst = zoneinfo.ZoneInfo("Asia/Tokyo")

    insert_arrival_action(session=session, jst_datetime=datetime(2024, 1, 1, 7, 0, 0, tzinfo=jst), user_id="test_user")
    user = session.query(User).filter(User.id == "test_user").one()
    user.current_score = 1398
    session.commit()

    # 1398 -> 1403: the upper limit is reached by this arrival
    insert_arrival_action(session=session, jst_datetime=datetime(2024, 1, 2, 7, 0, 0, tzinfo=jst), user_id="test_user")
    message = PointGetMessage(
        session,
        user_id="test_user",
        jst_datetime=datetime(2024, 1, 2, 7, 0, 0, tzinfo=jst),
        initial_arrival=True,
    ).render()

    assert message[0]["text"]["text"] == (
        "*07:00* 最速出社登録しました！ :hikarie:\n<@test_user>さんのポイント 1398 → *1403* (*+5*) *上限に到達!* :crown: "
    )
    assert message[2]["elements"][0]["text"].startswith(
        "かたがき: *でんせつのかいしゃいん* (lv12)\nつぎのレベルまで: *上限に到達*\nしんこうど: `██████████` | *100%*\n"
    )

    # 1403 -> 1408: already at the upper limit
    insert_arrival_action(session=session, jst_datetime=datetime(2024, 1, 3, 7, 0, 0, tzinfo=jst), user_id="test_user")
    message = PointGetMessage(
        session,
        user_id="test_user",
        jst_datetime=datetime(2024, 1, 3, 7, 0, 0, tzinfo=jst),
        initial_arrival=True,
    ).render()

    assert message[0]["text"]["text"].endswith("1403 → *1408* (*+5*)")
    assert "つぎのレベルまで: *上限に到達*" in message[2]["elements"][0]["text"]


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
def test_achievement_view(temp_db: sessionmaker[Session]) -> None:
    """Test the achievement view."""
    session = temp_db()
    initially_insert_badge_data(session=session)

    insert_arrival_action(
        session=session,
        jst_datetime=datetime(2024, 1, 1, 7, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
        user_id="test_user",
    )

    view = AchievementView(
        session=session,
        user_id="test_user",
    )
    expected_blocks = [
        {"text": {"text": "*1系 : 出社登録BOTを初めて利用した*", "type": "mrkdwn"}, "type": "section"},
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
    ]
    rendered_blocks = [block.to_dict() for block in view.blocks]
    for expected_block in expected_blocks:
        assert expected_block in rendered_blocks


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

    view = AchievementView(
        session=session,
        user_id="test_user",
    )

    rendered = [block.to_dict() for block in view.blocks]
    badge_type_sections = [
        block
        for block in rendered
        if block.get("type") == "section" and "*6系" in block.get("text", {}).get("text", "")
    ]
    assert badge_type_sections, "Badge type 6 section should be present"
    badge_type_1_sections = [
        block
        for block in rendered
        if block.get("type") == "section" and "*1系" in block.get("text", {}).get("text", "")
    ]
    assert not badge_type_1_sections, "Badge type 1 section should not be present"


@mock.patch("hikarie_bot.modals.BADGE_TYPES_TO_CHECK", [6])
def test_achievement_message_6xxx_taken_logic(temp_db: sessionmaker[Session]) -> None:
    """Test 6XXX badge logic: taken icon if any user has it, not achieved if none."""
    session = temp_db()
    initially_insert_badge_data(session=session)

    badge_6xxx = session.query(Badge).filter(Badge.badge_type_id == 6, Badge.id >= 6000, Badge.id < 7000).first()
    assert badge_6xxx is not None, "Test requires a 6XXX badge of type 6"

    # at least 10 arrivals to get the 6XXX badge
    for i in range(10):
        insert_arrival_action(
            session=session,
            jst_datetime=datetime(2024, 1, 1 + i, 7, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")),
            user_id="test_user",
        )

    # 取得したバッジが表示されていることのテスト
    view = AchievementView(session=session, user_id="test_user")
    rendered = [block.to_dict() for block in view.blocks]
    found = False
    for block in rendered:
        if block.get("type") == "context":
            for element in block.get("elements", []):
                if element.get("type") == "image" and element.get("alt_text", "").startswith(
                    f"【{badge_6xxx.message}】"
                ):
                    from hikarie_bot.constants import ACHIEVED_BADGE_IMAGE_URL

                    assert element["image_url"] == ACHIEVED_BADGE_IMAGE_URL
                    found = True
    assert found, "Should find taken icon for 6XXX badge when another user has it"


def test_achievement_view_attendance_history(temp_db: sessionmaker[Session]) -> None:
    """Test the attendance history section in AchievementView."""
    session = temp_db()
    initially_insert_badge_data(session=session)

    tokyo_tz = zoneinfo.ZoneInfo("Asia/Tokyo")

    # Create test user
    test_user_id = "test_user"

    # Create attendance data over the past 10 weeks (some attended, some not)
    base_date = datetime(2024, 3, 18, 9, 0, 0, tzinfo=tokyo_tz)  # Monday
    attendance_dates = []

    # Add some attendance records over 10 weeks (weekdays only)
    for week in range(10):
        week_start = base_date + timedelta(weeks=week)

        # Attend on Monday and Wednesday of each week
        monday = week_start
        wednesday = week_start + timedelta(days=2)

        if monday.weekday() == 0:  # Ensure it's Monday
            attendance_dates.extend([monday, wednesday])

    # Insert arrival actions for the attendance dates
    for date_time in attendance_dates:
        insert_arrival_action(session=session, jst_datetime=date_time, user_id=test_user_id)

    # Test with current date being a Wednesday in week 10
    test_current_date = base_date + timedelta(weeks=9, days=2)  # Wednesday of week 10

    with (
        mock.patch("hikarie_bot.utils.get_current_jst_datetime", return_value=test_current_date),
        mock.patch("hikarie_bot.modals.BADGE_TYPES_TO_CHECK", [1]),  # Minimize badge data
    ):
        view = AchievementView(session=session, user_id=test_user_id)

        # Get the rendered blocks
        rendered_blocks = [block.to_dict() for block in view.blocks]

        # Check that attendance history header exists
        header_blocks = [block for block in rendered_blocks if block.get("type") == "header"]
        attendance_header_found = any(
            "過去の出社履歴" in block.get("text", {}).get("text", "") for block in header_blocks
        )
        assert attendance_header_found, "Attendance history header should be present"

        # Check that context blocks (attendance data) exist
        context_blocks = [block for block in rendered_blocks if block.get("type") == "context"]
        attendance_context_blocks = [
            block
            for block in context_blocks
            if any(
                element.get("type") == "image"
                and ("出社" in element.get("alt_text", "") or "未出社" in element.get("alt_text", ""))
                and ("/" in element.get("alt_text", ""))  # 日付形式 (MM/DD) を含む
                for element in block.get("elements", [])
            )
        ]

        # Should have attendance context blocks (may be fewer than 5 if some weekdays have no data)
        # Only count blocks that have attendance data (not badge data)
        assert len(attendance_context_blocks) > 0, (
            f"Should have attendance context blocks, got {len(attendance_context_blocks)}\n"
            f"Context blocks found: {len(context_blocks)}\n"
            f"Attendance blocks: {[block.get('elements', [])[:2] for block in attendance_context_blocks]}"
        )

        # Check that each context block has at most 10 elements (Slack limit)
        for block in attendance_context_blocks:
            elements = block.get("elements", [])
            assert len(elements) <= 10, f"Context block should have at most 10 elements, got {len(elements)}"

            # Verify all elements are image elements with proper alt text
            for element in elements:
                assert element.get("type") == "image", "All elements should be image type"
                alt_text = element.get("alt_text", "")
                assert "出社" in alt_text or "未出社" in alt_text, (
                    f"Alt text should contain attendance info: {alt_text}"
                )
                assert "/" in alt_text, f"Alt text should contain date with /: {alt_text}"


def test_get_attendance_data_for_past_10_weeks(temp_db: sessionmaker[Session]) -> None:
    """Test the _get_attendance_data_for_past_10_weeks method specifically."""
    session = temp_db()
    initially_insert_badge_data(session=session)

    tokyo_tz = zoneinfo.ZoneInfo("Asia/Tokyo")
    test_user_id = "test_user"

    # Set current date to a Wednesday
    current_date = datetime(2024, 3, 20, 15, 0, 0, tzinfo=tokyo_tz)  # Wednesday

    # Create attendance on specific dates
    attendance_dates = [
        datetime(2024, 1, 22, 9, 0, 0, tzinfo=tokyo_tz),  # Monday, 8 weeks ago
        datetime(2024, 2, 14, 9, 0, 0, tzinfo=tokyo_tz),  # Wednesday, 5 weeks ago
        datetime(2024, 3, 18, 9, 0, 0, tzinfo=tokyo_tz),  # Monday, this week
        datetime(2024, 3, 20, 9, 0, 0, tzinfo=tokyo_tz),  # Wednesday, today
    ]

    for date_time in attendance_dates:
        insert_arrival_action(session=session, jst_datetime=date_time, user_id=test_user_id)

    with (
        mock.patch("hikarie_bot.utils.get_current_jst_datetime", return_value=current_date),
        mock.patch("hikarie_bot.modals.BADGE_TYPES_TO_CHECK", [1]),
    ):
        view = AchievementView(session=session, user_id=test_user_id)

        # Call the protected method directly for testing
        attendance_data = view._get_attendance_data_for_past_10_weeks()  # noqa: SLF001

        # Check that we have data for the correct date range
        assert len(attendance_data) > 0, "Should have attendance data"

        # Verify that only weekdays are included
        for date_obj in attendance_data:
            assert date_obj.weekday() < 5, f"Should only include weekdays, got {date_obj.strftime('%A')}"

        # Check specific attendance records
        assert attendance_data.get(date(2024, 1, 22)) is True, "Should show attendance on 2024-01-22"
        assert attendance_data.get(date(2024, 2, 14)) is True, "Should show attendance on 2024-02-14"
        assert attendance_data.get(date(2024, 3, 18)) is True, "Should show attendance on 2024-03-18 (this week Monday)"
        assert attendance_data.get(date(2024, 3, 20)) is True, "Should show attendance on 2024-03-20 (today)"

        # Check that some non-attendance days exist
        assert attendance_data.get(date(2024, 1, 23)) is False, "Should show no attendance on 2024-01-23"


def test_create_github_style_display(temp_db: sessionmaker[Session]) -> None:
    """Test the _create_github_style_display method."""
    session = temp_db()
    initially_insert_badge_data(session=session)

    tokyo_tz = zoneinfo.ZoneInfo("Asia/Tokyo")
    test_user_id = "test_user"
    current_date = datetime(2024, 3, 20, 15, 0, 0, tzinfo=tokyo_tz)

    # Create a small set of test data
    test_attendance_data = [
        datetime(2024, 3, 18, 9, 0, 0, tzinfo=tokyo_tz),  # monday
        datetime(2024, 3, 20, 9, 0, 0, tzinfo=tokyo_tz),  # wednesday
    ]

    for date_time in test_attendance_data:
        insert_arrival_action(session=session, jst_datetime=date_time, user_id=test_user_id)

    with (
        mock.patch("hikarie_bot.utils.get_current_jst_datetime", return_value=current_date),
        mock.patch("hikarie_bot.modals.BADGE_TYPES_TO_CHECK", [1]),
    ):
        view = AchievementView(session=session, user_id=test_user_id)

        # Check that blocks were created
        rendered_blocks = [block.to_dict() for block in view.blocks]
        import re

        context_blocks = [
            block
            for block in rendered_blocks
            if block.get("type") == "context"
            and all(
                re.match(r"\d{2}\/\d{2} (出社|未出社)", element.get("alt_text", ""))
                for element in block.get("elements", [])
            )
        ]

        assert len(context_blocks) == 5, f"Should have 5 context blocks for 5 weekdays, got {len(context_blocks)}"

        # Check that image elements have correct URLs
        from hikarie_bot.constants import ACHIEVED_BADGE_IMAGE_URL as ARRIVED_IMAGE_URL
        from hikarie_bot.constants import NOT_ACHIEVED_BADGE_IMAGE_URL as NOT_ARRIVED_IMAGE_URL

        all_elements = []
        for block in context_blocks:
            all_elements.extend(block.get("elements", []))

        attended_elements = [elem for elem in all_elements if elem.get("image_url") == ARRIVED_IMAGE_URL]
        not_attended_elements = [elem for elem in all_elements if elem.get("image_url") == NOT_ARRIVED_IMAGE_URL]

        # M xxxxxxxxxo <- last monday
        # T xxxxxxxxxx
        # W xxxxxxxxxo <- last wednesday (today)
        # T xxxxxxxxx-
        # F xxxxxxxxx-
        #            ^ the week of 2024-03-18
        # -> attended_elements: 2
        # -> not_attended_elements: 46 (5x9 + 1)

        assert len(attended_elements) == 2, f"Should have 2 attended elements, got {len(attended_elements)}"
        assert len(not_attended_elements) == 46, (
            f"Should have 46 not attended elements, got {len(not_attended_elements)}"
        )


def test_achievement_view_attendance_history_simple(temp_db: sessionmaker[Session]) -> None:
    """Test that attendance history section is added to AchievementView."""
    session = temp_db()
    initially_insert_badge_data(session=session)

    tokyo_tz = zoneinfo.ZoneInfo("Asia/Tokyo")
    test_user_id = "test_user"

    # Insert a simple attendance record
    attendance_date = datetime(2024, 3, 18, 9, 0, 0, tzinfo=tokyo_tz)  # Monday
    insert_arrival_action(session=session, jst_datetime=attendance_date, user_id=test_user_id)

    # Mock current date to be in the same timeframe
    current_date = datetime(2024, 3, 20, 15, 0, 0, tzinfo=tokyo_tz)  # Wednesday

    with (
        mock.patch("hikarie_bot.utils.get_current_jst_datetime", return_value=current_date),
        mock.patch("hikarie_bot.modals.BADGE_TYPES_TO_CHECK", [1]),
    ):
        view = AchievementView(session=session, user_id=test_user_id)

        # Check that blocks were created
        assert len(view.blocks) > 0, "View should have blocks"

        # Convert to dict for easier testing
        rendered_blocks = [block.to_dict() for block in view.blocks]

        # Check for header block containing attendance history
        header_found = any(
            block.get("type") == "header" and "出社履歴" in block.get("text", {}).get("text", "")
            for block in rendered_blocks
        )
        assert header_found, "Should have attendance history header"

        # Check for context blocks with attendance data (image elements)
        attendance_context_blocks = [
            block
            for block in rendered_blocks
            if block.get("type") == "context"
            and any(
                element.get("type") == "image"
                and ("出社" in element.get("alt_text", "") or "未出社" in element.get("alt_text", ""))
                and "/" in element.get("alt_text", "")  # Date format MM/DD
                for element in block.get("elements", [])
            )
        ]

        # Should have attendance context blocks (up to 5 for weekdays)
        assert len(attendance_context_blocks) > 0, "Should have attendance context blocks"


def test_attendance_data_generation(temp_db: sessionmaker[Session]) -> None:
    """Test basic attendance data generation."""
    session = temp_db()
    initially_insert_badge_data(session=session)

    tokyo_tz = zoneinfo.ZoneInfo("Asia/Tokyo")
    test_user_id = "test_user"

    # Create test data
    attendance_date = datetime(2024, 3, 18, 9, 0, 0, tzinfo=tokyo_tz)  # Monday
    insert_arrival_action(session=session, jst_datetime=attendance_date, user_id=test_user_id)

    current_date = datetime(2024, 3, 20, 15, 0, 0, tzinfo=tokyo_tz)  # Wednesday

    with (
        mock.patch("hikarie_bot.utils.get_current_jst_datetime", return_value=current_date),
        mock.patch("hikarie_bot.modals.BADGE_TYPES_TO_CHECK", [1]),
    ):
        view = AchievementView(session=session, user_id=test_user_id)

        # Test the data generation method directly
        attendance_data = view._get_attendance_data_for_past_10_weeks()  # noqa: SLF001

        # Basic checks
        assert isinstance(attendance_data, dict), "Should return a dictionary"
        assert len(attendance_data) > 0, "Should have some attendance data"

        # Check that the attendance date is recorded
        assert attendance_data.get(date(2024, 3, 18)) is True, "Should show attendance on 2024-03-18"

        # Check that weekdays only are included
        for date_obj in attendance_data:
            assert date_obj.weekday() < 5, f"Should only include weekdays, got {date_obj.strftime('%A')}"
