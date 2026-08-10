"""Small helpers to describe badge test scenarios as plain data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hikarie_bot.curd import insert_arrival_action
from hikarie_bot.db_data.badges import BadgeChecker

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from hikarie_bot.models import Badge


def to_datetime(value: str | datetime) -> datetime:
    """Parse a loosely written JST datetime used in test scenarios."""
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


@dataclass(frozen=True)
class Arrival:
    """A single arrival registration."""

    at: str | datetime
    user: str

    @property
    def jst_datetime(self) -> datetime:
        """Return the arrival time as a datetime."""
        return to_datetime(self.at)


@dataclass(frozen=True)
class Expectation:
    """Badges expected for a user on a given date."""

    on: str | datetime
    user: str
    badge_ids: list[int] = field(default_factory=list)

    @property
    def target_date(self) -> datetime:
        """Return the checked date as a datetime."""
        return to_datetime(self.on)


@dataclass(frozen=True)
class BadgeScenario:
    """A declarative badge checking scenario.

    ``arrivals`` are registered in order, then every ``expectations`` entry is
    verified against ``check`` (a ``BadgeChecker`` method name) and, when
    ``also_check_all`` is set, against ``BadgeChecker.check``.
    """

    id: str
    badge_types: list[int]
    check: str
    arrivals: list[Arrival]
    expectations: list[Expectation]
    also_check_all: bool = False


def daily(
    user: str, start: str, days: int, *, step: timedelta | None = None
) -> list[Arrival]:
    """Build consecutive arrivals for a single user."""
    begin = to_datetime(start)
    delta = step if step is not None else timedelta(days=1)
    return [Arrival(at=begin + delta * i, user=user) for i in range(days)]


def arrive(session: Session, at: str | datetime, user: str) -> None:
    """Register a single arrival, e.g. ``arrive(session, "2024-01-01 06:00", "u")``."""
    insert_arrival_action(
        session=session,
        jst_datetime=to_datetime(at),
        user_id=user,
    )


def resolve_badges(session: Session, badge_ids: list[int]) -> list[Badge]:
    """Resolve badge ids into badge rows."""
    return [
        BadgeChecker.get_badge(session=session, badge_id=badge_id)
        for badge_id in badge_ids
    ]


def register_arrivals(session: Session, arrivals: list[Arrival]) -> None:
    """Insert every arrival of a scenario."""
    for arrival in arrivals:
        insert_arrival_action(
            session=session,
            jst_datetime=arrival.jst_datetime,
            user_id=arrival.user,
        )


def run_badge_scenario(session: Session, scenario: BadgeScenario) -> None:
    """Run a declarative badge scenario and assert every expectation."""
    checker = BadgeChecker(badge_type_to_check=scenario.badge_types)
    check_one = getattr(checker, scenario.check)

    register_arrivals(session, scenario.arrivals)

    for expectation in scenario.expectations:
        expected = resolve_badges(session, expectation.badge_ids)
        where = f"{scenario.id}: {expectation.user} on {expectation.on}"

        actual = check_one(
            session=session,
            user_id=expectation.user,
            target_date=expectation.target_date,
        )
        assert actual == expected, (
            f"{where} via {scenario.check}: "
            f"expected {[b.id for b in expected]}, got {[b.id for b in actual]}"
        )

        if scenario.also_check_all:
            actual_all = checker.check(
                session=session,
                user_id=expectation.user,
                target_date=expectation.target_date,
            )
            assert actual_all == expected, (
                f"{where} via check(): "
                f"expected {[b.id for b in expected]}, got {[b.id for b in actual_all]}"
            )
