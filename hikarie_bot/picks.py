"""Decide whether a user may pick an item today, and record the pick.

A user may pick once a JST day, after their arrival that day is announced, and only while they
hold no item (db_data/items.py). After picking, or while holding an item, they can still look at
the day's offers. The three items offered are derived from the user and the day, so only the
pick is stored. Like an arrival, a pick is stored before it is announced in the thread; one whose
announcement was never posted is announced again on the next press.
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
    """What the user may do today.

    - refusal: they may not even look (not arrived yet, or a pick that cannot be stored);
    - unannounced: a stored pick whose announcement is still to be posted;
    - notice: they may look at the offers but not pick (picked today, or holding an item);
    - otherwise they may pick one of the offers.
    """

    offers: list[ItemData] = field(default_factory=list)
    refusal: str | None = None
    notice: str | None = None
    picked_item_id: str | None = None
    unannounced: StoredPick | None = None


def _detach(event: ItemPickEvent) -> StoredPick:
    return StoredPick(event.id, event.user_id, event.day, event.item_id, event.occurred_at)


def held_notice(held_item_id: str, last_day: date | None) -> str:
    """Return why a user who holds an item cannot pick another today."""
    item = ITEMS[held_item_id]
    until = f"{last_day:%m/%d}まで有効" if last_day else "次の出社で使います"
    return f"まだ *{item.name}* を持っているので、今日は選べません（{until}）。今日の候補は見るだけです。"


def picked_notice(item_id: str) -> str:
    """Return the notice of the item picked today."""
    return f"今日は *{ITEMS[item_id].name}* を獲得しました。効果は次の出社から発動します。"


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
    offered = offers(user_id, day)
    picked = session.scalar(select(ItemPickEvent).where(ItemPickEvent.user_id == user_id, ItemPickEvent.day == day))
    if picked is not None:
        if picked.slack_ts is None:
            return PickGate(unannounced=_detach(picked))
        notice = picked_notice(picked.item_id) if picked.item_id in ITEMS else ALREADY_PICKED
        return PickGate(offers=offered, notice=notice, picked_item_id=picked.item_id)
    held = compute_arrivals(session).held_item(user_id, day)
    if held is not None:
        return PickGate(offers=offered, notice=held_notice(held.pick.item_id, held.last_day))
    return PickGate(offers=offered)


def record_pick(session: Session, user_id: str, item_id: str, now: datetime) -> PickGate:
    """Store the pick if the user may pick it now; the gate holds the stored pick as unannounced."""
    gate = pick_gate(session, user_id, now)
    if gate.refusal or gate.notice or gate.unannounced:
        return PickGate(
            refusal=gate.refusal or (ALREADY_PICKED if gate.picked_item_id or gate.unannounced else gate.notice)
        )
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
