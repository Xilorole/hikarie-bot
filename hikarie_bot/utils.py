from bisect import bisect_right
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone

import jpholiday

# (name, points that complete the level) in level order; a level starts where the previous one is completed.
# Reaching the last threshold is the upper limit: the level stays at the last one.
LEVELS = (
    ("かけだしのかいしゃいん", 20),
    ("みならいのかいしゃいん", 42),
    ("けいけんちゅうのかいしゃいん", 71),
    ("はんにんまえのかいしゃいん", 111),
    ("じしんありのかいしゃいん", 167),
    ("いちにんまえのかいしゃいん", 244),
    ("じゅくれんのかいしゃいん", 346),
    ("せんもんかのかいしゃいん", 478),
    ("たつじんのかいしゃいん", 644),
    ("エリートかいしゃいん", 849),
    ("むてきのかいしゃいん", 1098),
    ("でんせつのかいしゃいん", 1400),
)
_THRESHOLDS = tuple(threshold for _, threshold in LEVELS)


@dataclass(frozen=True)
class Level:
    """The level a point total is in and where the total sits within it."""

    number: int
    name: str
    start: int  # points at which the level starts
    end: int  # points that complete the level
    point: int  # the point total this level was looked up for

    @property
    def is_max(self) -> bool:
        """Whether the point total has reached the upper limit (only the last level can complete)."""
        return self.point >= self.end

    @property
    def span(self) -> int:
        """The number of points the whole level takes."""
        return self.end - self.start

    @property
    def points_to_next(self) -> int:
        """The points still needed to complete the level (0 at the upper limit)."""
        return max(self.end - self.point, 0)

    @property
    def progress_points(self) -> int:
        """The points gained within the level; the whole span at the upper limit (100%)."""
        return min(self.point, self.end) - self.start


def get_level(point: int) -> Level:
    """Get the level of the given point total (the last level at or beyond the upper limit)."""
    index = min(bisect_right(_THRESHOLDS, point), len(LEVELS) - 1)
    name, end = LEVELS[index]
    return Level(number=index + 1, name=name, start=_THRESHOLDS[index - 1] if index else 0, end=end, point=point)


def leveled_up(previous_point: int, current_point: int) -> bool:
    """Check if the level went up between the two point totals.

    Reaching the upper limit does not change the level (see max_level_reached).
    """
    return get_level(previous_point).number < get_level(current_point).number


def max_level_reached(previous_point: int, current_point: int) -> bool:
    """Check if the upper limit was reached between the two point totals."""
    return not get_level(previous_point).is_max and get_level(current_point).is_max


def unix_timestamp_to_jst(unix_timestamp: float) -> datetime:
    """Convert a Unix timestamp to a string representing the date and time in Japan Standard Time (JST).

    Args:
    ----
        unix_timestamp (float): The Unix timestamp to convert.

    Returns:
    -------
        datetime: A datetime object representing the date and time in JST.

    """
    # Convert to a timezone-aware datetime object in UTC
    utc_time = datetime.fromtimestamp(float(unix_timestamp), UTC)

    # Convert to JST
    return utc_time.astimezone(timezone(timedelta(hours=9)))


def get_current_jst_datetime() -> datetime:
    "Get the current time in JST."
    tz_jst = timezone(timedelta(hours=+9), "JST")
    return datetime.now(tz_jst)


def is_jp_bizday(day: date) -> bool:
    "Check if the given day is a business day in Japan."
    return not (
        jpholiday.is_holiday(day)
        or day.weekday() in {5, 6}
        or (day.month == 1 and day.day in {1, 2, 3})
        or (day.month, day.day) == (12, 31)
    )


# list all workdays within the last 5 arrivals
def list_bizdays(start_of_day: datetime, length: int) -> list[datetime]:
    """List all workdays within the last 5 arrivals including the current day."""
    current_date: date = start_of_day.date()
    valid_bizdays = []
    for i in range(14):
        check_date = current_date - timedelta(days=i)
        if is_jp_bizday(check_date):
            valid_bizdays.append(check_date)
            if len(valid_bizdays) == length:
                break
    return valid_bizdays
