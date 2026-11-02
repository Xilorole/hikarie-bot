from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

from hikarie_bot.engine import JST
from hikarie_bot.slack_helper import DAILY_MESSAGE_TRIGGER, schedule_daily_message, send_daily_message


@pytest.mark.parametrize(
    ("after", "expected"),
    [
        (datetime(2024, 2, 13, 5, 59, tzinfo=JST), datetime(2024, 2, 13, 6, 0, tzinfo=JST)),  # Tuesday
        (datetime(2024, 2, 13, 6, 0, 1, tzinfo=JST), datetime(2024, 2, 14, 6, 0, tzinfo=JST)),
        (datetime(2024, 2, 9, 6, 0, 1, tzinfo=JST), datetime(2024, 2, 10, 6, 0, tzinfo=JST)),  # Friday → Saturday
    ],
)
def test_daily_message_runs_every_day_at_six(after: datetime, expected: datetime) -> None:
    """The job fires once a day at 06:00 JST; send_daily_message skips days off."""
    assert DAILY_MESSAGE_TRIGGER.get_next_fire_time(None, after) == expected


@pytest.mark.asyncio
async def test_send_daily_message() -> None:
    """The daily question is posted to the given channel."""
    client = AsyncMock()

    with freeze_time("2023-02-13 21:00:00"):  # 2023-02-14 06:00 JST
        await send_daily_message(client, "test_channel")

    client.chat_postMessage.assert_awaited_once()
    assert client.chat_postMessage.await_args.kwargs["channel"] == "test_channel"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "utc",
    [
        "2024-02-11 21:00:00",  # 2024-02-12, a substitute holiday
        "2024-02-09 21:00:00",  # Saturday
        "2024-12-30 21:00:00",  # Dec 31
        "2025-01-01 21:00:00",  # Jan 2
    ],
)
async def test_not_sending_message_on_days_off(utc: str) -> None:
    """Nothing is posted on weekends, holidays, Dec 31 or Jan 1-3 (06:00 JST of each day)."""
    client = AsyncMock()

    with freeze_time(utc):
        await send_daily_message(client, "test_channel")

    client.chat_postMessage.assert_not_awaited()


@pytest.mark.asyncio
async def test_schedule_daily_message() -> None:
    """The scheduler runs send_daily_message on the daily trigger."""
    client = AsyncMock()
    scheduler = schedule_daily_message(client, "test_channel")
    try:
        (job,) = scheduler.get_jobs()
        assert (job.func, job.trigger, job.args) == (
            send_daily_message,
            DAILY_MESSAGE_TRIGGER,
            (client, "test_channel"),
        )
    finally:
        scheduler.shutdown(wait=False)
