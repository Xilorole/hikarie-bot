"""Measure how the bot is used, week by week, from the engine's counted arrivals.

The report holds counts only (never user IDs or times), so it may go to the log channel.
Weeks run Monday to Sunday in JST.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from hikarie_bot.engine import BadgeEngine, week_start
from hikarie_bot.modals import _progress_bar

LAPSE_WEEKS = 4  # a user active in the 4 weeks before a week but not in it has lapsed


@dataclass(frozen=True)
class WeekUsage:
    """Everyone's counted arrivals in a week and how many users made them."""

    start: date
    arrivals: int
    users: int

    @property
    def per_user(self) -> float:
        """Arrivals per active user."""
        return self.arrivals / self.users if self.users else 0.0


@dataclass(frozen=True)
class UsageReport:
    """A week's usage, how its users moved against the weeks before, and the trend up to it.

    - new: first arrival ever in the week;
    - returning: active in the week, not in the LAPSE_WEEKS weeks before, but earlier;
    - lapsed: active in the LAPSE_WEEKS weeks before, not in the week.
    """

    week: WeekUsage
    previous: WeekUsage
    new: int
    returning: int
    lapsed: int
    active_recent: int  # users active in the week or the LAPSE_WEEKS weeks before
    trend: list[WeekUsage]  # oldest first, ending with the week


def last_full_week(today: date) -> date:
    """Return the Monday of the week before today's."""
    return week_start(today) - timedelta(days=7)


def usage_report(engine: BadgeEngine, day: date, weeks: int = 8) -> UsageReport:
    """Report the usage of the week holding `day`, with a trend of `weeks` weeks ending with it."""
    monday = week_start(day)
    users_by_week: dict[date, set[str]] = defaultdict(set)
    arrivals_by_week: dict[date, int] = defaultdict(int)
    first_week: dict[str, date] = {}
    for result in engine.results:
        week = week_start(result.time.date())
        users_by_week[week].add(result.user_id)
        arrivals_by_week[week] += 1
        first_week.setdefault(result.user_id, week)

    def usage(start: date) -> WeekUsage:
        return WeekUsage(start, arrivals_by_week.get(start, 0), len(users_by_week.get(start, set())))

    this_week = users_by_week.get(monday, set())
    before = set().union(*(users_by_week.get(monday - timedelta(weeks=n), set()) for n in range(1, LAPSE_WEEKS + 1)))
    new = {user for user in this_week if first_week[user] == monday}
    return UsageReport(
        week=usage(monday),
        previous=usage(monday - timedelta(weeks=1)),
        new=len(new),
        returning=len(this_week - before - new),
        lapsed=len(before - this_week),
        active_recent=len(this_week | before),
        trend=[usage(monday - timedelta(weeks=n)) for n in reversed(range(weeks))],
    )


def _change(current: int, previous: int) -> str:
    return f"{current - previous:+d}"


def describe_usage(report: UsageReport) -> str:
    """Describe the report as a Slack message (counts only)."""
    week, previous = report.week, report.previous
    end = week.start + timedelta(days=6)
    peak = max((usage.arrivals for usage in report.trend), default=0) or 1
    # at least one cell: a bar of spaces only renders as an empty inline code in Slack
    trend = "\n".join(
        f"`{usage.start:%m/%d}` `{_progress_bar(round(100 * usage.arrivals / peak))}`"
        f" {usage.arrivals}回 / {usage.users}人"
        for usage in report.trend
    )
    return (
        f"*利用状況 {week.start:%Y-%m-%d} 〜 {end:%m-%d}*\n"
        f"• 出社登録: *{week.arrivals}回* (前週比 {_change(week.arrivals, previous.arrivals)})\n"
        f"• 利用した人: *{week.users}人* (前週比 {_change(week.users, previous.users)})"
        f" · 1人あたり {week.per_user:.1f}回\n"
        f"• はじめて: {report.new}人 · 復帰: {report.returning}人"
        f" · 離脱 (前の{LAPSE_WEEKS}週は利用、今週なし): {report.lapsed}人\n"
        f"• 直近{LAPSE_WEEKS + 1}週で利用した人: {report.active_recent}人\n"
        f"*週ごとの推移*\n{trend}"
    )
