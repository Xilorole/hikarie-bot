"""Badge checking tests, written as declarative scenarios.

Each scenario lists the arrivals to register and, for a given date and user,
the badge ids that are expected. Adding a new case means adding data here --
no new boilerplate.
"""

from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from tests.helpers import (
    Arrival,
    BadgeScenario,
    Expectation,
    daily,
    run_badge_scenario,
    to_datetime,
)

# badge ids per badge type, kept here so scenarios stay readable
WELCOME = 101
FASTEST = 201
COUNT_5, COUNT_20, COUNT_100 = 301, 302, 303
STRAIGHT, ROYAL, ULTRA_ROYAL = 401, 402, 403
LATE, DAYTIME, MORNING = 503, 502, 501
KIRIBAN_100 = 601
NO_SEE_2W, NO_SEE_1M, NO_SEE_2M, NO_SEE_6M = 701, 702, 703, 704
LUCKY_2, LUCKY_3, LUCKY_4 = 801, 802, 803

# shared arrival pattern for the welcome / fastest_arrival scenarios:
#   user            2024-01-01 06:00 -> fastest and first ever
#   already_arrived 2024-01-02 06:00, 2024-01-03 06:00 -> fastest, not first
#   not_fastest     2024-01-03 07:00 -> first ever, not fastest
_INTRO_ARRIVALS = [
    Arrival("2024-01-01 06:00:00", "user"),
    Arrival("2024-01-02 06:00:00", "already_arrived"),
    Arrival("2024-01-03 06:00:00", "already_arrived"),
    Arrival("2024-01-03 07:00:00", "not_fastest"),
]

SCENARIOS = [
    BadgeScenario(
        id="id1_welcome",
        badge_types=[1],
        check="check_welcome",
        arrivals=_INTRO_ARRIVALS,
        expectations=[
            Expectation("2024-01-01", "user", [WELCOME]),
            Expectation("2024-01-03", "already_arrived", []),
            Expectation("2024-01-03", "not_fastest", [WELCOME]),
            Expectation("2024-01-03", "not_arrived", []),
        ],
        also_check_all=True,
    ),
    BadgeScenario(
        id="id2_fastest_arrival",
        badge_types=[2],
        check="check_fastest_arrival",
        arrivals=_INTRO_ARRIVALS,
        expectations=[
            Expectation("2024-01-01", "user", [FASTEST]),
            Expectation("2024-01-03", "already_arrived", [FASTEST]),
            Expectation("2024-01-03", "not_fastest", []),
            Expectation("2024-01-03", "not_arrived", []),
        ],
    ),
    BadgeScenario(
        # 5 / 20 / 100 arrivals unlock lv1 / lv2 / lv3 on that very day only
        id="id3_arrival_count",
        badge_types=[3],
        check="check_arrival_count",
        arrivals=[
            *daily("user", "2020-01-01 06:00:00", days=100),
            *daily("user_4", "2020-01-01 06:00:00", days=4),
        ],
        expectations=[
            Expectation("2020-01-04", "user", []),
            Expectation("2020-01-05", "user", [COUNT_5]),
            Expectation("2020-01-06", "user", []),
            Expectation("2020-01-19", "user", []),
            Expectation("2020-01-20", "user", [COUNT_20]),
            Expectation("2020-01-21", "user", []),
            Expectation("2020-04-08", "user", []),
            Expectation("2020-04-09", "user", [COUNT_100]),
            Expectation("2020-04-10", "user", []),
            # never reaches 5 arrivals
            Expectation("2020-01-04", "user_4", []),
            Expectation("2020-01-05", "user_4", []),
        ],
    ),
    BadgeScenario(
        id="id4_straight_flash",
        badge_types=[4],
        check="check_straight_flash",
        arrivals=[
            # 1. plain 5 business days in a row
            Arrival("2024-04-22 07:00:00", "user_1"),
            Arrival("2024-04-23 07:00:00", "user_1"),
            Arrival("2024-04-24 07:00:00", "user_1"),
            Arrival("2024-04-25 07:00:00", "user_1"),
            Arrival("2024-04-26 07:00:00", "user_1"),
            # 2. 5 business days in a row spanning holidays
            Arrival("2024-04-26 07:00:00", "user_2"),
            Arrival("2024-04-30 07:00:00", "user_2"),
            Arrival("2024-05-01 07:00:00", "user_2"),
            Arrival("2024-05-02 07:00:00", "user_2"),
            Arrival("2024-05-07 07:00:00", "user_2"),
            # 3. broken streak
            Arrival("2024-04-22 07:00:00", "user_3"),
            Arrival("2024-04-23 07:00:00", "user_3"),
            Arrival("2024-04-24 07:00:00", "user_3"),
            Arrival("2024-04-25 07:00:00", "user_3"),
            Arrival("2024-04-30 07:00:00", "user_3"),
            # 4. different time windows -> royal
            Arrival("2024-04-22 07:00:00", "user_4"),
            Arrival("2024-04-23 08:00:00", "user_4"),
            Arrival("2024-04-24 10:00:00", "user_4"),
            Arrival("2024-04-25 12:00:00", "user_4"),
            Arrival("2024-04-26 14:00:00", "user_4"),
            # 5. consecutive time windows -> ultra royal
            Arrival("2024-04-22 07:00:00", "user_5"),
            Arrival("2024-04-23 08:00:00", "user_5"),
            Arrival("2024-04-24 09:00:00", "user_5"),
            Arrival("2024-04-25 10:00:00", "user_5"),
            Arrival("2024-04-26 11:00:00", "user_5"),
            # 6. acquires every level one after another
            Arrival("2024-04-22 07:00:00", "user_6"),
            Arrival("2024-04-23 07:00:00", "user_6"),
            Arrival("2024-04-24 08:00:00", "user_6"),
            Arrival("2024-04-25 09:00:00", "user_6"),
            Arrival("2024-04-26 10:00:00", "user_6"),
            Arrival("2024-04-30 12:00:00", "user_6"),
            Arrival("2024-05-01 11:00:00", "user_6"),
            # 7. cooltime is 5 days
            Arrival("2024-04-22 07:00:00", "user_7"),
            Arrival("2024-04-23 07:00:00", "user_7"),
            Arrival("2024-04-24 07:00:00", "user_7"),
            Arrival("2024-04-25 07:00:00", "user_7"),
            Arrival("2024-04-26 07:00:00", "user_7"),
            Arrival("2024-04-30 07:00:00", "user_7"),
            Arrival("2024-05-01 07:00:00", "user_7"),
            Arrival("2024-05-02 07:00:00", "user_7"),
            Arrival("2024-05-07 07:00:00", "user_7"),
            Arrival("2024-05-08 07:00:00", "user_7"),
        ],
        expectations=[
            Expectation("2024-04-25", "user_1", []),
            Expectation("2024-04-26", "user_1", [STRAIGHT]),
            Expectation("2024-05-01", "user_1", []),
            Expectation("2024-05-02", "user_2", []),
            Expectation("2024-05-07", "user_2", [STRAIGHT]),
            Expectation("2024-05-08", "user_2", []),
            Expectation("2024-04-26", "user_3", []),
            Expectation("2024-04-30", "user_3", []),
            Expectation("2024-05-01", "user_3", []),
            Expectation("2024-04-25", "user_4", []),
            Expectation("2024-04-26", "user_4", [STRAIGHT, ROYAL]),
            Expectation("2024-04-27", "user_4", []),
            Expectation("2024-04-25", "user_5", []),
            Expectation("2024-04-26", "user_5", [STRAIGHT, ROYAL, ULTRA_ROYAL]),
            Expectation("2024-04-27", "user_5", []),
            Expectation("2024-04-25", "user_6", []),
            Expectation("2024-04-26", "user_6", [STRAIGHT]),
            Expectation("2024-04-30", "user_6", [ROYAL]),
            Expectation("2024-05-01", "user_6", [ULTRA_ROYAL]),
            Expectation("2024-04-25", "user_7", []),
            Expectation("2024-04-26", "user_7", [STRAIGHT]),
            Expectation("2024-05-07", "user_7", []),
            Expectation("2024-05-08", "user_7", [STRAIGHT]),
        ],
    ),
    BadgeScenario(
        # 6-9h -> morning, 9-11h -> daytime, 11h- -> late, outside -> nothing
        id="id5_time_window",
        badge_types=[5],
        check="check_time_window",
        arrivals=[
            Arrival("2024-04-22 06:00:00", "user_1"),
            Arrival("2024-04-22 09:00:00", "user_2"),
            Arrival("2024-04-22 11:00:00", "user_3"),
            Arrival("2024-04-22 05:59:59", "user_4"),
            Arrival("2024-04-22 18:00:00", "user_5"),
        ],
        expectations=[
            Expectation("2024-04-22", "user_1", [MORNING]),
            Expectation("2024-04-22", "user_2", [DAYTIME]),
            Expectation("2024-04-22", "user_3", [LATE]),
            Expectation("2024-04-22", "user_4", []),
            Expectation("2024-04-22", "user_5", []),
        ],
    ),
    BadgeScenario(
        # the 100th arrival overall gets the kiriban badge
        id="id6_kiriban",
        badge_types=[6],
        check="check_kiriban",
        arrivals=[
            *[
                Arrival(
                    to_datetime("2020-01-01 06:00:00") + timedelta(seconds=i),
                    f"user_{i}",
                )
                for i in range(99)
            ],
            Arrival("2020-01-02 06:00:00", "user_kiriban_100"),
        ],
        expectations=[
            Expectation("2020-01-01", "user_0", []),
            Expectation("2020-01-02", "user_kiriban_100", [KIRIBAN_100]),
        ],
    ),
    BadgeScenario(
        # every user first arrived on 2024-01-01, then came back after a break
        id="id7_long_time_no_see",
        badge_types=[7],
        check="check_long_time_no_see",
        arrivals=[
            Arrival("2024-01-01 07:00:01", "user_1"),
            Arrival("2024-01-01 07:00:02", "user_2"),
            Arrival("2024-01-01 07:00:03", "user_3"),
            Arrival("2024-01-01 07:00:04", "user_4"),
            Arrival("2024-01-01 07:00:05", "user_5"),
            Arrival("2024-01-16 06:00:01", "user_1"),  # 15 days
            Arrival("2024-02-02 06:00:02", "user_2"),  # 1 month
            Arrival("2024-03-02 06:00:03", "user_3"),  # 2 months
            Arrival("2024-07-02 06:00:04", "user_4"),  # 6 months
            Arrival("2024-01-15 06:00:05", "user_5"),  # 14 days: too short
        ],
        expectations=[
            Expectation("2024-01-16", "user_1", [NO_SEE_2W]),
            Expectation("2024-02-02", "user_2", [NO_SEE_1M]),
            Expectation("2024-03-02", "user_3", [NO_SEE_2M]),
            Expectation("2024-07-02", "user_4", [NO_SEE_6M]),
            Expectation("2024-01-15", "user_5", []),
        ],
    ),
    BadgeScenario(
        # the 2nd/3rd/4th user of the same minute gets lv1/lv2/lv3
        id="id8_lucky_you_guys",
        badge_types=[8],
        check="check_lucky_you_guys",
        arrivals=[
            Arrival("2024-01-01 07:00:00", "user_1"),
            Arrival("2024-01-01 07:00:00", "user_2"),
            Arrival("2024-01-01 07:00:00", "user_3"),
            Arrival("2024-01-01 07:00:00", "user_4"),
            Arrival("2024-01-01 07:01:00", "user_5"),
            Arrival("2024-01-01 07:01:00", "user_6"),
        ],
        expectations=[
            Expectation("2024-01-01", "user_1", []),
            Expectation("2024-01-01", "user_2", [LUCKY_2]),
            Expectation("2024-01-01", "user_3", [LUCKY_3]),
            Expectation("2024-01-01", "user_4", [LUCKY_4]),
            Expectation("2024-01-01", "user_5", []),
            Expectation("2024-01-01", "user_6", [LUCKY_2]),
        ],
    ),
    BadgeScenario(
        # A always comes fastest from 1/1 and hits 5 arrivals on 1/5
        # B starts on 1/4 and takes the fastest arrival on 1/6
        id="complex_id1_id2_id3",
        badge_types=[1, 2, 3],
        check="check",
        arrivals=[
            *daily("user_A", "2024-01-01 06:00:00", days=5),
            Arrival("2024-01-06 07:00:00", "user_A"),
            Arrival("2024-01-04 07:00:00", "user_B"),
            Arrival("2024-01-05 07:00:00", "user_B"),
            Arrival("2024-01-06 06:00:00", "user_B"),
        ],
        expectations=[
            Expectation("2024-01-01", "user_A", [WELCOME, FASTEST]),
            Expectation("2024-01-05", "user_A", [FASTEST, COUNT_5]),
            Expectation("2024-01-06", "user_A", []),
            Expectation("2024-01-04", "user_B", [WELCOME]),
            Expectation("2024-01-06", "user_B", [FASTEST]),
        ],
    ),
]


@pytest.mark.parametrize(
    "scenario", SCENARIOS, ids=[scenario.id for scenario in SCENARIOS]
)
def test_badge_checker(session: Session, scenario: BadgeScenario) -> None:
    """Run every declarative badge scenario."""
    run_badge_scenario(session, scenario)


def test_daily_helper_supports_custom_step() -> None:
    """The arrival helper can step by something other than a day."""
    arrivals = daily("user", "2020-01-01 06:00:00", days=3, step=timedelta(seconds=1))
    assert [a.jst_datetime.second for a in arrivals] == [0, 1, 2]
