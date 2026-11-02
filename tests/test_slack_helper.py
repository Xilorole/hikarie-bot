from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time
from pytest_mock import MockerFixture

from hikarie_bot.engine import JST
from hikarie_bot.slack_helper import DAILY_MESSAGE_TRIGGER, schedule_daily_message, send_daily_message


@pytest.mark.parametrize(
    ("after", "expected"),
    [
        (datetime(2024, 2, 13, 5, 59, tzinfo=JST), datetime(2024, 2, 13, 6, 0, tzinfo=JST)),  # Tuesday
        (datetime(2024, 2, 13, 6, 0, 1, tzinfo=JST), datetime(2024, 2, 14, 6, 0, tzinfo=JST)),
        (datetime(2024, 2, 9, 6, 0, 1, tzinfo=JST), datetime(2024, 2, 12, 6, 0, tzinfo=JST)),  # Friday → Monday
    ],
)
def test_daily_message_runs_on_weekdays_at_six(after: datetime, expected: datetime) -> None:
    """The job fires once a day at 06:00 JST, Monday to Friday."""
    assert DAILY_MESSAGE_TRIGGER.get_next_fire_time(None, after) == expected


@pytest.mark.asyncio
async def test_send_daily_message(mocker: MockerFixture) -> None:
    """The daily question is posted to the output channel."""
    mocker.patch("hikarie_bot.slack_helper.OUTPUT_CHANNEL", "test_channel")
    client = AsyncMock()

    with freeze_time("2023-02-13 21:00:00"):  # 2023-02-14 06:00 JST
        await send_daily_message(client)

    client.chat_postMessage.assert_awaited_once()
    assert client.chat_postMessage.await_args.kwargs["channel"] == "test_channel"


@pytest.mark.asyncio
async def test_not_sending_message_on_holiday() -> None:
    """Nothing is posted on a holiday in Japan."""
    client = AsyncMock()

    with freeze_time("2024-02-11 21:00:00"):  # 2024-02-12 06:00 JST, a substitute holiday
        await send_daily_message(client)

    client.chat_postMessage.assert_not_awaited()


@pytest.mark.asyncio
async def test_schedule_daily_message() -> None:
    """The scheduler runs send_daily_message on the daily trigger."""
    scheduler = schedule_daily_message(AsyncMock())
    try:
        (job,) = scheduler.get_jobs()
        assert (job.func, job.trigger) == (send_daily_message, DAILY_MESSAGE_TRIGGER)
    finally:
        scheduler.shutdown(wait=False)
