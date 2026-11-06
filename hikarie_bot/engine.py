"""Compute ranks, badges, scores and levels from arrival events in memory.

Arrivals are processed in time order; each badge rule reads only the state built from
earlier arrivals, so the whole history is one pass with no SQL. The rules reproduce the
previous SQL-based checks (including their quirks); tests/test_engine.py holds that
implementation's results on synthetic arrivals for comparison.

Item picks (db_data/items.py) are given to the engine before the arrivals; a pick acts on
the user's arrivals after the day it was picked, so it never changes the arrival it followed.

Rebirths (docs/design/rebirth.md) are processed with the arrivals in time order: a rebirth starts the
user's points over from 0, and their arrivals after its day get a multiplier that grows with the level
they were reborn at. Reaching the upper limit in a lap earns a mark, which is kept.

Nothing computed here is stored: the messages read the engine's results, recomputed from
arrival_event, item_pick_event and rebirth_event when needed. Times are aware datetimes in JST, so dates and
hours are JST.
"""

from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from heapq import merge
from typing import ClassVar, Self

from dateutil.relativedelta import relativedelta

from hikarie_bot import db_data
from hikarie_bot.constants import JST
from hikarie_bot.db_data.badges import KIRIBANS
from hikarie_bot.db_data.items import (
    ALARM_CLOCK,
    DASH_SHOES,
    DICE,
    ITEM_POINT_CAP,
    ITEMS,
    OMAMORI,
    TREAT,
    WEEKLY_PASS,
    dice_roll,
)
from hikarie_bot.utils import LEVELS, get_level, is_jp_bizday, list_bizdays

BADGE_SCORES = {badge.id: badge.score for badge in db_data.Badges}
APPLY_START = {
    badge_type.id: badge_type.apply_start for badge_type in db_data.BadgeTypes if badge_type.apply_start is not None
}
KIRIBAN_BADGES = {kiriban.number: kiriban.id for kiriban in KIRIBANS}
ARRIVAL_COUNT_BADGES = {5: 301, 20: 302, 100: 303}  # a user's arrival count -> its badge
STRAIGHT_FLASH_LENGTH = 5
STRAIGHT_FLASH, ROYAL_STRAIGHT_FLASH, ULTRA_ROYAL_STRAIGHT_FLASH = 401, 402, 403
TAKANAWA_OFFICE_START = datetime(2026, 1, 19, tzinfo=JST)
ALARM_CLOCK_HOUR = 9  # an arrival before this hour
ALARM_CLOCK_POINTS = 3
DASH_SHOES_POINTS = 2
WEEKLY_PASS_MAX_USES = 3
TREAT_RECIPIENTS = 3
TEAM_GOAL_PER_BIZDAY = 4  # the week's goal for everyone's arrivals, per business day of the week
TEAM_GOAL_BADGE = 2001
MAX_LEVEL = len(LEVELS)
MAX_POINTS = LEVELS[-1][1]  # a lap that reaches this earns a mark
FIRST_REBIRTH_LEVEL = 5  # the level the first rebirth needs; later ones need a level above the previous one's
BASE_MULTIPLIER = 10  # multipliers are in tenths: a rebirth at level n adds n


@dataclass(frozen=True)
class ItemPick:
    """A user's pick of an item on a JST day."""

    user_id: str
    day: date
    item_id: str


@dataclass
class ItemEffect:
    """What an item did for an arrival; giver is the user whose treat it was."""

    item_id: str
    points: int
    giver: str | None = None


@dataclass
class HeldItem:
    """A picked item and how far it has been used."""

    pick: ItemPick
    first_day: date | None = None  # the business days an item with a duration acts on
    last_day: date | None = None
    used_on: date | None = None  # the arrival a one-shot item acted on
    uses: int = 0

    @property
    def one_shot(self) -> bool:
        """Whether the item acts on one arrival only."""
        return self.last_day is None

    def acts_on(self, day: date) -> bool:
        """Whether the item acts on an arrival on this JST day (one-shot: if it is still unused)."""
        if self.one_shot:
            return self.used_on is None and self.pick.day < day
        return self.first_day <= day <= self.last_day

    def held_on(self, day: date) -> bool:
        """Whether the user still holds the item on this JST day (after that day's arrival)."""
        if self.pick.day > day:
            return False
        if self.one_shot:
            return self.used_on is None or self.used_on > day
        return day <= self.last_day


def previous_bizday(day: date) -> date:
    """Return the business day before a JST day."""
    current = day - timedelta(days=1)
    while not is_jp_bizday(current):
        current -= timedelta(days=1)
    return current


@dataclass
class Treat:
    """A treat given on a day: the later arrivals that day get a point each, up to TREAT_RECIPIENTS."""

    giver: str
    remaining: int = TREAT_RECIPIENTS


def next_bizdays(day: date, count: int) -> list[date]:
    """Return the first `count` business days after a JST day."""
    days: list[date] = []
    current = day
    while len(days) < count:
        current += timedelta(days=1)
        if is_jp_bizday(current):
            days.append(current)
    return days


def week_start(day: date) -> date:
    """Return the Monday of a JST day's week."""
    return day - timedelta(days=day.weekday())


def team_goal(monday: date) -> int:
    """Return the goal for everyone's arrivals in the week from this Monday (scaled by its business days)."""
    return TEAM_GOAL_PER_BIZDAY * sum(is_jp_bizday(monday + timedelta(days=i)) for i in range(7))


@dataclass(frozen=True)
class TeamProgress:
    """Everyone's arrivals in a week (Monday to Sunday, JST) so far, against the week's goal."""

    week_start: date
    count: int
    goal: int

    @property
    def reached(self) -> bool:
        """Whether the goal is reached; every arrival from then on in the week gets the team goal badge."""
        return self.goal > 0 and self.count >= self.goal


@dataclass(frozen=True)
class Outlook:
    """What a user can aim for after an arrival: the streak, the next count badge, the next kiriban, the week.

    next_count_badge and next_kiriban are (badge ID or kiriban number, arrivals still to go).
    """

    streak: int
    next_count_badge: tuple[int, int] | None
    next_kiriban: tuple[int, int] | None
    team: TeamProgress | None
    streak_pending: bool = False  # a business day not arrived yet: arriving today extends the streak


@dataclass
class ArrivalResult:
    """One counted arrival (the first of a user's day) and what it earned.

    The scores are the points of the user's current lap (since their last rebirth). score_sum is the badges'
    and items' points times the multiplier, rounded up.
    """

    id: int
    user_id: str
    time: datetime
    rank: int
    badge_ids: list[int]
    score_sum: int
    previous_score: int
    current_score: int
    item_effects: list[ItemEffect] = field(default_factory=list)  # their points are part of score_sum
    multiplier: int = BASE_MULTIPLIER  # in tenths
    marks: int = 0  # the marks the user holds after this arrival

    @property
    def earned_mark(self) -> bool:
        """Whether this arrival reached the upper limit of the lap, earning a mark."""
        return self.previous_score < MAX_POINTS <= self.current_score


@dataclass(frozen=True)
class Rebirth:
    """A rebirth that took effect: the level it was at and the multiplier after it (in tenths)."""

    user_id: str
    time: datetime
    number: int  # 1 for the first rebirth
    level: int
    multiplier: int


@dataclass(frozen=True)
class RebirthStatus:
    """Where a user stands on rebirth at some time.

    required_level is the level the next rebirth needs; can is whether the user may be reborn now (the level
    is enough and they were not reborn today). multiplier is the one acting on the user's next arrival,
    next_multiplier the one a rebirth now would give.
    """

    level: int
    points: int
    required_level: int
    points_to_go: int  # until the required level (0 once reached)
    reborn_today: bool
    multiplier: int
    next_multiplier: int
    rebirths: list[Rebirth]
    marks: int

    @property
    def can(self) -> bool:
        """Whether the user may be reborn now."""
        return self.points_to_go == 0 and not self.reborn_today


def multiplied(points: int, multiplier: int) -> int:
    """Return points times a multiplier in tenths, rounded up."""
    return -(-points * multiplier // BASE_MULTIPLIER)


def format_multiplier(multiplier: int) -> str:
    """Return a multiplier in tenths as "1.5倍"."""
    return f"{multiplier // BASE_MULTIPLIER}.{multiplier % BASE_MULTIPLIER}倍"


@dataclass
class UserState:
    """What the rules need to know about one user's earlier arrivals."""

    times: list[datetime] = field(default_factory=list)
    straight_flash: list[set[int]] = field(default_factory=list)
    results: list[ArrivalResult] = field(default_factory=list)
    items: list[HeldItem] = field(default_factory=list)  # in pick order
    forgive_gap: bool = False  # set while an omamori acts on the arrival being checked
    score: int = 0  # the points of the current lap
    rebirths: list[Rebirth] = field(default_factory=list)
    marks: int = 0

    def multiplier_on(self, day: date) -> int:
        """Return the multiplier (in tenths) on the user's arrivals on a JST day: rebirths act after their day."""
        return BASE_MULTIPLIER + sum(rebirth.level for rebirth in self.rebirths if rebirth.time.date() < day)

    def required_level(self) -> int:
        """Return the level the next rebirth needs: above the previous rebirth's, or the top level again."""
        if not self.rebirths:
            return FIRST_REBIRTH_LEVEL
        return min(self.rebirths[-1].level + 1, MAX_LEVEL)


@dataclass
class UserBadgeTally:
    """How often and when a user earned a badge."""

    first: datetime
    last: datetime
    count: int


def _time(result: ArrivalResult) -> datetime:
    return result.time


class BadgeEngine:
    """Process arrivals in time order and keep the state the badge rules read."""

    def __init__(self) -> None:
        """Start with no arrivals."""
        self.times: list[datetime] = []  # every counted arrival, in processing (= time) order
        self.days: dict[date, list[ArrivalResult]] = defaultdict(list)
        self.users: dict[str, UserState] = defaultdict(UserState)
        self.results: list[ArrivalResult] = []
        self.user_badges: dict[tuple[str, int], UserBadgeTally] = {}
        self.treats: dict[date, list[Treat]] = defaultdict(list)

    def pick(self, user_id: str, day: date, item_id: str) -> None:
        """Give the user an item picked on a JST day; it acts on their arrivals after that day.

        Picks must be given before the arrivals they act on (compute gives them all first).
        """
        item = ITEMS.get(item_id)
        if item is None:  # an item that was removed from the code no longer acts
            return
        held = HeldItem(ItemPick(user_id, day, item_id))
        if item.duration_bizdays is not None:
            days = next_bizdays(day, item.duration_bizdays)
            held.first_day, held.last_day = days[0], days[-1]
        self.users[user_id].items.append(held)

    def held_item(self, user_id: str, day: date) -> HeldItem | None:
        """Return the item the user holds on a JST day, if any."""
        user = self.users.get(user_id)
        return next((held for held in reversed(user.items) if held.held_on(day)), None) if user else None

    def add(self, user_id: str, time: datetime) -> ArrivalResult | None:
        """Count an arrival (an aware datetime); returns None if the user already arrived that JST day."""
        if time.tzinfo is None:
            msg = "the engine requires timezone-aware datetimes"
            raise ValueError(msg)
        time = time.astimezone(JST)
        user = self.users[user_id]
        if user.times and user.times[-1].date() == time.date():
            return None
        day = self.days[time.date()]
        rank = bisect_left(day, time, key=_time) + 1

        user.times.append(time)
        self.times.append(time)

        acting = [held for held in user.items if held.acts_on(time.date())]
        user.forgive_gap = any(held.pick.item_id == OMAMORI for held in acting)
        badge_ids = [badge_id for checker in self.CHECKERS.values() for badge_id in checker(self, user_id, time)]
        user.forgive_gap = False
        item_effects = self._item_effects(user_id, time, rank, acting)
        multiplier = user.multiplier_on(time.date())
        score_sum = multiplied(
            sum(BADGE_SCORES[badge_id] for badge_id in badge_ids) + sum(effect.points for effect in item_effects),
            multiplier,
        )
        previous_score = user.score
        user.score += score_sum
        if previous_score < MAX_POINTS <= user.score:
            user.marks += 1

        for badge_id in badge_ids:
            tally = self.user_badges.get((user_id, badge_id))
            if tally is None:
                self.user_badges[user_id, badge_id] = UserBadgeTally(first=time, last=time, count=1)
            else:
                tally.count += 1
                tally.last = time

        result = ArrivalResult(
            id=len(self.results) + 1,
            user_id=user_id,
            time=time,
            rank=rank,
            badge_ids=badge_ids,
            score_sum=score_sum,
            previous_score=previous_score,
            current_score=user.score,
            item_effects=item_effects,
            multiplier=multiplier,
            marks=user.marks,
        )
        self.results.append(result)
        user.results.append(result)
        day.append(result)
        return result

    def rebirth(self, user_id: str, time: datetime) -> Rebirth | None:
        """Start the user's points over at `time` (aware) if they may be reborn then; return the rebirth, or None.

        A rebirth the rules no longer allow (after a rule change) is ignored.
        """
        status = self.rebirth_status(user_id, time)
        if not status.can:
            return None
        user = self.users[user_id]
        rebirth = Rebirth(user_id, time.astimezone(JST), len(user.rebirths) + 1, status.level, status.next_multiplier)
        user.rebirths.append(rebirth)
        user.score = 0
        return rebirth

    def rebirth_status(self, user_id: str, now: datetime) -> RebirthStatus:
        """Return where the user stands on rebirth at `now` (aware; after the events processed so far)."""
        now = now.astimezone(JST)
        user = self.users.get(user_id) or UserState()
        level = get_level(user.score)
        required = user.required_level()
        start = 0 if required == 1 else LEVELS[required - 2][1]
        tomorrow = now.date() + timedelta(days=1)
        return RebirthStatus(
            level=level.number,
            points=user.score,
            required_level=required,
            points_to_go=max(0, start - user.score),
            reborn_today=bool(user.rebirths) and user.rebirths[-1].time.date() == now.date(),
            multiplier=user.multiplier_on(tomorrow),
            next_multiplier=user.multiplier_on(tomorrow) + level.number,
            rebirths=list(user.rebirths),
            marks=user.marks,
        )

    def _item_effects(self, user_id: str, time: datetime, rank: int, acting: list[HeldItem]) -> list[ItemEffect]:
        """Apply the user's acting items and the day's treats; one-shot items are used up."""
        day = time.date()
        effects: list[ItemEffect] = []
        for held in acting:
            if held.one_shot:
                held.used_on = day
            effects.append(ItemEffect(held.pick.item_id, self._item_points(user_id, time, rank, held)))
            if held.pick.item_id == TREAT:
                self.treats[day].append(Treat(giver=user_id))
        for treat in self.treats.get(day, []):
            if treat.giver != user_id and treat.remaining > 0:
                treat.remaining -= 1
                effects.append(ItemEffect(TREAT, 1, giver=treat.giver))
        # the cap keeps items from outgrowing the badges: later effects lose their points first
        budget = ITEM_POINT_CAP
        for effect in effects:
            effect.points = min(effect.points, budget)
            budget -= effect.points
        return effects

    def _item_points(self, user_id: str, time: datetime, rank: int, held: HeldItem) -> int:
        """Return the points an item gives this arrival (before the cap)."""
        item_id = held.pick.item_id
        if item_id == ALARM_CLOCK and time.hour < ALARM_CLOCK_HOUR:
            return ALARM_CLOCK_POINTS
        if item_id == DASH_SHOES and rank == 1:
            return DASH_SHOES_POINTS
        if item_id == DICE:
            return dice_roll(user_id, time.date())
        if item_id == WEEKLY_PASS and held.uses < WEEKLY_PASS_MAX_USES:
            times = self.users[user_id].times
            previous_bizday = list_bizdays(self._start_of_day(time) - timedelta(days=1), 1)
            if len(times) >= 2 and [times[-2].date()] == previous_bizday:  # noqa: PLR2004
                held.uses += 1
                return 1
        return 0

    def arrivals_on(self, day: date) -> list[ArrivalResult]:
        """Return the arrivals on a JST day, in time order."""
        return self.days.get(day, [])

    def arrival_of(self, user_id: str, day: date) -> ArrivalResult | None:
        """Return the user's counted arrival on a JST day, if any."""
        return next((result for result in self.arrivals_on(day) if result.user_id == user_id), None)

    def team_progress(self, until: datetime) -> TeamProgress | None:
        """Return everyone's arrivals in the week of `until` up to and including it, or None before the team goal.

        `until` is an aware datetime; the week runs Monday to Sunday in JST.
        """
        return None if until < APPLY_START[20] else self.week_progress(until)

    def week_progress(self, until: datetime) -> TeamProgress:
        """Return everyone's arrivals in the week of `until` up to and including it, whether or not the goal applies."""
        until = until.astimezone(JST)
        monday = week_start(until.date())
        start = datetime.combine(monday, datetime.min.time(), tzinfo=JST)
        count = bisect_right(self.times, until) - bisect_left(self.times, start)
        return TeamProgress(week_start=monday, count=count, goal=team_goal(monday))

    def outlook(self, result: ArrivalResult) -> Outlook:
        """Return what the user can aim for right after this arrival (later arrivals are not looked at)."""
        # result.id numbers the arrivals of all users, as the kiribans do
        return self._outlook(result.user_id, result.time, result.id)

    def status_outlook(self, user_id: str, now: datetime) -> Outlook:
        """Return what the user can aim for at `now` (an aware datetime), arrived today or not.

        Before today's arrival the streak counts up to the previous business day, as it is still alive.
        """
        now = now.astimezone(JST)
        return self._outlook(user_id, now, bisect_right(self.times, now))

    def _outlook(self, user_id: str, until: datetime, everyone: int) -> Outlook:
        """Build the outlook from the user's arrivals up to `until` and everyone's arrival count."""
        user = self.users.get(user_id)
        times = user.times if user else []
        own_count = bisect_right(times, until)
        days = {time.date() for time in times[:own_count]}
        day = until.date()
        pending = day not in days and is_jp_bizday(day)
        if day not in days:
            day = previous_bizday(day)
        streak = 0
        while day in days:
            streak += 1
            day = previous_bizday(day)
        next_count = next(
            ((badge_id, count - own_count) for count, badge_id in ARRIVAL_COUNT_BADGES.items() if count > own_count),
            None,
        )
        kiriban = next((kiriban for kiriban in KIRIBANS if kiriban.number > everyone), None)
        return Outlook(
            streak=streak,
            next_count_badge=next_count,
            next_kiriban=(kiriban.number, kiriban.number - everyone) if kiriban else None,
            team=self.team_progress(until),
            streak_pending=pending and streak > 0,
        )

    # --- badge rules ---

    @staticmethod
    def _start_of_day(time: datetime) -> datetime:
        return time.replace(hour=0, minute=0, second=0, microsecond=0)

    def _before(self, user_id: str, until: datetime) -> list[datetime]:
        """Return the user's arrivals strictly before `until`."""
        times = self.users[user_id].times
        return times[: bisect_left(times, until)]

    def _welcome(self, user_id: str, time: datetime) -> list[int]:
        return [101] if not self._before(user_id, self._start_of_day(time)) else []

    def _fastest_arrival(self, _user_id: str, time: datetime) -> list[int]:
        return [201] if bisect_left(self.days[time.date()], time, key=_time) == 0 else []

    def _arrival_count(self, user_id: str, time: datetime) -> list[int]:
        count = len(self._before(user_id, self._start_of_day(time) + timedelta(days=1)))
        return [ARRIVAL_COUNT_BADGES[count]] if count in ARRIVAL_COUNT_BADGES else []

    def _straight_flash(self, user_id: str, time: datetime) -> list[int]:
        user = self.users[user_id]
        result = self._straight_flash_badges(user, time)
        user.straight_flash.append(set(result))
        return result

    def _straight_flash_badges(self, user: UserState, time: datetime) -> list[int]:
        recent = user.times[-STRAIGHT_FLASH_LENGTH:][::-1]
        if len(recent) < STRAIGHT_FLASH_LENGTH:
            return []
        # the last five business days within two weeks; fewer (a long holiday) means no streak
        bizdays = list_bizdays(self._start_of_day(time), STRAIGHT_FLASH_LENGTH)
        dates = [arrival.date() for arrival in recent]
        if bizdays != dates and not (user.forgive_gap and self._one_gap(time, dates)):
            return []
        # A badge earned within the previous four arrivals is not awarded again.
        recently_achieved = set().union(*user.straight_flash[-(STRAIGHT_FLASH_LENGTH - 1) :])
        badges = [] if STRAIGHT_FLASH in recently_achieved else [STRAIGHT_FLASH]
        hours = {arrival.hour for arrival in recent}
        if len(hours) == STRAIGHT_FLASH_LENGTH:
            if ROYAL_STRAIGHT_FLASH not in recently_achieved:
                badges.append(ROYAL_STRAIGHT_FLASH)
            if (
                ULTRA_ROYAL_STRAIGHT_FLASH not in recently_achieved
                and max(hours) - min(hours) == STRAIGHT_FLASH_LENGTH - 1
            ):
                badges.append(ULTRA_ROYAL_STRAIGHT_FLASH)
        return badges

    def _one_gap(self, time: datetime, dates: list[date]) -> bool:
        """Whether the dates are the last six business days but one (an omamori forgives the missing one)."""
        bizdays = list_bizdays(self._start_of_day(time), STRAIGHT_FLASH_LENGTH + 1)
        return len(bizdays) == STRAIGHT_FLASH_LENGTH + 1 and dates[0] == bizdays[0] and set(dates) < set(bizdays)

    def _time_window(self, _user_id: str, time: datetime) -> list[int]:
        for start, end, badge_id in ((6, 7, 504), (7, 9, 501), (9, 11, 502), (11, 18, 503)):
            if start <= time.hour < end:
                return [badge_id]
        return []

    def _kiriban(self, _user_id: str, time: datetime) -> list[int]:
        previous = bisect_left(self.times, time)
        badge_id = KIRIBAN_BADGES.get(previous + 1)
        return [badge_id] if badge_id else []

    def _long_time_no_see(self, user_id: str, time: datetime) -> list[int]:
        earlier = self._before(user_id, time)
        if not earlier:
            return []
        last, current = earlier[-1].date(), time.date()
        spans = (
            (704, relativedelta(months=6)),
            (703, relativedelta(months=2)),
            (702, timedelta(days=30)),
            (701, timedelta(days=14)),
        )
        for badge_id, span in spans:
            if last + span < current:
                return [badge_id]
        return []

    def _lucky_you_guys(self, _user_id: str, time: datetime) -> list[int]:
        minute = time.replace(second=0, microsecond=0)
        # arrivals so far (this one included) within this minute, up to this time
        count = bisect_right(self.times, time) - bisect_left(self.times, minute)
        return {2: [801], 3: [802], 4: [803]}.get(count, [])

    def _start_dash(self, user_id: str, time: datetime) -> list[int]:
        times = self.users[user_id].times
        first_after_start = times[bisect_left(times, APPLY_START[15])] if times[-1] >= APPLY_START[15] else None
        if first_after_start is not None and time - first_after_start <= timedelta(days=14):
            return [1501]
        return []

    def _specific_day(self, _user_id: str, time: datetime) -> list[int]:
        if time < APPLY_START[16]:
            return []
        return {date(2024, 12, 27): [1601], date(2025, 1, 6): [1602]}.get(time.date(), [])

    def _yearly_specific_day(self, user_id: str, time: datetime) -> list[int]:
        if time < APPLY_START[17]:
            return []
        month, day = time.month, time.day
        if (month, day) == (12, 25):
            return [1701]
        if month == 3 and 24 < day <= 31 and not self._since(user_id, datetime(time.year, 3, 25, tzinfo=JST), time):  # noqa: PLR2004
            return [1702]
        if month == 4 and 1 <= day < 8 and not self._since(user_id, datetime(time.year, 4, 1, tzinfo=JST), time):  # noqa: PLR2004
            return [1703]
        if (month, day) in {(4, 29), (4, 30), (5, 1), (5, 2), (5, 3), (5, 4), (5, 5)}:
            return [1704]
        return []

    def _since(self, user_id: str, start: datetime, until: datetime) -> list[datetime]:
        """Return the user's arrivals in [start, until)."""
        times = self.users[user_id].times
        return times[bisect_left(times, start) : bisect_left(times, until)]

    def _specific_time(self, _user_id: str, time: datetime) -> list[int]:
        if time < APPLY_START[18]:
            return []
        hour, minute = time.hour, time.minute
        exact = {(11, 11): 1804, (11, 22): 1805, (11, 29): 1806, (9, 10): 1807, (12, 34): 1803}
        if (hour, minute) in exact:
            return [exact[hour, minute]]
        if hour == minute:
            return [1802]
        if abs(hour - minute) == 1:
            return [1801]
        return []

    def _takanawa_welcome(self, user_id: str, time: datetime) -> list[int]:
        if time < APPLY_START[19]:
            return []
        return [1901] if not self._since(user_id, TAKANAWA_OFFICE_START, time) else []

    def _team_goal(self, _user_id: str, time: datetime) -> list[int]:
        # this arrival is already counted: the one that reaches the goal gets the badge, as do later ones
        progress = self.team_progress(time)
        return [TEAM_GOAL_BADGE] if progress is not None and progress.reached else []

    # The badge types the bot awards, by type ID, in evaluation order.
    CHECKERS: ClassVar[dict[int, Callable[[Self, str, datetime], list[int]]]] = {
        1: _welcome,
        2: _fastest_arrival,
        3: _arrival_count,
        4: _straight_flash,
        5: _time_window,
        6: _kiriban,
        7: _long_time_no_see,
        8: _lucky_you_guys,
        15: _start_dash,
        16: _specific_day,
        17: _yearly_specific_day,
        18: _specific_time,
        19: _takanawa_welcome,
        20: _team_goal,
    }


def compute(
    arrivals: Iterable[tuple[str, datetime]],
    picks: Iterable[ItemPick] = (),
    rebirths: Iterable[tuple[str, datetime]] = (),
) -> BadgeEngine:
    """Run the engine over (user_id, aware time) pairs in time order, with the item picks and the rebirths.

    Arrivals and rebirths are processed together in time order (each iterable in time order).
    """
    engine = BadgeEngine()
    for pick in sorted(picks, key=lambda pick: pick.day):
        engine.pick(pick.user_id, pick.day, pick.item_id)
    for kind, user_id, time in _in_time_order(arrivals, rebirths):
        if kind == "arrival":
            engine.add(user_id, time)
        else:
            engine.rebirth(user_id, time)
    return engine


def _in_time_order(
    arrivals: Iterable[tuple[str, datetime]], rebirths: Iterable[tuple[str, datetime]]
) -> Iterator[tuple[str, str, datetime]]:
    """Merge the arrivals and the rebirths by time; an arrival comes before a rebirth at the same time."""
    tagged_arrivals = (("arrival", user_id, time) for user_id, time in arrivals)
    tagged_rebirths = (("rebirth", user_id, time) for user_id, time in rebirths)
    return merge(tagged_arrivals, tagged_rebirths, key=lambda event: event[2])
