"""Compute ranks, badges, scores and levels from arrival events in memory.

Arrivals are processed in time order; each badge rule reads only the state built from
earlier arrivals, so the whole history is one pass with no SQL. The rules reproduce the
previous SQL-based checks (including their quirks); tests/data holds that implementation's
results on synthetic arrivals for comparison.

Times are naive JST wall-clock datetimes, as the derived tables store them.
"""

from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta

from hikarie_bot import db_data
from hikarie_bot.constants import BADGE_TYPES_TO_CHECK, KIRIBAN_GENERATION_LIMIT
from hikarie_bot.db_data.badges import KiribanGenerator
from hikarie_bot.utils import (
    get_current_level_point,
    get_level,
    get_level_name,
    get_point_range_to_next_level,
    get_point_to_next_level,
    is_level_uped,
    list_bizdays,
)

JST = ZoneInfo("Asia/Tokyo")

BADGE_SCORES = {badge.id: badge.score for badge in db_data.Badges}
APPLY_START = {
    badge_type.id: badge_type.apply_start.replace(tzinfo=None)
    for badge_type in db_data.BadgeTypes
    if badge_type.apply_start is not None
}
KIRIBAN_BADGES = {
    kiriban.number: kiriban.id for kiriban in KiribanGenerator().generate_kiriban(KIRIBAN_GENERATION_LIMIT)
}
STRAIGHT_FLASH_LENGTH = 5
STRAIGHT_FLASH, ROYAL_STRAIGHT_FLASH, ULTRA_ROYAL_STRAIGHT_FLASH = 401, 402, 403
TAKANAWA_OFFICE_START = datetime(2026, 1, 19)  # noqa: DTZ001  # naive JST like the stored times


def to_jst_wall_clock(moment: datetime) -> datetime:
    """Convert an aware datetime to the naive JST wall-clock time stored in derived tables."""
    return moment.astimezone(JST).replace(tzinfo=None)


@dataclass
class UserState:
    """What the rules need to know about one user's earlier arrivals."""

    times: list[datetime] = field(default_factory=list)
    straight_flash: list[set[int]] = field(default_factory=list)
    score: int | None = None


@dataclass
class ArrivalResult:
    """One counted arrival (the first of a user's day) and what it earned."""

    id: int
    user_id: str
    time: datetime
    rank: int
    badge_ids: list[int]
    score_sum: int
    previous_score: int
    current_score: int


@dataclass
class UserBadgeTally:
    """How often and when a user earned a badge."""

    first: datetime
    last: datetime
    count: int


class BadgeEngine:
    """Process arrivals in time order and keep the state the badge rules read."""

    def __init__(self) -> None:
        """Start with no arrivals."""
        self.times: list[datetime] = []  # every counted arrival, in processing (= time) order
        self.days: dict[date, list[datetime]] = defaultdict(list)
        self.users: dict[str, UserState] = defaultdict(UserState)
        self.results: list[ArrivalResult] = []
        self.user_badges: dict[tuple[str, int], UserBadgeTally] = {}
        self._checkers: dict[int, Callable[[str, datetime], list[int]]] = {
            1: self._welcome,
            2: self._fastest_arrival,
            3: self._arrival_count,
            4: self._straight_flash,
            5: self._time_window,
            6: self._kiriban,
            7: self._long_time_no_see,
            8: self._lucky_you_guys,
            15: self._start_dash,
            16: self._specific_day,
            17: self._yearly_specific_day,
            18: self._specific_time,
            19: self._takanawa_welcome,
        }

    def add(self, user_id: str, time: datetime) -> ArrivalResult | None:
        """Count an arrival; returns None if the user already arrived that day."""
        user = self.users[user_id]
        if user.times and user.times[-1].date() == time.date():
            return None
        day = self.days[time.date()]
        rank = bisect_left(day, time) + 1

        user.times.append(time)
        day.append(time)
        self.times.append(time)

        badge_ids = [
            badge_id for type_id in BADGE_TYPES_TO_CHECK for badge_id in self._checkers[type_id](user_id, time)
        ]
        score_sum = sum(BADGE_SCORES[badge_id] for badge_id in badge_ids)
        previous_score = user.score or 0
        user.score = previous_score + score_sum

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
        )
        self.results.append(result)
        return result

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
        return [201] if bisect_left(self.days[time.date()], time) == 0 else []

    def _arrival_count(self, user_id: str, time: datetime) -> list[int]:
        count = len(self._before(user_id, self._start_of_day(time) + timedelta(days=1)))
        return {5: [301], 20: [302], 100: [303]}.get(count, [])

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
        if bizdays != [arrival.date() for arrival in recent]:
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
        if month == 3 and 24 < day <= 31 and not self._since(user_id, datetime(time.year, 3, 25), time):  # noqa: DTZ001, PLR2004
            return [1702]
        if month == 4 and 1 <= day < 8 and not self._since(user_id, datetime(time.year, 4, 1), time):  # noqa: DTZ001, PLR2004
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


@dataclass
class UserLevel:
    """The level fields stored on User and UserInfoRaw for a score change."""

    level: int
    level_name: str
    level_uped: bool
    point_to_next_level: int
    point_range_to_next_level: int
    current_level_point: int

    @classmethod
    def of(cls, previous_score: int, current_score: int) -> "UserLevel":
        """Compute the level fields for a score change."""
        return cls(
            level=get_level(current_score),
            level_name=get_level_name(current_score),
            level_uped=is_level_uped(previous_score, current_score),
            point_to_next_level=get_point_to_next_level(current_score),
            point_range_to_next_level=get_point_range_to_next_level(current_score),
            current_level_point=get_current_level_point(current_score),
        )


def compute(arrivals: Iterable[tuple[str, datetime]]) -> BadgeEngine:
    """Run the engine over (user_id, naive JST time) pairs in time order."""
    engine = BadgeEngine()
    for user_id, time in arrivals:
        engine.add(user_id, time)
    return engine
