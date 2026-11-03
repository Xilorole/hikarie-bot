from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from hikarie_bot import __main__ as bot
from hikarie_bot.arrivals import compute_arrivals
from hikarie_bot.constants import JST
from hikarie_bot.modals import ActionID
from hikarie_bot.models import ArrivalEvent
from hikarie_bot.settings import Settings
from hikarie_bot.sync import parse_arrival

DAILY_POST = datetime(2025, 6, 2, 6, 0, tzinfo=JST)
PRESSED = datetime(2025, 6, 2, 9, 10, 30, 123456, tzinfo=JST)


@pytest.fixture
def clock() -> Iterator[FrozenDateTimeFactory]:
    """Freeze the clock at the time of the press; move it with move_to."""
    with freeze_time(PRESSED) as frozen:
        yield frozen


@pytest.fixture
def database(app_database: Engine, settings: Settings, clock: FrozenDateTimeFactory) -> Engine:
    """Give the handler a fresh database and a frozen clock."""
    settings.bot_id = "B0BOT"
    return app_database


def click(user_id: str, action_id: str = ActionID.ARRIVED_OFFICE) -> dict:
    """Return a block action payload for a button on today's daily post."""
    return {
        "user": {"id": user_id},
        "channel": {"id": "C0OUT"},
        "actions": [{"action_id": action_id}],
        "message": {"ts": f"{DAILY_POST.timestamp():.6f}"},
    }


@pytest.mark.asyncio
async def test_button_records_an_event_and_announces_it_with_metadata(database: Engine) -> None:
    """A press stores a button event, computes scores, posts with metadata and links the post."""
    client = AsyncMock()
    client.chat_postMessage.return_value = {"ok": True, "ts": "1748822999.000100"}

    await bot.handle_button_click(AsyncMock(), click("U1", ActionID.FASTEST_ARRIVAL), client)

    with Session(database) as session:
        event = session.query(ArrivalEvent).one()
        assert (event.user_id, event.source, event.occurred_at) == ("U1", "button", PRESSED)
        assert event.slack_ts == "1748822999.000100"
        [arrival] = compute_arrivals(session).results
        assert (arrival.user_id, arrival.time, arrival.rank) == ("U1", PRESSED, 1)
        assert arrival.current_score == arrival.score_sum > 0

    post = client.chat_postMessage.await_args.kwargs
    assert post["thread_ts"] == f"{DAILY_POST.timestamp():.6f}"
    assert post["reply_broadcast"] is True
    assert "最速出社登録しました" in post["text"]
    # the post can be read back as the same arrival, with the exact press time
    parsed = parse_arrival({"ts": "1748822999.000100", "bot_id": "B0BOT", "metadata": post["metadata"]})
    assert (parsed.user_id, parsed.occurred_at) == ("U1", PRESSED.astimezone(UTC))
    client.chat_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_second_press_on_the_same_day_is_rejected(database: Engine) -> None:
    """Only the first press of the day counts; the second gets an ephemeral reply."""
    client = AsyncMock()
    client.chat_postMessage.return_value = {"ok": True, "ts": "1748822999.000100"}
    await bot.handle_button_click(AsyncMock(), click("U1"), client)

    await bot.handle_button_click(AsyncMock(), click("U1"), client)

    assert client.chat_postMessage.await_count == 1
    assert "既に出社申告" in client.chat_postEphemeral.await_args.kwargs["text"]
    with Session(database) as session:
        assert session.query(ArrivalEvent).count() == 1


@pytest.mark.asyncio
async def test_press_outside_the_window_is_rejected(database: Engine, clock: FrozenDateTimeFactory) -> None:
    """Presses after 18:00 of the post's day are not recorded."""
    clock.move_to(DAILY_POST.replace(hour=18, minute=30))
    client = AsyncMock()

    await bot.handle_button_click(AsyncMock(), click("U1"), client)

    assert "6時から18時" in client.chat_postEphemeral.await_args.kwargs["text"]
    with Session(database) as session:
        assert session.query(ArrivalEvent).count() == 0


@pytest.mark.asyncio
async def test_fastest_comes_from_the_rank_not_the_button(database: Engine, clock: FrozenDateTimeFactory) -> None:
    """A second press on the not yet replaced fastest button is announced as a normal arrival."""
    client = AsyncMock()
    client.chat_postMessage.return_value = {"ok": True, "ts": "1748822999.000100"}
    await bot.handle_button_click(AsyncMock(), click("U1", ActionID.FASTEST_ARRIVAL), client)

    clock.move_to(PRESSED.replace(second=31))
    client.chat_postMessage.return_value = {"ok": True, "ts": "1748822999.000200"}
    await bot.handle_button_click(AsyncMock(), click("U2", ActionID.FASTEST_ARRIVAL), client)

    post = client.chat_postMessage.await_args.kwargs
    assert post["reply_broadcast"] is False
    assert "最速" not in post["text"]
    assert "本日 2人目の出社です" in post["text"]


@pytest.mark.asyncio
async def test_press_again_retries_an_arrival_that_was_not_announced(
    database: Engine, clock: FrozenDateTimeFactory
) -> None:
    """If the announcement fails, the arrival stays and the next press announces it at its first time."""
    client = AsyncMock()
    client.chat_postMessage.side_effect = RuntimeError("slack is down")
    with pytest.raises(RuntimeError):
        await bot.handle_button_click(AsyncMock(), click("U1"), client)

    clock.move_to(PRESSED.replace(minute=20))
    client.chat_postMessage.side_effect = None
    client.chat_postMessage.return_value = {"ok": True, "ts": "1748822999.000100"}
    await bot.handle_button_click(AsyncMock(), click("U1"), client)

    # no refusal: the only ephemeral message is the next goals
    assert "つぎのもくひょう" in client.chat_postEphemeral.await_args.kwargs["text"]
    with Session(database) as session:
        event = session.query(ArrivalEvent).one()
        assert (event.occurred_at, event.slack_ts) == (PRESSED, "1748822999.000100")
    metadata = client.chat_postMessage.await_args.kwargs["metadata"]
    assert datetime.fromisoformat(metadata["event_payload"]["occurred_at"]) == PRESSED


@pytest.mark.asyncio
async def test_registry_update_happens_while_the_lock_is_held(database: Engine) -> None:
    """The daily post is rewritten before the next press may compute its list, so updates stay in order."""
    client = AsyncMock()
    client.chat_postMessage.return_value = {"ok": True, "ts": "1748822999.000100"}
    held: list[bool] = []

    async def record_lock(**_: object) -> None:
        held.append(bot.ARRIVAL_LOCK.locked())

    client.chat_update.side_effect = record_lock

    await bot.handle_button_click(AsyncMock(), click("U1"), client)

    assert held == [True]
    assert not bot.ARRIVAL_LOCK.locked()


def test_create_app_routes_actions_to_the_handlers(settings: Settings) -> None:
    """Only creating the app needs the token: importing the bot does not."""
    settings.slack_bot_token = "xoxb-test"  # noqa: S105

    app = bot.create_app()

    assert app.client.token == "xoxb-test"  # noqa: S105
    handlers = {listener.ack_function for listener in app._async_listeners}  # noqa: SLF001
    assert handlers == {
        bot.handle_button_click,
        bot.handle_check_achievement,
        bot.handle_pick_item,
        bot.handle_item_submission,
        bot.handle_item_review,
        bot.handle_reboot,
        bot.handle_arrive_shortcut,
    }


def daily_post(ts: datetime = DAILY_POST) -> dict:
    """Return the daily post as conversations.history lists it."""
    return {
        "ts": f"{ts.timestamp():.6f}",
        "bot_id": "B0BOT",
        "blocks": [{"type": "actions", "block_id": "FASTEST_ARRIVAL"}],
    }


def shortcut_client(messages: list[dict]) -> AsyncMock:
    """Return a client whose channel history holds these messages."""
    client = AsyncMock()
    client.views_open.return_value = {"ok": True, "view": {"id": "V1"}}
    client.conversations_history.return_value = {"ok": True, "messages": messages}
    client.chat_postMessage.return_value = {"ok": True, "ts": "1748822999.000100"}
    return client


@pytest.mark.asyncio
async def test_shortcut_records_the_arrival_on_todays_post(database: Engine, settings: Settings) -> None:
    """The global shortcut announces the arrival in the daily post's thread and says so in its modal."""
    settings.output_channel = "C0OUT"
    # a broadcast thread reply is listed in the history too, but is not the daily post
    broadcast = {**daily_post(PRESSED), "thread_ts": f"{DAILY_POST.timestamp():.6f}", "blocks": []}
    client = shortcut_client([broadcast, daily_post()])

    await bot.handle_arrive_shortcut(AsyncMock(), {"user": {"id": "U1"}, "trigger_id": "T1"}, client)

    post = client.chat_postMessage.await_args.kwargs
    assert (post["channel"], post["thread_ts"]) == ("C0OUT", f"{DAILY_POST.timestamp():.6f}")
    client.chat_update.assert_awaited_once()
    reply = client.views_update.await_args.kwargs["view"]["blocks"][0]["text"]["text"]
    assert reply.startswith("出社登録しました")
    assert "*つぎのもくひょう*\n• あと *4回* の出社で「出社登録ビギナー」" in reply
    client.chat_postEphemeral.assert_not_awaited()  # the modal says it all
    with Session(database) as session:
        assert session.query(ArrivalEvent).one().user_id == "U1"


@pytest.mark.asyncio
async def test_shortcut_without_a_daily_post_records_nothing(database: Engine, settings: Settings) -> None:
    """Before the daily post (or on a day off) the modal says so and nothing is stored."""
    settings.output_channel = "C0OUT"
    client = shortcut_client([])

    await bot.handle_arrive_shortcut(AsyncMock(), {"user": {"id": "U1"}, "trigger_id": "T1"}, client)

    assert client.views_update.await_args.kwargs["view"]["blocks"][0]["text"]["text"] == bot.NO_DAILY_POST
    client.chat_postMessage.assert_not_awaited()
    with Session(database) as session:
        assert session.query(ArrivalEvent).count() == 0


@pytest.mark.asyncio
async def test_shortcut_tells_a_second_arrival_it_is_already_recorded(database: Engine, settings: Settings) -> None:
    """A press after the day's arrival gets the same reply as the button, in the modal."""
    settings.output_channel = "C0OUT"
    client = shortcut_client([daily_post()])
    await bot.handle_arrive_shortcut(AsyncMock(), {"user": {"id": "U1"}, "trigger_id": "T1"}, client)

    await bot.handle_arrive_shortcut(AsyncMock(), {"user": {"id": "U1"}, "trigger_id": "T2"}, client)

    assert client.views_update.await_args.kwargs["view"]["blocks"][0]["text"]["text"] == bot.ALREADY_ARRIVED
    assert client.chat_postMessage.await_count == 1


@pytest.mark.asyncio
async def test_next_goals_go_to_the_user_alone_not_the_thread(database: Engine) -> None:
    """The thread post has no goals; the user gets them in an ephemeral message after the announcement."""
    client = AsyncMock()
    client.chat_postMessage.return_value = {"ok": True, "ts": "1748822999.000100"}

    await bot.handle_button_click(AsyncMock(), click("U1"), client)

    assert "つぎのもくひょう" not in client.chat_postMessage.await_args.kwargs["text"]
    ephemeral = client.chat_postEphemeral.await_args.kwargs
    assert (ephemeral["channel"], ephemeral["user"]) == ("C0OUT", "U1")
    assert "あと *4回* の出社で「出社登録ビギナー」" in ephemeral["text"]


@pytest.mark.asyncio
async def test_a_failed_goals_message_does_not_fail_the_press(database: Engine) -> None:
    """The arrival is announced before the goals, so a failure to send them is only logged."""
    client = AsyncMock()
    client.chat_postMessage.return_value = {"ok": True, "ts": "1748822999.000100"}
    client.chat_postEphemeral.side_effect = RuntimeError("slack is down")

    await bot.handle_button_click(AsyncMock(), click("U1"), client)

    client.chat_update.assert_awaited_once()
