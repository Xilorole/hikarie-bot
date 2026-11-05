import json
import re
from datetime import date, datetime, timedelta
from textwrap import dedent

from freezegun import freeze_time

from hikarie_bot.constants import ACHIEVED_BADGE_IMAGE_URL, JST, NOT_ACHIEVED_BADGE_IMAGE_URL
from hikarie_bot.db_data.items import ITEMS, TREAT
from hikarie_bot.engine import ArrivalResult, ItemEffect, Outlook, TeamProgress
from hikarie_bot.home import home_view
from hikarie_bot.modals import (
    arrival_summary,
    attendance_by_day,
    home_url,
    initial_message,
    item_picked_text,
    item_review_view,
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
                    "text": "かたがき: *かけだしのかいしゃいん* (Lv1)\n"
                    "つぎのレベルまで: *13pt*\n"
                    "しんこうど: `████░░░░░░` | * 35%* (*+35%*)\n"
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
        "かたがき: *でんせつのかいしゃいん* (Lv12)\nつぎのレベルまで: *上限に到達*\nしんこうど: `██████████` | *100%*\n"
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
    assert "しんこうど: `░░░░░░░░░░` | *  0%* (*+22%*)\n" in message[2]["elements"][0]["text"]


def test_my_page_attendance_history() -> None:
    """Test the attendance history section on my page."""
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
        view = home_view(engine, test_user_id, datetime.now(JST))

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
        view = home_view(engine, test_user_id, datetime.now(JST))

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


def test_my_page_attendance_history_simple() -> None:
    """Test that the attendance history section is on my page."""
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
        view = home_view(engine, test_user_id, datetime.now(JST))

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
    """The thread post has no goals (they are on my page) and no rank of the day."""
    message = render(point_get_message(arrival_with([501])))

    assert "人目" not in message[0]["text"]["text"]
    assert "つぎのもくひょう" not in json.dumps(message, ensure_ascii=False)


def test_arrival_summary_has_no_goals() -> None:
    """The arrival's modal says when it was recorded, for how many points and where; the goals are on my page."""
    assert arrival_summary(arrival_with([501]), "C0OUT") == (
        f"*{arrival_with([501]).time:%H:%M}* に出社登録しました（+{arrival_with([501]).score_sum}pt）。"
        "<#C0OUT> の今日の投稿のスレッドに記録しています"
    )


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


def test_the_pick_announcement_leaves_out_the_effect() -> None:
    """The thread only says who picked which item: the effect is for the modals and the collection."""
    assert item_picked_text("U1", ITEMS[TREAT]) == f"<@U1>さんが {ITEMS[TREAT].name} を獲得しました"


def test_daily_post_links_to_my_page_only_with_both_ids() -> None:
    """With the workspace and app IDs the daily post has a button opening the Home; without them it has none."""
    url = home_url("T0", "A0")

    assert url == "slack://app?team=T0&id=A0&tab=home"
    assert home_url("T0", "") is None
    for message in (initial_message(None, url), registry_message([], None, url)):
        buttons = render(message)[1]["elements"]
        assert {"text": "マイページを開く", "url": url, "action_id": "OPEN_MY_PAGE"}.items() <= {
            **buttons[1],
            "text": buttons[1]["text"]["text"],
        }.items()
    assert [button["action_id"] for button in render(initial_message())[1]["elements"]] == [
        "FASTEST_ARRIVAL",
        "PICK_ITEM",
    ]


def test_the_picked_offer_comes_first_and_the_others_are_dimmed() -> None:
    """After a pick the picked item leads as a section; the others follow, each as two small context blocks."""
    offered = list(ITEMS.values())[:3]

    view = item_review_view(offered, "notice", picked_item_id=offered[2].id)

    sections = [block for block in view["blocks"] if "accessory" in block]
    assert [block["text"]["text"].split("\n")[0] for block in sections] == [f"*{offered[2].name}*"]
    names = [
        block["elements"][1]["text"]
        for block in view["blocks"]
        if block["type"] == "context" and block["elements"][0]["type"] == "image"
    ]
    assert names == [f"*{offered[0].name}*", f"*{offered[1].name}*"]
