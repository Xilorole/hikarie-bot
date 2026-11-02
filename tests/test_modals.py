import re
from datetime import date, datetime, timedelta
from textwrap import dedent
from unittest import mock

from hikarie_bot.constants import ACHIEVED_BADGE_IMAGE_URL, NOT_ACHIEVED_BADGE_IMAGE_URL
from hikarie_bot.db_data import Badges
from hikarie_bot.engine import JST, ArrivalResult
from hikarie_bot.modals import (
    AchievementView,
    InitialMessage,
    PointGetMessage,
    RegistryMessage,
)
from tests.helpers import compute_in_order


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


def test_registry_message() -> None:
    """Test the second arrived user has lower point."""
    engine = compute_in_order(("test_user_1st", datetime(2024, 1, 1, 6, 0, 0, tzinfo=JST)))
    message = RegistryMessage(engine.arrivals_on(date(2024, 1, 1)))
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


def test_registry_message_2() -> None:
    """Test the second arrived user has lower point."""
    engine = compute_in_order(
        ("test_user_2nd", datetime(2024, 1, 1, 6, 1, 0, tzinfo=JST)),
        ("test_user_1st", datetime(2024, 1, 1, 6, 0, 0, tzinfo=JST)),
    )
    message = RegistryMessage(engine.arrivals_on(date(2024, 1, 1)))
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


def test_point_get_message() -> None:
    """Test the point get message."""
    engine = compute_in_order(("test_user", datetime(2024, 1, 1, 7, 0, 0, tzinfo=JST)))
    message = PointGetMessage(engine.results[0])

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


def point_get_after(day: int, previous_score: int) -> list[dict]:
    """Render the point message for a +5pt fastest arrival on 2024-01-<day>, starting from previous_score.

    The result is built by hand; reaching arbitrary scores through arrivals would take years of them.
    """
    arrival = ArrivalResult(
        id=1,
        user_id="test_user",
        time=datetime(2024, 1, day, 7, 0, 0, tzinfo=JST),
        rank=1,
        badge_ids=[],
        score_sum=5,
        previous_score=previous_score,
        current_score=previous_score + 5,
    )
    return PointGetMessage(arrival).render()


def test_point_get_message_max_level() -> None:
    """Test the point get message says the upper limit is reached."""
    # 1398 -> 1403: the upper limit is reached by this arrival
    message = point_get_after(2, 1398)
    assert message[0]["text"]["text"] == (
        "*07:00* 最速出社登録しました！ :hikarie:\n<@test_user>さんのポイント 1398 → *1403* (*+5*) *上限に到達!* :crown: "
    )
    assert message[2]["elements"][0]["text"].startswith(
        "かたがき: *でんせつのかいしゃいん* (lv12)\nつぎのレベルまで: *上限に到達*\nしんこうど: `██████████` | *100%*\n"
    )

    # 1403 -> 1408: already at the upper limit
    message = point_get_after(3, 1403)
    assert message[0]["text"]["text"].endswith("1403 → *1408* (*+5*)")
    assert "つぎのレベルまで: *上限に到達*" in message[2]["elements"][0]["text"]


def test_point_get_message_zero_progress() -> None:
    """Test the progress bar shows at least one cell when the progress is 0%."""
    # 15 -> 20: exactly at the start of lv2
    message = point_get_after(2, 15)

    assert message[0]["text"]["text"].endswith("15 → *20* (*+5*) *LvUP!* :star2: ")
    assert "しんこうど: `█         ` | *  0%* (*+22%*)\n" in message[2]["elements"][0]["text"]


@mock.patch("hikarie_bot.modals.BADGE_TYPES_TO_CHECK", [1])
def test_achievement_view() -> None:
    """Test the achievement view."""
    engine = compute_in_order(("test_user", datetime(2024, 1, 1, 7, 0, 0, tzinfo=JST)))

    view = AchievementView(
        engine,
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
def test_achievement_message_type_6() -> None:
    """Test the achievement message with badge_types_to_check patched to [6]."""
    engine = compute_in_order(("test_user", datetime(2024, 1, 1, 7, 0, 0, tzinfo=JST)))

    view = AchievementView(
        engine,
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
def test_achievement_message_6xxx_taken_logic() -> None:
    """Test 6XXX badge logic: taken icon if any user has it, not achieved if none."""
    badge_6xxx = next(badge for badge in Badges if badge.badge_type_id == 6 and 6000 <= badge.id < 7000)
    assert badge_6xxx is not None, "Test requires a 6XXX badge of type 6"

    # at least 10 arrivals to get the 6XXX badge
    engine = compute_in_order(*(("test_user", datetime(2024, 1, 1 + i, 7, 0, 0, tzinfo=JST)) for i in range(10)))

    # 取得したバッジが表示されていることのテスト
    view = AchievementView(engine, user_id="test_user")
    rendered = [block.to_dict() for block in view.blocks]
    found = False
    for block in rendered:
        if block.get("type") == "context":
            for element in block.get("elements", []):
                if element.get("type") == "image" and element.get("alt_text", "").startswith(
                    f"【{badge_6xxx.message}】"
                ):
                    assert element["image_url"] == ACHIEVED_BADGE_IMAGE_URL
                    found = True
    assert found, "Should find taken icon for 6XXX badge when another user has it"


def test_achievement_view_attendance_history() -> None:
    """Test the attendance history section in AchievementView."""
    # Create test user
    test_user_id = "test_user"

    # Create attendance data over the past 10 weeks (some attended, some not)
    base_date = datetime(2024, 3, 18, 9, 0, 0, tzinfo=JST)  # Monday
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
    engine = compute_in_order(*((test_user_id, date_time) for date_time in attendance_dates))

    # Test with current date being a Wednesday in week 10
    test_current_date = base_date + timedelta(weeks=9, days=2)  # Wednesday of week 10

    with (
        mock.patch("hikarie_bot.modals.get_current_jst_datetime", return_value=test_current_date),
        mock.patch("hikarie_bot.modals.BADGE_TYPES_TO_CHECK", [1]),  # Minimize badge data
    ):
        view = AchievementView(engine, user_id=test_user_id)

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


def test_get_attendance_data_for_past_10_weeks() -> None:
    """Test the _get_attendance_data_for_past_10_weeks method specifically."""
    test_user_id = "test_user"

    # Set current date to a Wednesday
    current_date = datetime(2024, 3, 20, 15, 0, 0, tzinfo=JST)  # Wednesday

    # Create attendance on specific dates
    attendance_dates = [
        datetime(2024, 1, 22, 9, 0, 0, tzinfo=JST),  # Monday, 8 weeks ago
        datetime(2024, 2, 14, 9, 0, 0, tzinfo=JST),  # Wednesday, 5 weeks ago
        datetime(2024, 3, 18, 9, 0, 0, tzinfo=JST),  # Monday, this week
        datetime(2024, 3, 20, 9, 0, 0, tzinfo=JST),  # Wednesday, today
    ]

    engine = compute_in_order(*((test_user_id, date_time) for date_time in attendance_dates))

    with (
        mock.patch("hikarie_bot.modals.get_current_jst_datetime", return_value=current_date),
        mock.patch("hikarie_bot.modals.BADGE_TYPES_TO_CHECK", [1]),
    ):
        view = AchievementView(engine, user_id=test_user_id)

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


def test_create_github_style_display() -> None:
    """Test the _create_github_style_display method."""
    test_user_id = "test_user"
    current_date = datetime(2024, 3, 20, 15, 0, 0, tzinfo=JST)

    # Create a small set of test data
    test_attendance_data = [
        datetime(2024, 3, 18, 9, 0, 0, tzinfo=JST),  # monday
        datetime(2024, 3, 20, 9, 0, 0, tzinfo=JST),  # wednesday
    ]

    engine = compute_in_order(*((test_user_id, date_time) for date_time in test_attendance_data))

    with (
        mock.patch("hikarie_bot.modals.get_current_jst_datetime", return_value=current_date),
        mock.patch("hikarie_bot.modals.BADGE_TYPES_TO_CHECK", [1]),
    ):
        view = AchievementView(engine, user_id=test_user_id)

        # Check that blocks were created
        rendered_blocks = [block.to_dict() for block in view.blocks]

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
        all_elements = []
        for block in context_blocks:
            all_elements.extend(block.get("elements", []))

        attended_elements = [elem for elem in all_elements if elem.get("image_url") == ACHIEVED_BADGE_IMAGE_URL]
        not_attended_elements = [elem for elem in all_elements if elem.get("image_url") == NOT_ACHIEVED_BADGE_IMAGE_URL]

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


def test_achievement_view_attendance_history_simple() -> None:
    """Test that attendance history section is added to AchievementView."""
    test_user_id = "test_user"

    # Insert a simple attendance record
    attendance_date = datetime(2024, 3, 18, 9, 0, 0, tzinfo=JST)  # Monday
    engine = compute_in_order((test_user_id, attendance_date))

    # Mock current date to be in the same timeframe
    current_date = datetime(2024, 3, 20, 15, 0, 0, tzinfo=JST)  # Wednesday

    with (
        mock.patch("hikarie_bot.modals.get_current_jst_datetime", return_value=current_date),
        mock.patch("hikarie_bot.modals.BADGE_TYPES_TO_CHECK", [1]),
    ):
        view = AchievementView(engine, user_id=test_user_id)

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


def test_attendance_data_generation() -> None:
    """Test basic attendance data generation."""
    test_user_id = "test_user"

    # Create test data
    attendance_date = datetime(2024, 3, 18, 9, 0, 0, tzinfo=JST)  # Monday
    engine = compute_in_order((test_user_id, attendance_date))

    current_date = datetime(2024, 3, 20, 15, 0, 0, tzinfo=JST)  # Wednesday

    with (
        mock.patch("hikarie_bot.modals.get_current_jst_datetime", return_value=current_date),
        mock.patch("hikarie_bot.modals.BADGE_TYPES_TO_CHECK", [1]),
    ):
        view = AchievementView(engine, user_id=test_user_id)

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


@mock.patch("hikarie_bot.modals.BADGE_TYPES_TO_CHECK", [6])
def test_unachieved_list_shows_the_next_kiriban_of_all_arrivals() -> None:
    """Someone without kiribans still sees the next kiriban to be reached by everyone's arrivals."""
    # the 10th and 11th arrivals are kiribans, taken by other users
    engine = compute_in_order(
        *((f"user_{i}", datetime(2024, 1, 1 + i, 7, 0, 0, tzinfo=JST)) for i in range(12)),
        ("test_user", datetime(2024, 1, 13, 8, 0, 0, tzinfo=JST)),
    )

    view = AchievementView(engine, user_id="test_user")

    texts = [block.to_dict().get("text", {}).get("text", "") for block in view.blocks]
    assert any("[6003] 20番目のお客様" in text for text in texts)  # 13 arrivals so far: 20 is next
    assert not any("[6001]" in text or "[6002]" in text for text in texts)
    assert "次のキリ番まで: あと *7回* (20回目)" in texts


def test_registry_message_lists_arrivals_by_time() -> None:
    """The list follows the arrival times, whatever order the arrivals were given in."""
    engine = compute_in_order(
        ("U_late", datetime(2024, 1, 1, 9, 30, tzinfo=JST)), ("U_early", datetime(2024, 1, 1, 9, 10, tzinfo=JST))
    )

    message = RegistryMessage(engine.arrivals_on(date(2024, 1, 1)))

    assert message.render()[-1]["text"]["text"].splitlines()[1:] == ["*09:10* : <@U_early>", "*09:30* : <@U_late>"]


@mock.patch("hikarie_bot.modals.BADGE_TYPES_TO_CHECK", [1])
def test_attendance_history_counts_the_first_monday_of_the_window() -> None:
    """An arrival on the first day shown (the Monday nine weeks back) is shown as attended."""
    engine = compute_in_order(("test_user", datetime(2024, 1, 15, 9, 0, tzinfo=JST)))
    view = AchievementView(engine, "test_user", jst_datetime=datetime(2024, 3, 20, 15, 0, tzinfo=JST))

    attendance = view._get_attendance_data_for_past_10_weeks()  # noqa: SLF001

    assert min(attendance) == date(2024, 1, 15)
    assert attendance[date(2024, 1, 15)] is True
