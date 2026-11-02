"""Record arrivals reported with the Slack button as arrival events."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from hikarie_bot.engine import JST
from hikarie_bot.models import ArrivalEvent


def record_button_arrival(session: Session, user_id: str, pressed_at: datetime) -> ArrivalEvent | None:
    """Return the user's arrival that JST day to announce, storing the press if there is none.

    Returns None once the arrival is announced (linked to a Slack post). An arrival whose
    announcement was never posted is returned again, so pressing again retries it.
    """
    start_of_day = pressed_at.astimezone(JST).replace(hour=0, minute=0, second=0, microsecond=0)
    event = session.scalar(
        select(ArrivalEvent)
        .where(ArrivalEvent.user_id == user_id)
        .where(ArrivalEvent.occurred_at >= start_of_day)
        .where(ArrivalEvent.occurred_at < start_of_day + timedelta(days=1))
        .order_by(ArrivalEvent.occurred_at)
        .limit(1)
    )
    if event is None:
        event = ArrivalEvent(user_id=user_id, occurred_at=pressed_at, source="button")
        session.add(event)
        session.commit()
    return event if event.slack_ts is None else None


def attach_slack_ts(session: Session, event_id: int, slack_ts: str) -> None:
    """Link an arrival to its announcement: it then counts as announced, and a sync does not store it twice."""
    event = session.get(ArrivalEvent, event_id)
    if event is not None and event.slack_ts is None:
        event.slack_ts = slack_ts
        session.commit()
