"""Decide whether a user may pick an item today, and record the pick.

A user may pick once a JST day, after their arrival that day is announced, and only while they
hold no item (db_data/items.py). The three items offered are derived from the user and the day,
so only the pick is stored. Like an arrival, a pick is stored before it is announced in the
thread; one whose announcement was never posted is announced again on the next press.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from hikarie_bot.arrivals import compute_arrivals
from hikarie_bot.constants import JST
from hikarie_bot.db_data.items import ITEMS, ItemData, offers
from hikarie_bot.models import ArrivalEvent, ItemPickEvent

NOT_ARRIVED = "アイテムは、今日の出社登録のあとに選べます"
ALREADY_PICKED = "今日のアイテムは獲得済みです"
NOT_OFFERED = "そのアイテムは今日の候補にありません。選び直してください"


@dataclass
class StoredPick:
    """A stored pick, detached from the session."""

    id: int
    user_id: str
    day: date
    item_id: str
    occurred_at: datetime

    @property
    def item(self) -> ItemData:
        """Return the picked item."""
        return ITEMS[self.item_id]


@dataclass
class PickGate:
    """Whether the user may pick today: the offers, why not, or a pick still to announce."""

    offers: list[ItemData] = field(default_factory=list)
    refusal: str | None = None
    unannounced: StoredPick | None = None


def _detach(event: ItemPickEvent) -> StoredPick:
    return StoredPick(event.id, event.user_id, event.day, event.item_id, event.occurred_at)


def held_refusal(held_item_id: str, last_day: date | None) -> str:
    """Return why a user who holds an item cannot pick another."""
    item = ITEMS[held_item_id]
    until = f"（{last_day:%m/%d}まで有効）" if last_day else "（次の出社で使います）"
    return f"まだ {item.label} を持っています{until}。アイテムは1つまでです"


def pick_gate(session: Session, user_id: str, now: datetime) -> PickGate:
    """Check whether the user may pick an item on the JST day of `now`."""
    day = now.astimezone(JST).date()
    start_of_day = datetime.combine(day, datetime.min.time(), tzinfo=JST)
    announced = session.scalar(
        select(ArrivalEvent.id)
        .where(ArrivalEvent.user_id == user_id)
        .where(ArrivalEvent.occurred_at >= start_of_day)
        .where(ArrivalEvent.occurred_at < start_of_day + timedelta(days=1))
        .where(ArrivalEvent.slack_ts.is_not(None))
        .limit(1)
    )
    if announced is None:
        return PickGate(refusal=NOT_ARRIVED)
    picked = session.scalar(select(ItemPickEvent).where(ItemPickEvent.user_id == user_id, ItemPickEvent.day == day))
    if picked is not None:
        if picked.slack_ts is None:
            return PickGate(unannounced=_detach(picked))
        return PickGate(refusal=ALREADY_PICKED)
    held = compute_arrivals(session).held_item(user_id, day)
    if held is not None:
        return PickGate(refusal=held_refusal(held.pick.item_id, held.last_day))
    return PickGate(offers=offers(user_id, day))


def record_pick(session: Session, user_id: str, item_id: str, now: datetime) -> PickGate:
    """Store the pick if the user may pick it now; the gate holds the stored pick as unannounced."""
    gate = pick_gate(session, user_id, now)
    if gate.refusal or gate.unannounced:
        return PickGate(refusal=gate.refusal or ALREADY_PICKED)
    if item_id not in {item.id for item in gate.offers}:
        return PickGate(refusal=NOT_OFFERED)
    event = ItemPickEvent(user_id=user_id, day=now.astimezone(JST).date(), item_id=item_id, occurred_at=now)
    session.add(event)
    try:
        session.commit()
    except IntegrityError:  # picked in another process at the same moment
        session.rollback()
        return PickGate(refusal=ALREADY_PICKED)
    return PickGate(unannounced=_detach(event))


def attach_pick_ts(session: Session, pick_id: int, slack_ts: str) -> None:
    """Link a pick to its announcement: it then counts as announced, and a sync does not store it twice."""
    event = session.get(ItemPickEvent, pick_id)
    if event is not None and event.slack_ts is None:
        event.slack_ts = slack_ts
        session.commit()
