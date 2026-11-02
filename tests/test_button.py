from datetime import UTC, datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from hikarie_bot import __main__ as bot
from hikarie_bot.arrivals import compute_arrivals
from hikarie_bot.modals import ActionID
from hikarie_bot.models import ArrivalEvent
from hikarie_bot.settings import Settings
from hikarie_bot.sync import parse_arrival

JST = ZoneInfo("Asia/Tokyo")
DAILY_POST = datetime(2025, 6, 2, 6, 0, tzinfo=JST)
PRESSED = datetime(2025, 6, 2, 9, 10, 30, 123456, tzinfo=JST)


@pytest.fixture
def database(app_database: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Engine:
    """Give the handler a fresh database and freeze its clock."""
    monkeypatch.setattr(bot, "get_current_jst_datetime", lambda: PRESSED)
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
async def test_press_outside_the_window_is_rejected(database: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """Presses after 18:00 of the post's day are not recorded."""
    monkeypatch.setattr(bot, "get_current_jst_datetime", lambda: DAILY_POST.replace(hour=18, minute=30))
    client = AsyncMock()

    await bot.handle_button_click(AsyncMock(), click("U1"), client)

    assert "6時から18時" in client.chat_postEphemeral.await_args.kwargs["text"]
    with Session(database) as session:
        assert session.query(ArrivalEvent).count() == 0


@pytest.mark.asyncio
async def test_fastest_comes_from_the_rank_not_the_button(database: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """A second press on the not yet replaced fastest button is announced as a normal arrival."""
    client = AsyncMock()
    client.chat_postMessage.return_value = {"ok": True, "ts": "1748822999.000100"}
    await bot.handle_button_click(AsyncMock(), click("U1", ActionID.FASTEST_ARRIVAL), client)

    monkeypatch.setattr(bot, "get_current_jst_datetime", lambda: PRESSED.replace(second=31))
    client.chat_postMessage.return_value = {"ok": True, "ts": "1748822999.000200"}
    await bot.handle_button_click(AsyncMock(), click("U2", ActionID.FASTEST_ARRIVAL), client)

    post = client.chat_postMessage.await_args.kwargs
    assert post["reply_broadcast"] is False
    assert "最速" not in post["text"]


@pytest.mark.asyncio
async def test_press_again_retries_an_arrival_that_was_not_announced(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the announcement fails, the arrival stays and the next press announces it at its first time."""
    client = AsyncMock()
    client.chat_postMessage.side_effect = RuntimeError("slack is down")
    with pytest.raises(RuntimeError):
        await bot.handle_button_click(AsyncMock(), click("U1"), client)

    monkeypatch.setattr(bot, "get_current_jst_datetime", lambda: PRESSED.replace(minute=20))
    client.chat_postMessage.side_effect = None
    client.chat_postMessage.return_value = {"ok": True, "ts": "1748822999.000100"}
    await bot.handle_button_click(AsyncMock(), click("U1"), client)

    client.chat_postEphemeral.assert_not_awaited()
    with Session(database) as session:
        event = session.query(ArrivalEvent).one()
        assert (event.occurred_at, event.slack_ts) == (PRESSED, "1748822999.000100")
    metadata = client.chat_postMessage.await_args.kwargs["metadata"]
    assert datetime.fromisoformat(metadata["event_payload"]["occurred_at"]) == PRESSED


def test_create_app_routes_actions_to_the_handlers(settings: Settings) -> None:
    """Only creating the app needs the token: importing the bot does not."""
    settings.slack_bot_token = "xoxb-test"  # noqa: S105

    app = bot.create_app()

    assert app.client.token == "xoxb-test"  # noqa: S105
    handlers = {listener.ack_function for listener in app._async_listeners}  # noqa: SLF001
    assert handlers == {bot.handle_button_click, bot.handle_check_achievement, bot.handle_reboot}
