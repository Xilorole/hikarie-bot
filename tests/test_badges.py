"""Badge rules, run on the engine with arrivals as (user, JST time) and expectations as (badge IDs, user, day)."""

from datetime import date, datetime

import pytest

from hikarie_bot.constants import JST
from hikarie_bot.db_data import Badges
from hikarie_bot.db_data.badges import KIRIBANS, kiriban_score
from tests.helpers import compute_in_order

BADGE_TYPE = {badge.id: badge.badge_type_id for badge in Badges}

# Shared by the welcome and fastest-arrival rules:
# - "user" arrives for the first time on a day of their own
# - "already_arrived" came before 01-03 and is the fastest on that day
# - "not_fastest" arrives for the first time an hour after "already_arrived" on 01-03
FIRST_AND_REPEAT = [
    ("user", "2024-01-01 06:00:00"),
    ("already_arrived", "2024-01-02 06:00:00"),
    ("already_arrived", "2024-01-03 06:00:00"),
    ("not_fastest", "2024-01-03 07:00:00"),
]


def at(user: str, *times: str) -> list[tuple[str, str]]:
    """Return one arrival of the user per time."""
    return [(user, time) for time in times]


@pytest.mark.parametrize(
    ("types", "arrivals", "checks"),
    [
        pytest.param(
            {1},
            FIRST_AND_REPEAT,
            [
                ([101], "user", "2024-01-01"),
                ([], "already_arrived", "2024-01-03"),
                ([101], "not_fastest", "2024-01-03"),
                ([], "not_arrived", "2024-01-03"),
            ],
            id="welcome",
        ),
        pytest.param(
            {2},
            FIRST_AND_REPEAT,
            [
                ([201], "user", "2024-01-01"),
                ([201], "already_arrived", "2024-01-03"),
                ([], "not_fastest", "2024-01-03"),
                ([], "not_arrived", "2024-01-03"),
            ],
            id="fastest_arrival",
        ),
        pytest.param(
            {3},
            # five days in a row for "user", four for "user_4"
            [("user", f"2020-01-0{day} 06:00:00") for day in range(1, 6)]
            + [("user_4", f"2020-01-0{day} 06:00:00") for day in range(1, 5)],
            [
                ([], "user", "2020-01-04"),
                ([301], "user", "2020-01-05"),  # the fifth arrival
                ([], "user", "2020-01-06"),
                ([], "user_4", "2020-01-04"),
                ([], "user_4", "2020-01-05"),
            ],
            id="arrival_count",
        ),
        pytest.param(
            {4},
            [
                # 1. five business days in a row at the same hour: level 1 on the fifth
                *at("user_1", *(f"2024-04-{day} 07:00:00" for day in (22, 23, 24, 25, 26))),
                # 2. the streak skips weekends and holidays
                *at("user_2", "2024-04-26 07:00:00", "2024-04-30 07:00:00", "2024-05-01 07:00:00"),
                *at("user_2", "2024-05-02 07:00:00", "2024-05-07 07:00:00"),
                # 3. a missed business day breaks it
                *at("user_3", "2024-04-22 07:00:00", "2024-04-23 07:00:00", "2024-04-24 07:00:00"),
                *at("user_3", "2024-04-25 07:00:00", "2024-04-30 07:00:00"),
                # 4. a different hour every day: level 2 as well
                *at("user_4", "2024-04-22 07:00:00", "2024-04-23 08:00:00", "2024-04-24 10:00:00"),
                *at("user_4", "2024-04-25 12:00:00", "2024-04-26 14:00:00"),
                # 5. consecutive hours every day: all three levels
                *at("user_5", "2024-04-22 07:00:00", "2024-04-23 08:00:00", "2024-04-24 09:00:00"),
                *at("user_5", "2024-04-25 10:00:00", "2024-04-26 11:00:00"),
                # 6. the levels on different days
                *at("user_6", "2024-04-22 07:00:00", "2024-04-23 07:00:00", "2024-04-24 08:00:00"),
                *at("user_6", "2024-04-25 09:00:00", "2024-04-26 10:00:00", "2024-04-30 12:00:00"),
                *at("user_6", "2024-05-01 11:00:00"),
                # 7. level 1 again only after a cooldown of five days
                *at("user_7", "2024-04-22 07:00:00", "2024-04-23 07:00:00", "2024-04-24 07:00:00"),
                *at("user_7", "2024-04-25 07:00:00", "2024-04-26 07:00:00", "2024-04-30 07:00:00"),
                *at("user_7", "2024-05-01 07:00:00", "2024-05-02 07:00:00", "2024-05-07 07:00:00"),
                *at("user_7", "2024-05-08 07:00:00"),
            ],
            [
                ([], "user_1", "2024-04-25"),
                ([401], "user_1", "2024-04-26"),
                ([], "user_1", "2024-05-01"),
                ([], "user_2", "2024-05-02"),
                ([401], "user_2", "2024-05-07"),
                ([], "user_2", "2024-05-08"),
                ([], "user_3", "2024-04-26"),
                ([], "user_3", "2024-04-30"),
                ([], "user_3", "2024-05-01"),
                ([], "user_4", "2024-04-25"),
                ([401, 402], "user_4", "2024-04-26"),
                ([], "user_4", "2024-04-27"),
                ([], "user_5", "2024-04-25"),
                ([401, 402, 403], "user_5", "2024-04-26"),
                ([], "user_5", "2024-04-27"),
                ([], "user_6", "2024-04-25"),
                ([401], "user_6", "2024-04-26"),
                ([402], "user_6", "2024-04-30"),
                ([403], "user_6", "2024-05-01"),
                ([], "user_7", "2024-04-25"),
                ([401], "user_7", "2024-04-26"),
                ([], "user_7", "2024-05-07"),
                ([401], "user_7", "2024-05-08"),
            ],
            id="straight_flash",
        ),
        pytest.param(
            {5},
            [
                ("user_1", "2024-04-22 06:00:00"),  # the earliest morning time
                ("user_2", "2024-04-22 09:00:00"),
                ("user_3", "2024-04-22 11:00:00"),
                ("user_4", "2024-04-22 05:59:59"),  # before the first window
                ("user_5", "2024-04-22 18:00:00"),  # after the last window
                ("user_6", "2024-04-22 07:00:00"),
            ],
            [
                ([504], "user_1", "2024-04-22"),
                ([502], "user_2", "2024-04-22"),
                ([503], "user_3", "2024-04-22"),
                ([], "user_4", "2024-04-22"),
                ([], "user_5", "2024-04-22"),
                ([501], "user_6", "2024-04-22"),
            ],
            id="time_window",
        ),
        pytest.param(
            {6},
            # nine arrivals on 01-01 and the tenth, a kiriban, the next day
            [(f"user_{i}", f"2020-01-01 06:00:0{i}") for i in range(9)] + [("user_kiriban_10", "2020-01-02 06:00:00")],
            [
                ([], "user_0", "2020-01-01"),
                ([6001], "user_kiriban_10", "2020-01-02"),
            ],
            id="kiriban",
        ),
        pytest.param(
            {7},
            [
                # everyone arrives first on 2024-01-01
                *at("user_1", "2024-01-01 07:00:01", "2024-01-16 06:00:01"),  # 15 days later
                *at("user_2", "2024-01-01 07:00:02", "2024-02-02 06:00:02"),  # a month later
                *at("user_3", "2024-01-01 07:00:03", "2024-03-02 06:00:03"),  # two months later
                *at("user_4", "2024-01-01 07:00:04", "2024-07-02 06:00:04"),  # half a year later
                *at("user_5", "2024-01-01 07:00:05", "2024-01-15 06:00:05"),  # 14 days later: not enough
            ],
            [
                ([701], "user_1", "2024-01-16"),
                ([702], "user_2", "2024-02-02"),
                ([703], "user_3", "2024-03-02"),
                ([704], "user_4", "2024-07-02"),
                ([], "user_5", "2024-01-15"),
            ],
            id="long_time_no_see",
        ),
        pytest.param(
            {8},
            [
                # four arrivals in the same minute, then two in the next one
                ("user_1", "2024-01-01 07:00:00"),
                ("user_2", "2024-01-01 07:00:00"),
                ("user_3", "2024-01-01 07:00:00"),
                ("user_4", "2024-01-01 07:00:00"),
                ("user_5", "2024-01-01 07:01:00"),
                ("user_6", "2024-01-01 07:01:00"),
            ],
            [
                ([], "user_1", "2024-01-01"),
                ([801], "user_2", "2024-01-01"),
                ([802], "user_3", "2024-01-01"),
                ([803], "user_4", "2024-01-01"),
                ([], "user_5", "2024-01-01"),
                ([801], "user_6", "2024-01-01"),
            ],
            id="lucky_you_guys",
        ),
        pytest.param(
            {1, 2, 3},
            [
                # A is always the fastest and reaches five arrivals on 01-05
                *at("user_A", "2024-01-01 06:00:00", "2024-01-02 06:00:00", "2024-01-03 06:00:00"),
                *at("user_A", "2024-01-04 06:00:00", "2024-01-05 06:00:00", "2024-01-06 07:00:00"),
                # B starts on 01-04 and is the fastest on 01-06
                *at("user_B", "2024-01-04 07:00:00", "2024-01-05 07:00:00", "2024-01-06 06:00:00"),
            ],
            [
                ([101, 201], "user_A", "2024-01-01"),
                ([201, 301], "user_A", "2024-01-05"),
                ([], "user_A", "2024-01-06"),
                ([101], "user_B", "2024-01-04"),
                ([201], "user_B", "2024-01-06"),
            ],
            id="welcome_fastest_arrival_count",
        ),
        pytest.param(
            {15},
            [
                # user_1 starts on 12-09, the first day the badge applies, so the window ends on 12-23
                *at("user_1", "2024-12-09 07:00:00", "2024-12-23 07:00:00", "2024-12-24 07:00:00"),
                # user_2 arrives on 12-08, before the badge applies: the window starts on 12-10
                *at("user_2", "2024-12-08 07:00:00", "2024-12-10 07:00:00", "2024-12-24 07:00:00"),
                *at("user_2", "2024-12-25 07:00:00"),
            ],
            [
                ([1501], "user_1", "2024-12-09"),
                ([1501], "user_1", "2024-12-23"),
                ([], "user_1", "2024-12-24"),
                ([], "user_2", "2024-12-08"),
                ([1501], "user_2", "2024-12-10"),
                ([1501], "user_2", "2024-12-24"),
                ([], "user_2", "2024-12-25"),
            ],
            id="start_dash",
        ),
        pytest.param(
            {16},
            [
                ("user_1", "2024-12-27 07:00:00"),
                ("user_2", "2025-01-06 07:00:00"),
                ("user_3", "2024-12-26 07:00:00"),  # the day before
                ("user_4", "2025-01-05 07:00:00"),  # the day before
            ],
            [
                ([1601], "user_1", "2024-12-27"),
                ([1602], "user_2", "2025-01-06"),
                ([], "user_3", "2024-12-26"),
                ([], "user_4", "2025-01-05"),
            ],
            id="specific_day",
        ),
        pytest.param(
            {17},
            [
                # user_1: Christmas, the end and the start of the fiscal year; the last two once a year
                *at("user_1", "2024-12-25 07:00:00", "2025-03-25 07:00:00", "2025-03-31 07:00:00"),
                *at("user_1", "2025-04-01 07:00:00", "2025-04-08 07:00:00", "2026-12-25 07:00:00"),
                *at("user_1", "2026-03-25 07:00:00", "2026-04-01 07:00:00"),
                # user_2: the days around Christmas and the year end window, then 03-31 as the first arrival in it
                *at("user_2", "2025-12-24 07:00:00", "2025-12-26 07:00:00", "2025-03-24 07:00:00"),
                *at("user_2", "2025-03-31 07:00:00", "2025-04-08 07:00:00"),
                # user_3: Golden Week (04-29 to 05-05)
                *at("user_3", "2025-04-28 07:00:00", "2025-04-30 07:00:00", "2025-05-01 07:00:00"),
            ],
            [
                ([1701], "user_1", "2024-12-25"),
                ([1702], "user_1", "2025-03-25"),
                ([], "user_1", "2025-03-31"),  # the second arrival in the window
                ([1703], "user_1", "2025-04-01"),
                ([], "user_1", "2025-04-08"),
                ([1701], "user_1", "2026-12-25"),
                ([1702], "user_1", "2026-03-25"),
                ([1703], "user_1", "2026-04-01"),
                ([], "user_2", "2025-12-24"),
                ([], "user_2", "2025-12-26"),
                ([], "user_2", "2025-03-24"),
                ([1702], "user_2", "2025-03-31"),
                ([], "user_2", "2025-04-08"),
                ([], "user_3", "2025-04-28"),
                ([1704], "user_3", "2025-04-30"),
                ([1704], "user_3", "2025-05-01"),
            ],
            id="yearly_specific_day",
        ),
        pytest.param(
            {18},
            [
                ("user_1", "2025-12-27 07:08:00"),  # adjacent digits
                ("user_2", "2025-12-27 07:07:00"),  # same digits
                ("user_3", "2025-12-27 07:06:00"),
                ("user_4", "2025-12-27 12:33:00"),
                ("user_5", "2025-12-27 12:34:00"),  # consecutive digits
                ("user_6", "2025-12-27 11:11:00"),
                ("user_7", "2025-12-27 11:12:00"),
                ("user_8", "2025-12-27 11:10:00"),
            ],
            [
                ([1801], "user_1", "2025-12-27"),
                ([1802], "user_2", "2025-12-27"),
                ([1801], "user_3", "2025-12-27"),
                ([], "user_4", "2025-12-27"),
                ([1803], "user_5", "2025-12-27"),
                ([1804], "user_6", "2025-12-27"),
                ([1801], "user_7", "2025-12-27"),
                ([1801], "user_8", "2025-12-27"),
            ],
            id="specific_time",
        ),
        pytest.param(
            {18},
            [
                ("user_1", "2025-12-27 11:22:00"),
                ("user_2", "2025-12-27 11:29:00"),
                ("user_3", "2025-12-27 09:10:00"),
                ("user_4", "2025-12-27 09:11:00"),  # the neighbours of those times earn nothing
                ("user_5", "2025-12-27 11:21:00"),
                ("user_6", "2025-12-27 11:30:00"),
            ],
            [
                ([1805], "user_1", "2025-12-27"),
                ([1806], "user_2", "2025-12-27"),
                ([1807], "user_3", "2025-12-27"),
                ([], "user_4", "2025-12-27"),
                ([], "user_5", "2025-12-27"),
                ([], "user_6", "2025-12-27"),
            ],
            id="specific_time_added_badges",
        ),
        pytest.param(
            {19},
            [
                ("user_first_takanawa", "2026-01-19 10:00:00"),
                *at("user_second_takanawa", "2026-01-19 10:00:00", "2026-01-20 10:00:00"),
                ("user_before_move", "2026-01-18 10:00:00"),
                ("user_on_move_day", "2026-01-19 09:00:00"),
            ],
            [
                ([1901], "user_first_takanawa", "2026-01-19"),
                ([], "user_second_takanawa", "2026-01-20"),  # not the first arrival at the new office
                ([], "user_before_move", "2026-01-18"),
                ([1901], "user_on_move_day", "2026-01-19"),
            ],
            id="takanawa_welcome",
        ),
    ],
)
def test_badge_rule(types: set[int], arrivals: list[tuple[str, str]], checks: list[tuple[list[int], str, str]]) -> None:
    """Each user's arrival on the day earns exactly the expected badges of the given types."""
    engine = compute_in_order(*((user, datetime.fromisoformat(time).replace(tzinfo=JST)) for user, time in arrivals))

    for expected, user, day in checks:
        arrival = engine.arrival_of(user, date.fromisoformat(day))
        earned = [badge_id for badge_id in arrival.badge_ids if BADGE_TYPE[badge_id] in types] if arrival else []
        assert earned == expected, f"{user} on {day}"


@pytest.mark.parametrize(
    ("number", "score"),
    [
        (10, 4),  # power of ten multiple
        (11, 4),  # repetitive
        (121, 5),  # palindrome
        (123, 7),  # sequential, ascending
        (4321, 7),  # sequential, descending
        (100, 6),
        (1111, 8),  # repetitive, not a palindrome or a power of ten
        (5000, 8),
        (1, None),
        (12, None),
        (1213, None),
    ],
)
def test_kiriban_score(number: int, score: int | None) -> None:
    """Kiriban numbers score by their kind, the first matching kind winning."""
    assert kiriban_score(number) == score


def test_kiriban_badges() -> None:
    """Kiriban badges are the kiribans below 10000, numbered from 6001 in order."""
    assert len(KIRIBANS) == 244
    assert [(k.id, k.number, k.score) for k in (KIRIBANS[0], KIRIBANS[22], KIRIBANS[-1])] == [
        (6001, 10, 4),
        (6023, 123, 7),
        (6244, 9999, 8),
    ]
