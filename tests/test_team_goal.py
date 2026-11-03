"""The weekly team goal and the outlook shown after an arrival."""

from datetime import date, datetime, time, timedelta

from hikarie_bot.constants import JST
from hikarie_bot.engine import TEAM_GOAL_BADGE, BadgeEngine, TeamProgress, team_goal, week_start
from tests.helpers import compute_in_order

FIRST_WEEK = date(2026, 11, 9)  # the Monday the team goal starts
USERS = ("U1", "U2", "U3", "U4")


def at(day: date, hour: int, minute: int = 0) -> datetime:
    """Return a JST time on a day."""
    return datetime.combine(day, time(hour, minute), tzinfo=JST)


def full_week(monday: date) -> list[tuple[str, datetime]]:
    """Every user arrives on every weekday: 20 arrivals, the goal of a five-day week."""
    return [
        (user, at(monday + timedelta(days=offset), 9, index)) for offset in range(5) for index, user in enumerate(USERS)
    ]


def test_goal_scales_with_the_business_days_of_the_week() -> None:
    """Four arrivals per business day: 20 for a full week, 16 with the Labor Thanksgiving Day holiday."""
    assert team_goal(FIRST_WEEK) == 20
    assert team_goal(date(2026, 11, 23)) == 16
    assert week_start(date(2026, 11, 13)) == FIRST_WEEK


def test_the_arrival_that_reaches_the_goal_and_later_ones_get_the_badge() -> None:
    """The 20th arrival of the week reaches the goal; arrivals after it in the week get the badge too."""
    arrivals = [*full_week(FIRST_WEEK), ("U5", at(FIRST_WEEK + timedelta(days=4), 17))]
    engine = compute_in_order(*arrivals)

    week = [result for result in engine.results if week_start(result.time.date()) == FIRST_WEEK]
    with_badge = [TEAM_GOAL_BADGE in result.badge_ids for result in week]
    assert with_badge == [False] * 19 + [True, True]
    assert engine.team_progress(at(FIRST_WEEK + timedelta(days=4), 18)) == TeamProgress(FIRST_WEEK, 21, 20)


def test_each_week_starts_from_zero() -> None:
    """The next week counts its own arrivals."""
    engine = compute_in_order(*full_week(FIRST_WEEK), ("U1", at(date(2026, 11, 16), 9)))

    assert TEAM_GOAL_BADGE not in engine.results[-1].badge_ids
    assert engine.team_progress(at(date(2026, 11, 16), 10)) == TeamProgress(date(2026, 11, 16), 1, 20)


def test_no_team_goal_before_it_starts() -> None:
    """Weeks before the start neither count toward a goal nor give the badge (past points do not change)."""
    engine = compute_in_order(*full_week(date(2026, 11, 2)))

    assert all(TEAM_GOAL_BADGE not in result.badge_ids for result in engine.results)
    assert engine.team_progress(at(date(2026, 11, 6), 18)) is None
    assert engine.week_progress(at(date(2026, 11, 6), 18)).count == 20


def test_outlook_streak_skips_days_off() -> None:
    """The streak counts business days in a row, across weekends and holidays, and breaks on a missed one."""
    engine = BadgeEngine()
    engine.add("U1", at(date(2026, 11, 19), 9))  # Thursday
    engine.add("U1", at(date(2026, 11, 20), 9))  # Friday
    result = engine.add("U1", at(date(2026, 11, 24), 9))  # Tuesday after the Monday holiday

    assert engine.outlook(result).streak == 3

    later = engine.add("U1", at(date(2026, 11, 26), 9))  # missed Wednesday
    assert engine.outlook(later).streak == 1


def test_outlook_next_count_badge_and_kiriban() -> None:
    """After the third arrival: two more to the 5-arrival badge, seven more to everyone's 10th (a kiriban)."""
    engine = BadgeEngine()
    for offset in range(3):
        result = engine.add("U1", at(date(2025, 6, 2) + timedelta(days=offset), 9))

    outlook = engine.outlook(result)
    assert outlook.next_count_badge == (301, 2)
    assert outlook.next_kiriban == (10, 7)
    assert outlook.team is None  # before the team goal starts


def test_outlook_looks_only_at_arrivals_up_to_the_one_given() -> None:
    """A later arrival of the same user does not change the outlook of an earlier one."""
    engine = BadgeEngine()
    first = engine.add("U1", at(date(2025, 6, 2), 9))
    engine.add("U1", at(date(2025, 6, 3), 9))

    assert engine.outlook(first).next_count_badge == (301, 4)
    assert engine.outlook(first).streak == 1
