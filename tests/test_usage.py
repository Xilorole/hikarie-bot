"""The weekly usage report (counts only)."""

from datetime import date, datetime, time, timedelta

from hikarie_bot.constants import JST
from hikarie_bot.usage import describe_usage, last_full_week, usage_report
from tests.helpers import compute_in_order

WEEK = date(2025, 6, 9)  # a Monday


def at(day: date, hour: int = 9) -> datetime:
    """Return a JST time on a day."""
    return datetime.combine(day, time(hour), tzinfo=JST)


def test_report_counts_new_returning_and_lapsed_users() -> None:
    """New: first ever this week. Returning: back after more than four weeks. Lapsed: active before, not now."""
    engine = compute_in_order(
        ("U1", at(WEEK - timedelta(weeks=1))),  # regular: last week and this week, twice
        ("U1", at(WEEK)),
        ("U1", at(WEEK + timedelta(days=1))),
        ("U2", at(WEEK - timedelta(weeks=8))),  # back after eight weeks
        ("U2", at(WEEK + timedelta(days=2))),
        ("U3", at(WEEK + timedelta(days=3))),  # new
        ("U4", at(WEEK - timedelta(weeks=3))),  # lapsed
    )

    report = usage_report(engine, WEEK + timedelta(days=4), weeks=3)

    assert (report.week.start, report.week.arrivals, report.week.users) == (WEEK, 4, 3)
    assert (report.previous.arrivals, report.previous.users) == (1, 1)
    assert (report.new, report.returning, report.lapsed, report.active_recent) == (1, 1, 1, 4)
    assert [(usage.start, usage.arrivals) for usage in report.trend] == [
        (WEEK - timedelta(weeks=2), 0),
        (WEEK - timedelta(weeks=1), 1),
        (WEEK, 4),
    ]


def test_description_has_counts_but_no_user_ids() -> None:
    """The text for the log channel carries counts only."""
    engine = compute_in_order(("U0SECRET", at(WEEK)), ("U0OTHER", at(WEEK, 10)))

    text = describe_usage(usage_report(engine, WEEK))

    assert "出社登録: *2回* (前週比 +2)" in text
    assert "利用した人: *2人* (前週比 +2) · 1人あたり 1.0回" in text
    assert "U0" not in text


def test_last_full_week_is_the_monday_before_this_week() -> None:
    """On any day, the report covers the previous Monday to Sunday."""
    assert last_full_week(date(2025, 6, 16)) == WEEK
    assert last_full_week(date(2025, 6, 22)) == WEEK


def test_a_week_without_arrivals_still_draws_one_cell() -> None:
    """A bar of spaces renders as an empty inline code in Slack, so an empty week keeps one cell."""
    engine = compute_in_order(("U1", at(WEEK)))

    text = describe_usage(usage_report(engine, WEEK, weeks=2))

    assert f"`{WEEK - timedelta(weeks=1):%m/%d}` `░░░░░░░░░░` 0回 / 0人" in text
