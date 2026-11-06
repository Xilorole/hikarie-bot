"""Decide whether a user may be reborn now, and record the rebirth (docs/design/rebirth.md).

A rebirth is the user's choice, so it is stored; its level and multiplier are computed by the engine. Like
an item pick, it is stored before it is announced in today's daily post's thread, and one whose
announcement was never posted is announced again on the next press.
"""

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from hikarie_bot.arrivals import compute_arrivals
from hikarie_bot.constants import JST
from hikarie_bot.engine import RebirthStatus
from hikarie_bot.models import RebirthEvent

REBORN_TODAY = "今日はもう転生しました。次の転生は明日からできます"


@dataclass
class StoredRebirth:
    """A stored rebirth, detached from the session."""

    id: int
    user_id: str
    day: date
    occurred_at: datetime


@dataclass
class RebirthGate:
    """What a press of the rebirth button does: a refusal, or the stored rebirth to announce."""

    refusal: str | None = None
    unannounced: StoredRebirth | None = None


def not_yet(status: RebirthStatus) -> str:
    """Return why the user cannot be reborn yet."""
    return f"転生は Lv{status.required_level} からできます（あと {status.points_to_go}pt）"


def record_rebirth(session: Session, user_id: str, now: datetime) -> RebirthGate:
    """Store the rebirth if the user may be reborn now; an unannounced one of today is returned to announce again."""
    day = now.astimezone(JST).date()
    today = session.scalar(select(RebirthEvent).where(RebirthEvent.user_id == user_id, RebirthEvent.day == day))
    if today is not None:
        if today.slack_ts is None:
            return RebirthGate(unannounced=StoredRebirth(today.id, user_id, day, today.occurred_at))
        return RebirthGate(refusal=REBORN_TODAY)
    status = compute_arrivals(session).rebirth_status(user_id, now)
    if not status.can:
        return RebirthGate(refusal=REBORN_TODAY if status.reborn_today else not_yet(status))
    event = RebirthEvent(user_id=user_id, day=day, occurred_at=now)
    session.add(event)
    try:
        session.commit()
    except IntegrityError:  # reborn in another process at the same moment
        session.rollback()
        return RebirthGate(refusal=REBORN_TODAY)
    return RebirthGate(unannounced=StoredRebirth(event.id, user_id, day, event.occurred_at))


def attach_rebirth_ts(session: Session, rebirth_id: int, slack_ts: str) -> None:
    """Link a rebirth to its announcement, so a sync does not store it twice."""
    event = session.get(RebirthEvent, rebirth_id)
    if event is not None and event.slack_ts is None:
        event.slack_ts = slack_ts
        session.commit()
