"""Items: their effects in the engine, the pick gate and handlers, and restoring picks from Slack."""

# Times are written naive for brevity and taken as JST.
# ruff: noqa: DTZ001
import json
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from hikarie_bot import __main__ as bot
from hikarie_bot.constants import JST
from hikarie_bot.db_data.items import (
    ALARM_CLOCK,
    DASH_SHOES,
    DICE,
    ID_CARD,
    ITEM_IMAGE_URLS,
    ITEMS,
    OFFER_COUNT,
    OMAMORI,
    TREAT,
    WEEKLY_PASS,
    dice_roll,
    offers,
)
from hikarie_bot.engine import BadgeEngine, ItemPick, compute
from hikarie_bot.modals import ActionID, BlockID, CallbackID, registry_message
from hikarie_bot.models import ItemPickEvent
from hikarie_bot.picks import ALREADY_PICKED, NOT_ARRIVED, NOT_OFFERED
from hikarie_bot.settings import Settings
from hikarie_bot.sync import parse_item_pick, sync_channel
from tests.helpers import only_badge_types

# June 2025 has no public holidays: business days are Mon 2 - Fri 6, Mon 9 - Fri 13, ...


def at(day: int, hour: int = 10, minute: int = 0) -> datetime:
    """Return a JST time in June 2025."""
    return datetime(2025, 6, day, hour, minute).replace(tzinfo=JST)


def run(arrivals: list[tuple[str, datetime]], picks: list[tuple[str, int, str]]) -> BadgeEngine:
    """Run the engine over arrivals (any order) and picks given as (user, June day, item)."""
    return compute(
        sorted(arrivals, key=lambda arrival: arrival[1]),
        [ItemPick(user_id, date(2025, 6, day), item_id) for user_id, day, item_id in picks],
    )


def item_points(engine: BadgeEngine, user_id: str, day: int) -> list[tuple[str, int]]:
    """Return the (item, points) effects of the user's arrival on a June day."""
    arrival = engine.arrival_of(user_id, date(2025, 6, day))
    return [(effect.item_id, effect.points) for effect in arrival.item_effects]


# --- the engine ---


def test_every_item_has_an_image_in_the_repository() -> None:
    """Each card's image is a 128x128 file under assets/items, served by its file name."""
    for item_id, url in ITEM_IMAGE_URLS.items():
        path = Path(__file__).parent.parent / "assets" / "items" / f"{item_id}.png"
        assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", item_id
        assert int.from_bytes(path.read_bytes()[16:20]) == int.from_bytes(path.read_bytes()[20:24]) == 128, item_id
        assert url.endswith(f"/assets/items/{item_id}.png")


def test_every_item_tells_its_points_and_fits_a_radio_option() -> None:
    """The effect says what the item does in points, or that it gives none; the name fits a radio option."""
    for item in ITEMS.values():
        assert item.flavor, item.id
        assert "pt" in item.effect or "ポイントは増えない" in item.effect, item.id
        assert len(f"*{item.name}*") <= 75, item.id


def test_offers_are_three_distinct_items_and_the_same_every_time() -> None:
    """The offers depend only on the user and the day."""
    first = offers("U1", date(2025, 6, 2))
    assert len({item.id for item in first}) == OFFER_COUNT
    assert offers("U1", date(2025, 6, 2)) == first
    assert any(offers(user, date(2025, 6, 2)) != first for user in ("U2", "U3", "U4", "U5"))


@only_badge_types()
def test_a_one_shot_item_acts_on_the_next_arrival_only_however_late() -> None:
    """Not on the day it was picked, then on the next arrival a week later, then never again."""
    engine = run([("U1", at(2, 8)), ("U1", at(9, 8)), ("U1", at(10, 8))], [("U1", 2, ALARM_CLOCK)])

    assert item_points(engine, "U1", 2) == []
    assert item_points(engine, "U1", 9) == [(ALARM_CLOCK, 3)]
    assert engine.arrival_of("U1", date(2025, 6, 9)).score_sum == 3
    assert item_points(engine, "U1", 10) == []
    assert engine.held_item("U1", date(2025, 6, 2)).pick.item_id == ALARM_CLOCK
    assert engine.held_item("U1", date(2025, 6, 5)).pick.item_id == ALARM_CLOCK
    assert engine.held_item("U1", date(2025, 6, 9)) is None


@only_badge_types()
def test_alarm_clock_pays_only_before_nine() -> None:
    """The arrival uses the item either way."""
    engine = run([("U1", at(2)), ("U1", at(3, 9, 0))], [("U1", 2, ALARM_CLOCK)])

    assert item_points(engine, "U1", 3) == [(ALARM_CLOCK, 0)]
    assert engine.held_item("U1", date(2025, 6, 3)) is None


@only_badge_types()
def test_dash_shoes_pay_only_the_fastest_arrival() -> None:
    """Second place gets nothing."""
    engine = run(
        [("U1", at(2)), ("U2", at(2)), ("U1", at(3, 8)), ("U2", at(3, 7)), ("U1", at(4, 7)), ("U2", at(4, 8))],
        [("U1", 2, DASH_SHOES), ("U2", 2, DASH_SHOES)],
    )

    assert item_points(engine, "U1", 3) == [(DASH_SHOES, 0)]
    assert item_points(engine, "U2", 3) == [(DASH_SHOES, 2)]


@only_badge_types()
def test_dice_rolls_the_same_points_on_every_computation() -> None:
    """The roll comes from the user and the day."""
    engine = run([("U1", at(2)), ("U1", at(3))], [("U1", 2, DICE)])

    assert item_points(engine, "U1", 3) == [(DICE, dice_roll("U1", date(2025, 6, 3)))]
    assert {dice_roll(f"U{n}", date(2025, 6, 3)) for n in range(40)} == {0, 1, 2, 3}


@only_badge_types()
def test_weekly_pass_pays_consecutive_arrivals_in_its_five_business_days_up_to_three() -> None:
    """Picked on Fri 6: it acts Mon 9 - Fri 13; a gap pays nothing; at most three points; held until Fri 13."""
    days = [6, 9, 10, 12, 13, 16]
    engine = run([("U1", at(day)) for day in days], [("U1", 6, WEEKLY_PASS)])

    assert item_points(engine, "U1", 6) == []
    assert item_points(engine, "U1", 9) == [(WEEKLY_PASS, 1)]  # Fri 6 is the previous business day
    assert item_points(engine, "U1", 10) == [(WEEKLY_PASS, 1)]
    assert item_points(engine, "U1", 12) == [(WEEKLY_PASS, 0)]  # Wed 11 missed
    assert item_points(engine, "U1", 13) == [(WEEKLY_PASS, 1)]
    assert item_points(engine, "U1", 16) == []
    assert engine.held_item("U1", date(2025, 6, 13)).pick.item_id == WEEKLY_PASS
    assert engine.held_item("U1", date(2025, 6, 16)) is None


@only_badge_types()
def test_weekly_pass_stops_after_three_points() -> None:
    """Five consecutive arrivals in the window pay three points."""
    engine = run([("U1", at(day)) for day in (6, 9, 10, 11, 12, 13)], [("U1", 6, WEEKLY_PASS)])

    assert sum(points for day in (9, 10, 11, 12, 13) for _, points in item_points(engine, "U1", day)) == 3


@only_badge_types()
def test_id_card_shows_in_the_list_during_its_window() -> None:
    """The card follows the name on the days it acts on, and gives no points."""
    engine = run([("U1", at(day)) for day in (2, 3, 10)] + [("U2", at(3, 11))], [("U1", 2, ID_CARD)])

    lines = registry_message(engine.arrivals_on(date(2025, 6, 3)))[3].text.text.splitlines()
    assert lines[1:] == ["*10:00* : <@U1> :identification_card:", "*11:00* : <@U2>"]
    assert item_points(engine, "U1", 3) == [(ID_CARD, 0)]
    assert item_points(engine, "U1", 10) == []  # the window was Tue 3 - Mon 9


@only_badge_types()
def test_treat_pays_the_next_three_arrivals_that_day_but_not_the_giver_or_earlier_ones() -> None:
    """The treat comes with the giver's next arrival."""
    arrivals = [("U1", at(2, 8)), ("U0", at(3, 7)), ("U1", at(3, 8))]
    arrivals += [(f"U{n}", at(3, 8 + n)) for n in range(2, 6)]
    engine = run(arrivals, [("U1", 2, TREAT)])

    assert item_points(engine, "U1", 3) == [(TREAT, 0)]
    assert item_points(engine, "U0", 3) == []
    assert [item_points(engine, f"U{n}", 3) for n in range(2, 6)] == [[(TREAT, 1)]] * 3 + [[]]
    assert engine.arrival_of("U2", date(2025, 6, 3)).item_effects[0].giver == "U1"


@only_badge_types()
def test_items_pay_at_most_three_points_an_arrival() -> None:
    """A dice roll and treats together are capped."""
    givers = ["U1", "U2", "U3"]
    arrivals = [(user, at(2, 8)) for user in [*givers, "U9"]]
    arrivals += [(user, at(3, 8, n)) for n, user in enumerate(givers)] + [("U9", at(3, 9))]
    day = next(day for day in range(3, 30) if dice_roll("U9", date(2025, 6, day)) == 3)
    arrivals = [(user, time.replace(day=day)) if time.day == 3 else (user, time) for user, time in arrivals]
    engine = run(arrivals, [(user, 2, TREAT) for user in givers] + [("U9", 2, DICE)])

    assert item_points(engine, "U9", day) == [(DICE, 3), (TREAT, 0), (TREAT, 0), (TREAT, 0)]


@only_badge_types(4)
def test_omamori_forgives_one_missed_day_of_a_straight_flash() -> None:
    """Mon-Thu, a missed Friday, then Monday: a streak only with an omamori."""
    days = [2, 3, 4, 5, 9]
    arrivals = [("U1", at(day, 9 + n)) for n, day in enumerate(days)]

    assert run(arrivals, []).arrival_of("U1", date(2025, 6, 9)).badge_ids == []
    assert 401 in run(arrivals, [("U1", 5, OMAMORI)]).arrival_of("U1", date(2025, 6, 9)).badge_ids
    # two missed days are too many
    late = [*arrivals[:4], ("U1", at(10, 13))]
    assert run(late, [("U1", 5, OMAMORI)]).arrival_of("U1", date(2025, 6, 10)).badge_ids == []


def test_a_removed_item_no_longer_acts() -> None:
    """A stored pick of an item the code no longer has is ignored."""
    engine = run([("U1", at(2)), ("U1", at(3))], [("U1", 2, "retired_item")])

    assert item_points(engine, "U1", 3) == []
    assert engine.held_item("U1", date(2025, 6, 2)) is None


# --- the button, the modal and the thread ---


@pytest.fixture
def clock() -> Iterator[FrozenDateTimeFactory]:
    """Freeze the clock on Mon 2 June 2025 at 09:10; move it with move_to."""
    with freeze_time(at(2, 9, 10)) as frozen:
        yield frozen


@pytest.fixture
def database(app_database: Engine, settings: Settings, clock: FrozenDateTimeFactory) -> Engine:
    """Give the handlers a fresh database and a frozen clock."""
    settings.bot_id = "B0BOT"
    return app_database


def post_ts(day: int) -> str:
    """Return the ts of the daily post of a June day."""
    return f"{at(day, 6).timestamp():.6f}"


def press(user_id: str, day: int, action_id: str) -> dict[str, Any]:
    """Return a block action payload for a button on the daily post of a June day."""
    return {
        "user": {"id": user_id},
        "channel": {"id": "C0OUT"},
        "actions": [{"action_id": action_id}],
        "message": {"ts": post_ts(day)},
        "trigger_id": "T0TRIGGER",
    }


def submission(user_id: str, item_id: str, private_metadata: str) -> dict[str, Any]:
    """Return a view submission payload picking an item."""
    values = {BlockID.ITEM_CHOICE: {ActionID.ITEM_CHOICE: {"selected_option": {"value": item_id}}}}
    return {"user": {"id": user_id}, "view": {"private_metadata": private_metadata, "state": {"values": values}}}


def slack() -> AsyncMock:
    """Return a Slack client whose posts get increasing ts."""
    client = AsyncMock()
    counter = iter(range(100, 1000))
    client.chat_postMessage.side_effect = lambda **_: {"ok": True, "ts": f"1748822999.000{next(counter)}"}
    return client


async def arrive(client: AsyncMock, user_id: str, day: int) -> None:
    """Press the arrival button on the daily post of a June day."""
    await bot.handle_button_click(AsyncMock(), press(user_id, day, ActionID.ARRIVED_OFFICE), client)


async def open_offers(client: AsyncMock, user_id: str, day: int) -> str:
    """Press the item button; return the opened modal's private metadata."""
    await bot.handle_pick_item(AsyncMock(), press(user_id, day, ActionID.PICK_ITEM), client)
    return client.views_open.await_args.kwargs["view"]["private_metadata"]


def picks(database: Engine) -> list[tuple[str, date, str, str | None]]:
    """Return the stored picks."""
    with Session(database) as session:
        return [(pick.user_id, pick.day, pick.item_id, pick.slack_ts) for pick in session.query(ItemPickEvent)]


@pytest.mark.asyncio
async def test_no_item_before_arriving(database: Engine) -> None:
    """The modal does not open before the user's arrival is announced."""
    client = slack()

    await bot.handle_pick_item(AsyncMock(), press("U1", 2, ActionID.PICK_ITEM), client)

    assert client.chat_postEphemeral.await_args.kwargs["text"] == NOT_ARRIVED
    client.views_open.assert_not_awaited()


@pytest.mark.asyncio
async def test_pick_is_stored_and_announced_quietly_in_the_thread(database: Engine) -> None:
    """The offered item is stored, then posted as one line in the daily post's thread with its metadata."""
    client = slack()
    await arrive(client, "U1", 2)
    metadata = await open_offers(client, "U1", 2)
    offered = [item.id for item in offers("U1", date(2025, 6, 2))]
    view = client.views_open.await_args.kwargs["view"]
    assert view["callback_id"] == CallbackID.ITEM_PICK
    cards = [block for block in view["blocks"] if block["type"] == "card"]
    assert [(card["subtitle"]["text"], card["body"]["text"]) for card in cards] == [
        (ITEMS[item_id].flavor, f"効果: {ITEMS[item_id].effect}") for item_id in offered
    ]
    assert [option["value"] for option in view["blocks"][-1]["element"]["options"]] == offered
    ack = AsyncMock()

    await bot.handle_item_submission(ack, submission("U1", offered[1], metadata), client)

    ack.assert_awaited_once_with()
    post = client.chat_postMessage.await_args.kwargs
    assert post["thread_ts"] == post_ts(2)
    assert "reply_broadcast" not in post
    assert [block["type"] for block in post["blocks"]] == ["context"]
    assert ITEMS[offered[1]].name in post["text"]
    assert picks(database) == [("U1", date(2025, 6, 2), offered[1], "1748822999.000101")]  # the second post
    parsed = parse_item_pick({"ts": "1748822999.000101", "bot_id": "B0BOT", "metadata": post["metadata"]})
    assert (parsed.user_id, parsed.day, parsed.item_id) == ("U1", date(2025, 6, 2), offered[1])


@pytest.mark.asyncio
async def test_one_pick_a_day_and_then_the_offers_are_read_only(database: Engine) -> None:
    """After picking, the button opens the day's offers to look at, with the picked one marked."""
    client = slack()
    await arrive(client, "U1", 2)
    metadata = await open_offers(client, "U1", 2)
    await bot.handle_item_submission(
        AsyncMock(), submission("U1", offers("U1", date(2025, 6, 2))[0].id, metadata), client
    )
    client.views_open.reset_mock()

    await bot.handle_pick_item(AsyncMock(), press("U1", 2, ActionID.PICK_ITEM), client)

    view = client.views_open.await_args.kwargs["view"]
    assert view["callback_id"] == CallbackID.ITEM_REVIEW
    assert "submit" not in view  # nothing to submit: "閉じる" is the only button
    assert not any(block["type"] == "input" for block in view["blocks"])
    titles = [block["title"]["text"] for block in view["blocks"] if block["type"] == "card"]
    assert [title.endswith("獲得済み") for title in titles] == [True, False, False]
    # a modal left open from before cannot pick a second item either
    ack = AsyncMock()
    await bot.handle_item_submission(ack, submission("U1", offers("U1", date(2025, 6, 2))[1].id, metadata), client)
    assert ack.await_args.kwargs["errors"] == {BlockID.ITEM_CHOICE: ALREADY_PICKED}
    assert len(picks(database)) == 1


@pytest.mark.asyncio
async def test_holding_an_item_shows_the_offers_without_a_pick(database: Engine, clock: FrozenDateTimeFactory) -> None:
    """A weekly pass is held for five business days: the next day's offers can be looked at, not picked."""
    client = slack()
    await arrive(client, "U1", 2)
    with Session(database) as session:  # store a weekly pass, as if it had been offered and picked
        session.add(ItemPickEvent(user_id="U1", day=date(2025, 6, 2), item_id=WEEKLY_PASS, occurred_at=at(2, 9, 10)))
        session.commit()
    clock.move_to(at(3, 9, 0))
    await arrive(client, "U1", 3)

    await bot.handle_pick_item(AsyncMock(), press("U1", 3, ActionID.PICK_ITEM), client)

    view = client.views_open.await_args.kwargs["view"]
    assert view["callback_id"] == CallbackID.ITEM_REVIEW
    notice = view["blocks"][0]["text"]["text"]
    assert "週間パス" in notice
    assert "06/09まで" in notice
    assert len([block for block in view["blocks"] if block["type"] == "card"]) == 3
    # nor can a submission get around it
    ack = AsyncMock()
    metadata = json.dumps({"channel": "C0OUT", "thread_ts": post_ts(3), "day": "2025-06-03"})
    await bot.handle_item_submission(ack, submission("U1", offers("U1", date(2025, 6, 3))[0].id, metadata), client)
    assert ack.await_args.kwargs["response_action"] == "errors"


@pytest.mark.asyncio
async def test_an_item_that_was_not_offered_is_refused(database: Engine) -> None:
    """The submission is checked against today's offers."""
    client = slack()
    await arrive(client, "U1", 2)
    metadata = await open_offers(client, "U1", 2)
    offered = {item.id for item in offers("U1", date(2025, 6, 2))}
    other = next(item_id for item_id in ITEMS if item_id not in offered)
    ack = AsyncMock()

    await bot.handle_item_submission(ack, submission("U1", other, metadata), client)

    assert ack.await_args.kwargs == {"response_action": "errors", "errors": {BlockID.ITEM_CHOICE: NOT_OFFERED}}
    assert picks(database) == []


@pytest.mark.asyncio
async def test_a_modal_submitted_the_next_day_is_refused(database: Engine, clock: FrozenDateTimeFactory) -> None:
    """The offers belong to the day the modal opened."""
    client = slack()
    await arrive(client, "U1", 2)
    metadata = await open_offers(client, "U1", 2)
    clock.move_to(at(3, 0, 5))
    ack = AsyncMock()

    await bot.handle_item_submission(ack, submission("U1", offers("U1", date(2025, 6, 2))[0].id, metadata), client)

    assert ack.await_args.kwargs["response_action"] == "errors"
    assert picks(database) == []


@pytest.mark.asyncio
async def test_a_pick_whose_announcement_failed_is_announced_on_the_next_press(database: Engine) -> None:
    """Like an arrival, the pick stays stored and the button posts it again."""
    client = slack()
    await arrive(client, "U1", 2)
    metadata = await open_offers(client, "U1", 2)
    item_id = offers("U1", date(2025, 6, 2))[0].id
    client.chat_postMessage.side_effect = RuntimeError("slack is down")
    with pytest.raises(RuntimeError):
        await bot.handle_item_submission(AsyncMock(), submission("U1", item_id, metadata), client)
    assert picks(database)[0][3] is None

    client.chat_postMessage.side_effect = None
    client.chat_postMessage.return_value = {"ok": True, "ts": "1748822999.000900"}
    client.views_open.reset_mock()
    await bot.handle_pick_item(AsyncMock(), press("U1", 2, ActionID.PICK_ITEM), client)

    client.views_open.assert_not_awaited()
    assert picks(database) == [("U1", date(2025, 6, 2), item_id, "1748822999.000900")]
    assert client.chat_postMessage.await_args.kwargs["metadata"]["event_payload"]["item_id"] == item_id


# --- restoring from Slack ---


class ThreadSource:
    """A channel with one daily post whose thread holds an arrival and a pick."""

    def __init__(self, replies: list[dict[str, Any]]) -> None:
        """Keep the replies."""
        self.replies_ = replies

    async def history(self, _channel: str) -> AsyncIterator[dict[str, Any]]:
        """Yield the daily post."""
        yield {"ts": post_ts(2), "bot_id": "B0BOT", "reply_count": len(self.replies_), "text": "高輪に出社してる？"}

    async def replies(self, _channel: str, _ts: str) -> list[dict[str, Any]]:
        """Return the parent and the replies."""
        return [{"ts": post_ts(2)}, *self.replies_]


@pytest.mark.asyncio
async def test_sync_restores_picks_once(app_database: Engine, settings: Settings) -> None:
    """The pick's metadata in the thread is read back into item_pick_event; a second sync adds nothing."""
    settings.bot_id = "B0BOT"
    with freeze_time(at(2, 9, 10)):
        client = slack()
        await arrive(client, "U1", 2)
        metadata = await open_offers(client, "U1", 2)
        item_id = offers("U1", date(2025, 6, 2))[0].id
        await bot.handle_item_submission(AsyncMock(), submission("U1", item_id, metadata), client)
    posts = [call.kwargs for call in client.chat_postMessage.await_args_list]
    replies = [
        {"ts": f"{at(2, 9, 10 + n).timestamp():.6f}", "bot_id": "B0BOT", "metadata": post["metadata"], "text": ""}
        for n, post in enumerate(posts)
    ]
    with Session(app_database) as session:
        session.query(ItemPickEvent).delete()
        session.commit()

        first = await sync_channel(session, ThreadSource(replies), "C0OUT")
        second = await sync_channel(session, ThreadSource(replies), "C0OUT")

        assert (first.picks_inserted, second.picks_inserted) == (1, 0)
        pick = session.query(ItemPickEvent).one()
        assert (pick.user_id, pick.day, pick.item_id) == ("U1", date(2025, 6, 2), item_id)
        assert pick.occurred_at == at(2, 9, 10).astimezone(UTC)
