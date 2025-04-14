from datetime import UTC, date, datetime, timedelta, timezone

import jpholiday

from .exceptions import InvalidPointError

level_map = {
    1: {"name": "かけだしのかいしゃいん", "point": 20},
    2: {"name": "みならいのかいしゃいん", "point": 42},
    3: {"name": "けいけんちゅうのかいしゃいん", "point": 71},
    4: {"name": "はんにんまえのかいしゃいん", "point": 111},
    5: {"name": "じしんありのかいしゃいん", "point": 167},
    6: {"name": "いちにんまえのかいしゃいん", "point": 244},
    7: {"name": "じゅくれんのかいしゃいん", "point": 346},
    8: {"name": "せんもんかのかいしゃいん", "point": 478},
    9: {"name": "たつじんのかいしゃいん", "point": 644},
    10: {"name": "エリートかいしゃいん", "point": 849},
    11: {"name": "むてきのかいしゃいん", "point": 1098},
    12: {"name": "でんせつのかいしゃいん", "point": 1400},
}


def get_level(point: int) -> int:
    """Get the level based on the given point.

    Args:
    ----
        point (int): The point to determine the level.

    Returns:
    -------
        int: The level.

    """
    for level, level_info in sorted(level_map.items(), key=lambda kv: kv[0]):
        if point < level_info["point"]:
            return level
    raise ValueError


def get_level_name(point: int) -> str:
    """Get the level name based on the given point.

    Args:
    ----
        point (int): The point to determine the level name.

    Returns:
    -------
        str: The name of the level.

    """
    for _, level_info in sorted(level_map.items(), key=lambda kv: kv[0]):
        if point < level_info["point"]:
            return level_info["name"]
    return level_map[len(level_map)]["name"]


def is_level_uped(previous_point: int, current_point: int) -> bool:
    """Check if the current point indicates a level up from the previous point.

    Args:
    ----
        previous_point (int): The previous point value.
        current_point (int): The current point value.

    Returns:
    -------
        bool: True if the current point indicates a level up, False otherwise.

    """
    for _, level_info in sorted(level_map.items(), key=lambda kv: kv[0]):
        if previous_point < level_info["point"] <= current_point:
            return True
    return False


def get_point_to_next_level(point: int) -> int:
    """Calculate the number of points needed to reach the next level.

    Args:
    ----
        point (int): The current point value.

    Returns:
    -------
        int: The number of points needed to reach the next level.

    """
    for _, level_info in sorted(level_map.items(), key=lambda kv: kv[0]):
        if point < level_info["point"]:
            return level_info["point"] - point
    # If the point is greater than the last level point, return 0
    return 0


def get_point_range_to_next_level(point: int) -> int:
    """Calculate the range of points required to reach the next level.

    Args:
    ----
        point (int): The current point value.

    Returns:
    -------
        int: The range of points required to reach the next level.

    Raises:
    ------
        ValueError: If the point value is invalid.

    """
    for idx, level_info in sorted(level_map.items(), key=lambda kv: kv[0]):
        if point < level_info["point"]:
            previous_level_point = level_map[idx - 1].get("point") if level_map.get(idx - 1) else 0
            return level_info["point"] - previous_level_point
    # if the point is greater than the last level point, return undefined
    raise InvalidPointError(point=point)


def get_current_level_point(point: int) -> int:
    """Calculate the current level point based on the given total point.

    Args:
    ----
        point (int): The total point.

    Returns:
    -------
        int: The current level point.

    Raises:
    ------
        ValueError: If the given point is invalid.

    """
    for idx, level_info in sorted(level_map.items(), key=lambda kv: kv[0]):
        if point < level_info["point"]:
            previous_level_point = level_map[idx - 1]["point"] if level_map.get(idx - 1) else 0
            return point - previous_level_point
    raise InvalidPointError(point=point)


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
