# The engine works on naive JST wall-clock times, as the derived tables store them.
# ruff: noqa: DTZ001
import random
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hikarie_bot.constants import BADGE_TYPES_TO_CHECK
from hikarie_bot.curd import insert_arrival_action
from hikarie_bot.db_data import Badges
from hikarie_bot.engine import BadgeEngine, compute
from hikarie_bot.migrations import init_database
from hikarie_bot.models import Achievement, GuestArrivalInfo, User, UserBadge
from hikarie_bot.utils import is_jp_bizday

JST = ZoneInfo("Asia/Tokyo")
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
    return sorted(arrivals + special, key=lambda arrival: arrival[1])


def replay_with_insert_arrival_action(arrivals: list[tuple[str, datetime]]) -> Session:
    """Build the derived tables the way the bot did before the engine."""
    engine = create_engine("sqlite://")
    init_database(engine)
    session = Session(engine)
    for user_id, moment in arrivals:
        insert_arrival_action(session, moment.replace(tzinfo=JST), user_id)
    return session


@pytest.fixture(scope="module")
def arrivals() -> list[tuple[str, datetime]]:
    """Return the synthetic arrivals."""
    return synthetic_arrivals()


@pytest.fixture(scope="module")
def reference(arrivals: list[tuple[str, datetime]]) -> Session:
    """Return the derived tables built by the previous implementation."""
    return replay_with_insert_arrival_action(arrivals)


def test_synthetic_data_triggers_every_badge_type(arrivals: list[tuple[str, datetime]]) -> None:
    """Every rule is exercised, so the equivalence check covers all of them."""
    engine = compute(arrivals)
    earned = {BADGE_TYPE[badge_id] for result in engine.results for badge_id in result.badge_ids}
    assert earned == set(BADGE_TYPES_TO_CHECK)


def test_engine_matches_insert_arrival_action(arrivals: list[tuple[str, datetime]], reference: Session) -> None:
    """Ranks, badges, scores and badge tallies equal the previous implementation's."""
    engine = compute(arrivals)

    expected_arrivals = [
        (a.user_id, a.arrival_time, a.arrival_rank, a.acquired_score_sum)
        for a in reference.query(GuestArrivalInfo).order_by(GuestArrivalInfo.id)
    ]
    assert [(r.user_id, r.time, r.rank, r.score_sum) for r in engine.results] == expected_arrivals

    expected_badges = sorted(
        (a.user_id, a.arrival.arrival_time, a.badge_id) for a in reference.query(Achievement).join(Achievement.arrival)
    )
    assert sorted((r.user_id, r.time, b) for r in engine.results for b in r.badge_ids) == expected_badges

    assert {u: s.score for u, s in engine.users.items()} == {u.id: u.current_score for u in reference.query(User)}
    assert {(u, b): (t.count, t.first, t.last) for (u, b), t in engine.user_badges.items()} == {
        (ub.user_id, ub.badge_id): (ub.count, ub.initially_acquired_datetime, ub.last_acquired_datetime)
        for ub in reference.query(UserBadge)
    }


def test_second_arrival_on_the_same_day_is_not_counted() -> None:
    """Only the first arrival of a user's day counts, like insert_arrival_action."""
    engine = BadgeEngine()
    assert engine.add("U1", datetime(2025, 6, 2, 9, 0)) is not None
    assert engine.add("U1", datetime(2025, 6, 2, 10, 0)) is None
    assert engine.add("U2", datetime(2025, 6, 2, 10, 0)).rank == 2
