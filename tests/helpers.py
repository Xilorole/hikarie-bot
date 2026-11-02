"""Shared test helpers."""

from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from hikarie_bot import db_data
from hikarie_bot.arrivals import compute_arrivals, record_button_arrival
from hikarie_bot.engine import JST, BadgeEngine, compute


def record_arrival(session: Session, jst_datetime: datetime, user_id: str) -> bool:
    """Record an arrival as the bot does for a button press.

    Naive datetimes are taken as JST. Returns False if the user already arrived that day.
    """
    pressed_at = jst_datetime if jst_datetime.tzinfo else jst_datetime.replace(tzinfo=JST)
    event = record_button_arrival(session, user_id, pressed_at)
    return event is not None and event.occurred_at == pressed_at  # otherwise an earlier arrival that day


def compute_in_order(*arrivals: tuple[str, datetime]) -> BadgeEngine:
    """Run the engine over (user_id, aware time) pairs given in any order."""
    return compute(sorted(arrivals, key=lambda arrival: arrival[1]))


CHECK_TYPES = {
    "check_welcome": 1,
    "check_fastest_arrival": 2,
    "check_arrival_count": 3,
    "check_straight_flash": 4,
    "check_time_window": 5,
    "check_kiriban": 6,
    "check_long_time_no_see": 7,
    "check_lucky_you_guys": 8,
    "check_start_dash": 15,
    "check_specific_day": 16,
    "check_yearly_specific_day": 17,
    "check_specific_time": 18,
    "check_takanawa_welcome": 19,
}
BADGE_TYPE = {badge.id: badge.badge_type_id for badge in db_data.Badges}


class EngineChecker:
    """Answer per-rule badge questions from the engine's results on the events stored by record_arrival.

    `check_<rule>(session, user_id, target_date)` returns the badge IDs of that rule earned by
    the user's arrival on target_date's day; `check` covers every rule given at construction.
    """

    def __init__(self, badge_type_to_check: list[int]) -> None:
        """Remember which badge types `check` reports."""
        self.badge_type_to_check = badge_type_to_check

    @staticmethod
    def get_badge(session: Session, badge_id: int) -> int:
        """Return the badge ID (the engine reports IDs)."""
        return badge_id

    def check(self, session: Session, user_id: str, target_date: datetime) -> list[int]:
        """Return the badges of the configured types earned that day."""
        return self._earned(session, user_id, target_date, set(self.badge_type_to_check))

    def __getattr__(self, name: str) -> Callable[..., list[int]]:
        """Provide `check_<rule>` for every rule in CHECK_TYPES."""
        if name not in CHECK_TYPES:
            raise AttributeError(name)
        return lambda session, user_id, target_date: self._earned(session, user_id, target_date, {CHECK_TYPES[name]})

    @staticmethod
    def _earned(session: Session, user_id: str, target_date: datetime, types: set[int]) -> list[int]:
        arrival = compute_arrivals(session).arrival_of(user_id, target_date.date())
        return [badge_id for badge_id in arrival.badge_ids if BADGE_TYPE[badge_id] in types] if arrival else []
