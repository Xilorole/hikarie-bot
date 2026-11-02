"""Shared test helpers."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from unittest import mock

from hikarie_bot.engine import BadgeEngine, compute


def compute_in_order(*arrivals: tuple[str, datetime]) -> BadgeEngine:
    """Run the engine over (user_id, aware time) pairs given in any order."""
    return compute(sorted(arrivals, key=lambda arrival: arrival[1]))


@contextmanager
def only_badge_types(*type_ids: int) -> Iterator[None]:
    """Make the bot award only these badge types (usable as a decorator or a context manager)."""
    checkers = {type_id: checker for type_id, checker in BadgeEngine.CHECKERS.items() if type_id in type_ids}
    with mock.patch.object(BadgeEngine, "CHECKERS", checkers):
        yield
