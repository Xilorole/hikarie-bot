"""Shared test helpers."""

from datetime import datetime

from hikarie_bot.engine import BadgeEngine, compute


def compute_in_order(*arrivals: tuple[str, datetime]) -> BadgeEngine:
    """Run the engine over (user_id, aware time) pairs given in any order."""
    return compute(sorted(arrivals, key=lambda arrival: arrival[1]))
