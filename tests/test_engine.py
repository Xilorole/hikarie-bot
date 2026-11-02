# Times are written naive for brevity and taken as JST.
# ruff: noqa: DTZ001
import random
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta

import pytest

from hikarie_bot.constants import BADGE_TYPES_TO_CHECK
from hikarie_bot.db_data import Badges
from hikarie_bot.engine import JST, BadgeEngine, compute
from hikarie_bot.utils import is_jp_bizday

BADGE_TYPE = {badge.id: badge.badge_type_id for badge in Badges}


def synthetic_arrivals() -> list[tuple[str, datetime]]:
    """Arrivals from 2024-11 to 2026-02 shaped to trigger every badge rule at least once."""
    rng = random.Random(42)
    arrivals: list[tuple[str, datetime]] = []
    day = date(2024, 11, 25)
    streak_hours = iter([7, 8, 9, 10, 11])  # one straight flash week with consecutive distinct hours
    while day <= date(2026, 2, 6):
        weekday_business = is_jp_bizday(day)
        if day >= date(2025, 2, 3) and day <= date(2025, 2, 7):
            arrivals.append(("U1", datetime.combine(day, time(next(streak_hours), 30))))
        elif weekday_business:
            arrivals.append(("U1", datetime.combine(day, time(rng.choice([7, 8, 9, 10]), rng.randint(0, 59)))))
        arrivals.extend(
            (user, datetime.combine(day, time(rng.randint(6, 16), rng.randint(0, 59), rng.randint(0, 59))))
            for user in ("U2", "U3", "U4")
            if weekday_business and rng.random() < 0.12
        )
        day += timedelta(days=1)

    special = [
        ("U5", datetime(2024, 11, 26, 9, 0)),  # then away for over six months
        ("U5", datetime(2025, 7, 1, 9, 0)),
        ("U6", datetime(2024, 12, 9, 8, 0)),  # start dash: first arrival after apply_start
        ("U6", datetime(2024, 12, 18, 8, 0)),
        ("U2", datetime(2024, 12, 25, 10, 0)),
        ("U3", datetime(2024, 12, 27, 10, 0)),
        ("U3", datetime(2025, 1, 6, 10, 5)),
        ("U4", datetime(2025, 3, 26, 9, 0)),
        ("U4", datetime(2025, 4, 2, 9, 0)),
        ("U2", datetime(2025, 5, 3, 11, 0)),  # golden week, a Saturday
        ("U2", datetime(2025, 6, 10, 11, 11)),
        ("U3", datetime(2025, 6, 11, 11, 22)),
        ("U4", datetime(2025, 6, 12, 11, 29)),
        ("U3", datetime(2025, 6, 13, 9, 10)),
        ("U4", datetime(2025, 6, 16, 12, 34)),
        ("U2", datetime(2025, 6, 17, 10, 10)),
        ("U3", datetime(2025, 6, 18, 9, 8)),
        ("U6", datetime(2026, 1, 19, 9, 0)),
    ]
    # four people within one minute
    special += [
        (user, datetime(2025, 9, 9, 7, 5, second)) for user, second in (("U2", 1), ("U3", 2), ("U4", 3), ("U6", 4))
    ]
    return sorted(
        ((user, time.replace(tzinfo=JST)) for user, time in arrivals + special), key=lambda arrival: arrival[1]
    )


# Recorded from the previous SQL-based implementation (insert_arrival_action) on synthetic_arrivals()
# before it was removed: how often each badge was earned and every user's final score.
PREVIOUS_ARRIVALS = 427
PREVIOUS_BADGE_COUNTS = {
    101: 6, 201: 294, 301: 4, 302: 4, 303: 1, 401: 58, 402: 1, 403: 1,
    501: 162, 502: 183, 503: 73, 504: 9, 701: 19, 702: 7, 703: 1, 704: 2, 801: 1, 802: 1, 803: 1,
    1501: 22, 1601: 2, 1602: 2, 1701: 5, 1702: 3, 1703: 2, 1704: 5,
    1801: 14, 1802: 5, 1803: 1, 1804: 2, 1806: 1, 1807: 3, 1901: 5,
    **dict.fromkeys(range(6001, 6061), 1),  # the first 60 kiriban, once each
}  # fmt: skip
PREVIOUS_USER_SCORES = {"U1": 1718, "U2": 173, "U3": 210, "U4": 193, "U5": 16, "U6": 40}


@pytest.fixture(scope="module")
def arrivals() -> list[tuple[str, datetime]]:
    """Return the synthetic arrivals."""
    return synthetic_arrivals()


def test_synthetic_data_triggers_every_badge_type(arrivals: list[tuple[str, datetime]]) -> None:
    """Every rule is exercised, so the equivalence check covers all of them."""
    engine = compute(arrivals)
    earned = {BADGE_TYPE[badge_id] for result in engine.results for badge_id in result.badge_ids}
    assert earned == set(BADGE_TYPES_TO_CHECK)


def test_engine_matches_the_previous_implementation(arrivals: list[tuple[str, datetime]]) -> None:
    """Badge counts and final scores equal the previous implementation's on the same arrivals."""
    engine = compute(arrivals)

    assert len(engine.results) == PREVIOUS_ARRIVALS
    assert Counter(badge_id for result in engine.results for badge_id in result.badge_ids) == PREVIOUS_BADGE_COUNTS
    assert {user_id: state.score for user_id, state in engine.users.items()} == PREVIOUS_USER_SCORES


def test_second_arrival_on_the_same_day_is_not_counted() -> None:
    """Only the first arrival of a user's day counts, like insert_arrival_action."""
    engine = BadgeEngine()
    assert engine.add("U1", datetime(2025, 6, 2, 9, 0, tzinfo=JST)) is not None
    assert engine.add("U1", datetime(2025, 6, 2, 10, 0, tzinfo=JST)) is None
    assert engine.add("U2", datetime(2025, 6, 2, 10, 0, tzinfo=JST)).rank == 2


def test_days_follow_jst_whatever_the_input_timezone() -> None:
    """An arrival given in UTC counts on its JST day, and naive times are refused."""
    engine = BadgeEngine()
    engine.add("U1", datetime(2025, 6, 1, 23, 30, tzinfo=UTC))  # 08:30 on 2 June in JST

    assert [arrival.user_id for arrival in engine.arrivals_on(date(2025, 6, 2))] == ["U1"]
    assert engine.arrival_of("U1", date(2025, 6, 2)).time.hour == 8
    with pytest.raises(ValueError, match="timezone-aware"):
        engine.add("U2", datetime(2025, 6, 2, 9, 0))


def test_straight_flash_without_five_business_days_is_no_streak(monkeypatch: pytest.MonkeyPatch) -> None:
    """A two-week window with fewer than five business days ends the streak instead of failing."""
    monkeypatch.setattr("hikarie_bot.engine.list_bizdays", lambda start, _length: [start.date()])
    engine = BadgeEngine()
    for day in range(2, 7):
        result = engine.add("U1", datetime(2025, 6, day, 9, 0, tzinfo=JST))

    assert not {401, 402, 403} & set(result.badge_ids)
