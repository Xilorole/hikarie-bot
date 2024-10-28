import asyncio
import logging
from contextlib import suppress
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time
from loguru import logger
from pytest_mock import MockerFixture

from hikarie_bot.slack_helper import MessageFilter, send_daily_message

logging.basicConfig(level=logging.DEBUG)


def test_filter(mocker: MockerFixture) -> None:
    """Test the message filter."""
    # temporarily override the environment variables
    mocker.patch("hikarie_bot.slack_helper.BOT_ID", "test_bot_id")
    mocker.patch("hikarie_bot.slack_helper.V1_BOT_ID", "test_v1_bot_id")

    message = {
        "user": "test_user",
        "bot_id": "test_v1_bot_id",
        "text": "ヒカリエは正義 :hikarie:¥n"
        "本日の最速出社申告ユーザ:<@USRIDTST0123> @ 9:00",
    }
    assert MessageFilter.run(message) is True

    message = {
        "user": "TST",
        "bot_id": "test_bot_id",
        "text": "<@USRIDTST0123> clicked *出社してる*",
    }
    assert MessageFilter.run(message) is False

    message = {
        "user": "TST",
        "bot_id": "test_bot_id",
        "text": "ヒカリエは正義 :hikarie:¥n"
        "本日の最速出社申告ユーザ:<@USRIDTST0123> @ 9:00",
    }
    assert MessageFilter.run(message) is True


@pytest.mark.asyncio
async def test_send_daily_message(mocker: MockerFixture) -> None:
    """Test the daily message sending function."""
    mocker.patch("hikarie_bot.slack_helper.OUTPUT_CHANNEL", "test_channel")
    mocker.patch("hikarie_bot.slack_helper.BOT_ID", "test_bot_id")

    # Mock the app.client methods
    mock_app = AsyncMock()
    mock_app.client.conversations_history.return_value = {
        "messages": [{"user": "other_user_id"}]
    }
    mock_app.client.chat_postMessage.return_value = None

    # Freeze time to a specific datetime
    with freeze_time("2023-02-14 06:00:00", tz_offset=-9, real_asyncio=True):
        # Run the function in a background task
        task = asyncio.create_task(send_daily_message(mock_app, check_interval=1))
        await asyncio.sleep(0.01)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

        # Assertions
        mock_app.client.conversations_history.assert_called_once()
        mock_app.client.chat_postMessage.assert_called_once_with(
            channel="test_channel",
            blocks=mock_app.client.chat_postMessage.call_args[1]["blocks"],
            text=mock_app.client.chat_postMessage.call_args[1]["text"],
        )


@pytest.mark.asyncio
async def test_not_sending_message_on_holiday(mocker: MockerFixture) -> None:
    """Test the daily message sending function."""
    # Mock environment variables
    mocker.patch("hikarie_bot.slack_helper.OUTPUT_CHANNEL", "test_channel")
    mocker.patch("hikarie_bot.slack_helper.BOT_ID", "test_bot_id")

    # Mock the app.client methods
    mock_app = AsyncMock()
    mock_app.client.conversations_history.return_value = {
        "messages": [{"user": "other_user_id"}]
    }
    mock_app.client.chat_postMessage.return_value = None

    # Freeze time to a specific datetime
    with freeze_time("2024-02-12 06:00:00", tz_offset=-9, real_asyncio=True):
        # Monday and holiday
        # Run the function in a background task
        logger.info("Starting the task")
        task = asyncio.create_task(send_daily_message(mock_app, check_interval=1))
        logger.info("Task started")
        # Allow some time for the function to run
        await asyncio.sleep(0.01)
        logger.info("Task finished")
        # Cancel the task to stop the infinite loop
        task.cancel()
        logger.info("Task cancelled")

        with suppress(asyncio.CancelledError):
            await task

        # aseert the conversation history is not called
        mock_app.client.conversations_history.assert_not_called()
        mock_app.client.chat_postMessage.assert_not_called()


@pytest.mark.asyncio
async def test_not_sending_message_0559_and_0601(mocker: MockerFixture) -> None:
    """Test the daily message sending function."""
    # Mock environment variables
    mocker.patch("hikarie_bot.slack_helper.OUTPUT_CHANNEL", "test_channel")
    mocker.patch("hikarie_bot.slack_helper.BOT_ID", "test_bot_id")

    # Mock the app.client methods
    mock_app = AsyncMock()
    mock_app.client.conversations_history.return_value = {
        "messages": [{"user": "other_user_id"}]
    }
    mock_app.client.chat_postMessage.return_value = None

    # Freeze time to a specific datetime
    with freeze_time("2024-02-13 06:01:00", tz_offset=-9, real_asyncio=True):
        # Monday and holiday
        # Run the function in a background task
        logger.info("Starting the task")
        task = asyncio.create_task(send_daily_message(mock_app, check_interval=1))
        logger.info("Task started")
        # Allow some time for the function to run
        await asyncio.sleep(0.01)
        logger.info("Task finished")
        # Cancel the task to stop the infinite loop
        task.cancel()
        logger.info("Task cancelled")

        with suppress(asyncio.CancelledError):
            await task

        # aseert the conversation history is not called
        mock_app.client.conversations_history.assert_not_called()
        mock_app.client.chat_postMessage.assert_not_called()

    # 一応再初期化
    mock_app = AsyncMock()
    mock_app.client.conversations_history.return_value = {
        "messages": [{"user": "other_user_id"}]
    }
    mock_app.client.chat_postMessage.return_value = None

    # Freeze time to a specific datetime
    with freeze_time("2024-02-13 05:59:00", tz_offset=-9, real_asyncio=True):
        # Monday and holiday
        # Run the function in a background task
        logger.info("Starting the task")
        task = asyncio.create_task(send_daily_message(mock_app, check_interval=1))
        logger.info("Task started")
        # Allow some time for the function to run
        await asyncio.sleep(0.01)
        logger.info("Task finished")
        # Cancel the task to stop the infinite loop
        task.cancel()
        logger.info("Task cancelled")

        with suppress(asyncio.CancelledError):
            await task

        # aseert the conversation history is not called
        mock_app.client.conversations_history.assert_not_called()
        mock_app.client.chat_postMessage.assert_not_called()
