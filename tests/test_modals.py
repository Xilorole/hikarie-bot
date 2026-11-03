import json
import re
from datetime import date, datetime, time, timedelta
from textwrap import dedent

from freezegun import freeze_time

from hikarie_bot.constants import ACHIEVED_BADGE_IMAGE_URL, JST, NOT_ACHIEVED_BADGE_IMAGE_URL
from hikarie_bot.db_data.items import ITEMS, TREAT
from hikarie_bot.engine import ArrivalResult, ItemEffect, Outlook, TeamProgress
from hikarie_bot.modals import (
    achievement_view,
    attendance_by_day,
    goals_message,
    initial_message,
    item_picked_text,
    outlook_lines,
    point_get_message,
    registry_message,
    render,
    to_text,
)
from tests.helpers import compute_in_order, only_badge_types


def test_initial_message() -> None:
    """Test the initial message."""
    message = initial_message()
    assert to_text(message) == "高輪に出社してる？"
    assert render(message) == [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "高輪に出社してる？"},
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
                        "text": "ステータス",
                        "type": "plain_text",
                    },
                    "type": "button",
                },
                {
                    "action_id": "PICK_ITEM",
                    "text": {"emoji": True, "text": "今日のアイテム", "type": "plain_text"},
                    "type": "button",
                },
            ],
        },
    ]


def test_registry_message() -> None:
    """Test the second arrived user has lower point."""
    engine = compute_in_order(("test_user_1st", datetime(2024, 1, 1, 6, 0, 0, tzinfo=JST)))
    message = registry_message(engine.arrivals_on(date(2024, 1, 1)))
    assert render(message) == [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "高輪に出社してる？"},
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
                        "text": "ステータス",
                        "type": "plain_text",
                    },
                    "type": "button",
                },
                {
                    "action_id": "PICK_ITEM",
                    "text": {"emoji": True, "text": "今日のアイテム", "type": "plain_text"},
                    "type": "button",
                },
            ],
        },
        {
            "type": "divider",
        },
        {
            "text": {
                "text": "本日の出社ユーザー:\n*06:00* : <@test_user_1st>",
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
    message = registry_message(engine.arrivals_on(date(2024, 1, 1)))
    assert render(message) == [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "高輪に出社してる？"},
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
                        "text": "ステータス",
                        "type": "plain_text",
                    },
                    "type": "button",
                },
                {
                    "action_id": "PICK_ITEM",
                    "text": {"emoji": True, "text": "今日のアイテム", "type": "plain_text"},
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
                        本日の出社ユーザー:
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
    message = point_get_message(engine.results[0])

    assert render(message) == [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*07:00* 最速出社登録しました！\n<@test_user>さんのポイント 0 → *7* (*+7*)",
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
    return render(point_get_message(arrival))


def test_point_get_message_max_level() -> None:
    """Test the point get message says the upper limit is reached."""
    # 1398 -> 1403: the upper limit is reached by this arrival
    message = point_get_after(2, 1398)
    assert message[0]["text"]["text"] == (
        "*07:00* 最速出社登録しました！\n<@test_user>さんのポイント 1398 → *1403* (*+5*) *上限に到達!* :crown: "
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


def cards(view: dict) -> dict[str, dict]:
    """Return the badge cards of a status view by their title."""
    return {block["title"]["text"]: block for block in view["blocks"] if block["type"] == "card"}


@only_badge_types(1, 3)
def test_badge_card_lists_earned_with_first_date_then_unearned() -> None:
    """Earned badges come first as "*name* <score>pt x<count>"; the unearned follow by name only."""
    engine = compute_in_order(*(("test_user", datetime(2024, 1, 1 + i, 7, 0, 0, tzinfo=JST)) for i in range(5)))

    view = achievement_view(engine, user_id="test_user", jst_datetime=datetime(2024, 1, 5, 18, 0, tzinfo=JST))

    by_title = cards(view)
    assert view["title"]["text"] == "ステータス"
    assert set(by_title) == {"*出社登録BOTを初めて利用した*", "*たくさん出社登録をした*"}
    count = by_title["*たくさん出社登録をした*"]
    assert count["subtitle"]["text"] == "1 / 3 獲得・計 3pt"
    assert count["body"]["text"] == "*出社登録ビギナー* 3pt x1\n\n未獲得: 出社登録マスター / 出社登録フリーク"
    assert "icon" not in count
    assert by_title["*出社登録BOTを初めて利用した*"]["body"]["text"] == "*はじめての出社登録* 2pt x1"


@only_badge_types(5)
def test_badge_card_counts_a_badge_earned_again() -> None:
    """A badge earned on several days shows how often it was earned."""
    engine = compute_in_order(*(("test_user", datetime(2024, 1, 1 + i, 8, 0, 0, tzinfo=JST)) for i in range(3)))

    card = cards(achievement_view(engine, user_id="test_user"))["*時間帯による出社登録*"]

    assert card["body"]["text"].startswith("*朝型出社* 3pt x3\n\n未獲得: ")
    assert card["subtitle"]["text"] == "1 / 4 獲得・計 9pt"


@only_badge_types(6)
def test_kiriban_card_lists_only_the_taken_ones_and_the_next() -> None:
    """Kiribans have no fixed total: the card lists the taken ones and how far the next one is."""
    engine = compute_in_order(*(("test_user", datetime(2024, 1, 1 + i, 7, 0, 0, tzinfo=JST)) for i in range(10)))

    card = cards(achievement_view(engine, user_id="test_user"))["*特定の出社登録の回数で付与される*"]

    assert card["subtitle"]["text"] == "1個 獲得・計 4pt"
    assert card["body"]["text"] == "*10番目のお客様* 4pt x1\n\n次のキリ番 11回目まで あと1回"


def test_achievement_view_attendance_history() -> None:
    """Test the attendance history section in the achievement view."""
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
        freeze_time(test_current_date),
        only_badge_types(1),  # Minimize badge data
    ):
        view = achievement_view(engine, user_id=test_user_id)

        # Get the rendered blocks
        rendered_blocks = view["blocks"]

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

    attendance_data = attendance_by_day(engine, test_user_id, current_date.date())

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
        freeze_time(current_date),
        only_badge_types(1),
    ):
        view = achievement_view(engine, user_id=test_user_id)

        # Check that blocks were created
        rendered_blocks = view["blocks"]

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
    """Test that attendance history section is added to the achievement view."""
    test_user_id = "test_user"

    # Insert a simple attendance record
    attendance_date = datetime(2024, 3, 18, 9, 0, 0, tzinfo=JST)  # Monday
    engine = compute_in_order((test_user_id, attendance_date))

    # Mock current date to be in the same timeframe
    current_date = datetime(2024, 3, 20, 15, 0, 0, tzinfo=JST)  # Wednesday

    with (
        freeze_time(current_date),
        only_badge_types(1),
    ):
        view = achievement_view(engine, user_id=test_user_id)

        # Check that blocks were created
        assert len(view["blocks"]) > 0, "View should have blocks"

        # Convert to dict for easier testing
        rendered_blocks = view["blocks"]

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

    attendance_data = attendance_by_day(engine, test_user_id, current_date.date())

    # Basic checks
    assert isinstance(attendance_data, dict), "Should return a dictionary"
    assert len(attendance_data) > 0, "Should have some attendance data"

    # Check that the attendance date is recorded
    assert attendance_data.get(date(2024, 3, 18)) is True, "Should show attendance on 2024-03-18"

    # Check that weekdays only are included
    for date_obj in attendance_data:
        assert date_obj.weekday() < 5, f"Should only include weekdays, got {date_obj.strftime('%A')}"


@only_badge_types(6)
def test_kiriban_card_shows_the_next_kiriban_of_all_arrivals() -> None:
    """Someone without kiribans still sees the next kiriban to be reached by everyone's arrivals."""
    # the 10th and 11th arrivals are kiribans, taken by other users
    engine = compute_in_order(
        *((f"user_{i}", datetime(2024, 1, 1 + i, 7, 0, 0, tzinfo=JST)) for i in range(12)),
        ("test_user", datetime(2024, 1, 13, 8, 0, 0, tzinfo=JST)),
    )

    card = cards(achievement_view(engine, user_id="test_user"))["*特定の出社登録の回数で付与される*"]

    assert card["subtitle"]["text"] == "0個 獲得・計 0pt"
    assert card["body"]["text"] == "次のキリ番 20回目まで あと7回"


def test_registry_message_lists_arrivals_by_time() -> None:
    """The list follows the arrival times, whatever order the arrivals were given in."""
    engine = compute_in_order(
        ("U_late", datetime(2024, 1, 1, 9, 30, tzinfo=JST)), ("U_early", datetime(2024, 1, 1, 9, 10, tzinfo=JST))
    )

    message = registry_message(engine.arrivals_on(date(2024, 1, 1)))

    assert render(message)[-1]["text"]["text"].splitlines()[1:] == ["*09:10* : <@U_early>", "*09:30* : <@U_late>"]


def test_attendance_history_counts_the_first_monday_of_the_window() -> None:
    """An arrival on the first day shown (the Monday nine weeks back) is shown as attended."""
    engine = compute_in_order(("test_user", datetime(2024, 1, 15, 9, 0, tzinfo=JST)))

    attendance = attendance_by_day(engine, "test_user", date(2024, 3, 20))

    assert min(attendance) == date(2024, 1, 15)
    assert attendance[date(2024, 1, 15)] is True


def arrival_with(badge_ids: list[int], rank: int = 2, previous_score: int = 30, score_sum: int = 3) -> ArrivalResult:
    """Return a hand-built arrival (lv2 throughout unless the scores say otherwise)."""
    return ArrivalResult(
        id=100,
        user_id="test_user",
        time=datetime(2026, 11, 10, 9, 0, tzinfo=JST),
        rank=rank,
        badge_ids=badge_ids,
        score_sum=score_sum,
        previous_score=previous_score,
        current_score=previous_score + score_sum,
    )


def test_point_get_message_has_no_goals() -> None:
    """The thread post has no goals (they go to the user alone) and no rank of the day."""
    message = render(point_get_message(arrival_with([501])))

    assert "人目" not in message[0]["text"]["text"]
    assert "つぎのもくひょう" not in json.dumps(message, ensure_ascii=False)


def test_goals_message_lists_what_to_aim_for() -> None:
    """The ephemeral message lists the straight flash, the next count badge and the week; no kiriban, no emoji."""
    outlook = Outlook(
        streak=3, next_count_badge=(302, 4), next_kiriban=(3443, 12), team=TeamProgress(date(2026, 11, 9), 12, 20)
    )

    assert render(goals_message(outlook))[0]["text"]["text"] == (
        "*つぎのもくひょう*\n"
        "ストレートフラッ出社まで あと2日（3日連続）\n"
        "「出社登録マスター」まで あと4回\n"
        "今週のみんなの出社 *12* / 20回。届いたら、そのあとの出社は +1pt"
    )
    assert goals_message(Outlook(streak=1, next_count_badge=None, next_kiriban=None, team=None)) == []


def test_status_streak_before_todays_arrival() -> None:
    """Before arriving today the status shows the streak as still alive and what arriving today makes it."""
    outlook = Outlook(streak=2, next_count_badge=None, next_kiriban=None, team=None, streak_pending=True)

    assert outlook_lines(outlook) == ["ストレートフラッ出社まで あと3日（2日連続）"]


def test_outlook_lines_leave_out_a_streak_with_nothing_to_reach() -> None:
    """A streak shows from its second day (or its first, before today's arrival) until the straight flash."""
    assert outlook_lines(Outlook(streak=1, next_count_badge=None, next_kiriban=None, team=None)) == []
    assert outlook_lines(Outlook(streak=7, next_count_badge=None, next_kiriban=None, team=None)) == []
    pending = Outlook(streak=1, next_count_badge=None, next_kiriban=None, team=None, streak_pending=True)
    assert outlook_lines(pending) == ["ストレートフラッ出社まで あと4日（1日連続）"]


def test_daily_post_shows_the_team_progress() -> None:
    """The morning post and the updated post end with the week's progress; without it they are unchanged."""
    team = TeamProgress(date(2026, 11, 9), 21, 20)
    text = "今週のみんなの出社 *21* / 20回。達成したので、今週これからの出社は +1pt"

    assert render(initial_message(team))[-1] == {
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": text}],
    }
    assert render(registry_message([], team))[-1]["elements"][0]["text"] == text
    assert len(initial_message()) == 2


def test_item_names_are_shown_without_emoji() -> None:
    """The breakdown and the pick announcement name the item without its emoji."""
    arrival = arrival_with([501])
    arrival.item_effects = [ItemEffect(TREAT, 1, giver="U2")]
    text = render(point_get_message(arrival))[2]["elements"][0]["text"]

    assert f" - {ITEMS[TREAT].name} (<@U2>さんから):*+1pt*" in text
    assert ITEMS[TREAT].emoji not in text
    assert ITEMS[TREAT].emoji not in item_picked_text("U1", ITEMS[TREAT])


def test_status_top_is_one_list_with_the_goals_indented() -> None:
    """Level, points and the goals heading are list items; the goals sit one level below, the count in bold."""
    engine = compute_in_order(("test_user", datetime(2026, 11, 9, 9, 0, tzinfo=JST)))

    view = achievement_view(engine, user_id="test_user", jst_datetime=datetime(2026, 11, 9, 18, 0, tzinfo=JST))

    top = view["blocks"][0]
    assert top["type"] == "rich_text"
    items = [(item["indent"], item["elements"][0]["elements"]) for item in top["elements"]]
    assert [indent for indent, _ in items] == [0, 0, 0, 1, 1]
    assert items[2][1] == [{"type": "text", "text": "つぎのもくひょう", "style": {"bold": True}}]
    team = items[4][1]
    assert team[:3] == [
        {"type": "text", "text": "今週のみんなの出社 "},
        {"type": "text", "text": "1", "style": {"bold": True}},
        {"type": "text", "text": " / 20回。届いたら、そのあとの出社は +1pt"},
    ]


def test_every_badge_card_fits_slack_body_limit() -> None:
    """With years of arrivals the oldest earned badges fold into one line; every body stays within 200 characters."""
    arrivals = [
        (user, datetime.combine(day, time(9 + index % 3, index * 11 % 60), tzinfo=JST))
        for day in (date(2022, 6, 1) + timedelta(days=offset) for offset in range(1600))
        if day.weekday() < 5
        for index, user in enumerate(("U0", "U1", "U2"))
    ]
    engine = compute_in_order(*arrivals)

    view = achievement_view(engine, user_id="U0", jst_datetime=datetime(2026, 11, 3, 18, tzinfo=JST))

    bodies = {block["title"]["text"]: block["body"]["text"] for block in view["blocks"] if block["type"] == "card"}
    assert all(len(body) <= 200 for body in bodies.values())
    kiriban = bodies["*特定の出社登録の回数で付与される*"]
    earned = kiriban.split("\n\n")[0].split("\n")
    assert re.fullmatch(r"ほか\d+個（計 \d+pt）", earned[-1])  # the folded older ones come last
    numbers = [int(re.match(r"\*(\d+)番目", line).group(1)) for line in earned[:-1]]
    assert numbers == sorted(numbers, reverse=True)  # newest first
    assert kiriban.endswith("回")  # the next kiriban always shows
