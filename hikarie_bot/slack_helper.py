import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import jpholiday
from loguru import logger
from slack_bolt.app.async_app import AsyncApp

from hikarie_bot.modals import InitialMessage
from hikarie_bot.settings import BOT_ID, OUTPUT_CHANNEL, V1_BOT_ID, V2_BOT_ID
from hikarie_bot.utils import unix_timestamp_to_jst


class Pattern:
    """Class for storing the regular expression patterns used in the Slack app."""

    v1_message = (
        r"<@([A-Z0-9]+)>"
        r"(?!.*\bclicked|\b)"
        r"(?!.*\bクリック|\b)"
        r"(?!.*\b参加しました\b)"
    )
    v2_message = r"ヒカリエに出社してる？"  # noqa: RUF001


class MessageFilter:
    """Class for filtering Slack messages."""

    @classmethod
    def run(cls, message: dict) -> bool:
        """Run the message filters.

        If any of the filters return True, the message passes the filter.

        Parameters
        ----------
        message : dict
            The Slack message to filter.

        Returns
        -------
            bool: True if the message passes ANY filters, False otherwise.

        """
        filters = [
            cls.filter_v1,
            cls.filter_v2,
            cls.filter_v3,
        ]
        return any(filter_func(message) for filter_func in filters)

    @classmethod
    def extract_user_id(cls, message: dict) -> str | None:
        """Extract the user ID from a Slack message.

        Parameters
        ----------
        message : dict
            The Slack message to extract the user ID from.

        Returns
        -------
            str: The user ID if it exists, None otherwise.

        """
        for filter_func in [cls.filter_v1, cls.filter_v2, cls.filter_v3]:
            if user_id := filter_func(message):
                return user_id
        return None

    @classmethod
    def filter_v1(cls, message: dict) -> str | None:
        """Filter question messages from a Slack message.

        Parameters
        ----------
        message : dict
            The Slack message to filter.

        Returns
        -------
            bool: True if the message is a question message, False otherwise.

        Description
        -----------
        This method filters the messages based on the following criteria:
            - The message is sent by the bot.
            - The message includes the mentioned user's ID.

        """
        logger.debug(f"message: {message}, user: {V1_BOT_ID}")
        if (
            message.get("bot_id") == V1_BOT_ID
            and message.get("text")
            and (match := re.search(Pattern.v1_message, message["text"]))
        ):
            return match.group(1)
        return None

    @classmethod
    def filter_v2(cls, message: dict[str, str]) -> str | None:
        """Filter question messages from a Slack message.

        Parameters
        ----------
        message : dict
            The Slack message to filter.

        Returns
        -------
            bool: True if the message is a question message, False otherwise.

        Description
        -----------
        This method filters the messages based on the following criteria:
            - The message is sent by the bot.
            - The message includes the mentioned user's ID.

        """
        logger.debug(f"message: {message}")
        if (
            message.get("bot_id") == V2_BOT_ID
            and message.get("text")
            and (match := re.search(Pattern.v1_message, message["text"]))
        ):
            return match.group(1)
        return None

    @classmethod
    def filter_v3(cls, message: dict[str, str]) -> str | None:
        """Filter question messages from a Slack message.

        Parameters
        ----------
        message : dict
            The Slack message to filter.

        Returns
        -------
            bool: True if the message is a question message, False otherwise.

        Description
        -----------
        This method filters the messages based on the following criteria:
            - The message is sent by the bot.
            - The message includes the mentioned user's ID.

        """
        logger.debug(f"message: {message}, user: {BOT_ID}")
        if (
            message.get("bot_id") == BOT_ID
            and message.get("text")
            and (match := re.search(Pattern.v1_message, message["text"]))
        ):
            return match.group(1)
        return None


async def send_daily_message(
    app: AsyncApp, at_hour: int = 6, at_minute: int = 0, check_interval: int = 5
) -> None:
    "Run task every weekday 06:00 JST."
    # タイムゾーンの生成
    JST = timezone(timedelta(hours=+9), "JST")  # noqa: N806
    channel_id = OUTPUT_CHANNEL

    logger.info("Started task")
    weekday_limit = 5

    while True:
        # check if the time is 06:00 JST
        now = datetime.now(JST)
        next_day = now + timedelta(days=1)
        logger.debug(f"Current time: {now}")
        if (
            now.hour == at_hour
            and now.minute == at_minute
            and now.weekday() < weekday_limit
            and not jpholiday.is_holiday(now.date())
        ):
            logger.info("Attempting to fetch messages")
            # check if the BOT already sent to channel
            logger.debug(f"Channel ID: {channel_id}")
            try:
                messages = await app.client.conversations_history(
                    channel=channel_id,
                    oldest=str(
                        datetime(
                            year=now.year,
                            month=now.month,
                            day=now.day,
                            tzinfo=JST,
                        ).timestamp()
                    ),
                    latest=str(
                        datetime(
                            year=next_day.year,
                            month=next_day.month,
                            day=next_day.day,
                            tzinfo=JST,
                        ).timestamp()
                    ),
                )
                app_user_id = BOT_ID
                logger.debug(f"Messages: {messages['messages']}")
                if any(
                    app_user_id == message.get("user")
                    for message in messages["messages"]
                ):
                    logger.info("Message already sent")
                else:
                    logger.info("Sending message to channel")
                    try:
                        await app.client.chat_postMessage(
                            channel=OUTPUT_CHANNEL,
                            blocks=InitialMessage().render(),
                            text=InitialMessage().to_text(),
                        )
                        logger.info("Message sent")
                    except Exception as e:  # noqa: BLE001
                        logger.error(f"Error sending message: {e}")

            except Exception as e:  # noqa: BLE001
                logger.error(f"Unexpected error fetching conversation history: {e}")
                await asyncio.sleep(check_interval)
                continue

        else:
            logger.debug("Conditions not met for sending message")
        logger.debug("Sleeping for check_interval")
        await asyncio.sleep(check_interval)
        logger.debug("Woke up from sleep")


async def get_messages(app: AsyncApp) -> list[dict[str, Any]]:
    """Get messages from a Slack channel.

    Parameters
    ----------
    app : AsyncApp
        The Slack application instance used to interact with the Slack API.
    channel_id : str
        The ID of the Slack channel to fetch the messages from.

    Returns
    -------
    list[dict]
        The list of messages from the Slack channel.

    """
    messages: list[dict[str, Any]] = []

    _messages = await app.client.conversations_history(
        channel=OUTPUT_CHANNEL,
        oldest="1651363200",  # 2022-05-01 00:00:00
    )
    messages += _messages["messages"]
    while _messages["has_more"]:
        jst_message_datetime = unix_timestamp_to_jst(
            float(_messages["messages"][-1]["ts"])
        )
        logger.info(f"loading. latest message: {jst_message_datetime}")
        _messages = await app.client.conversations_history(
            channel=OUTPUT_CHANNEL,
            cursor=_messages["response_metadata"]["next_cursor"],
            oldest="1651363200",  # 2022-05-01 00:00:00
        )
        messages += _messages["messages"]
        await asyncio.sleep(0.1)
    return messages


async def retrieve_thread_messages(
    app: AsyncApp, message: dict[str, Any]
) -> list[dict[str, Any]]:
    """Retrieve thread messages from a Slack channel.

    Parameters
    ----------
    app : AsyncApp
        The Slack application instance used to interact with the Slack API.
    message : dict
        The message to retrieve the thread messages for.

    Returns
    -------
    list[dict]
        The list of thread messages for the given message.

    """
    thread_messages = []
    logger.debug(f"message: {message}")
    if message.get("thread_ts") and (message.get("bot_id") == BOT_ID):
        jst_message_datetime = unix_timestamp_to_jst(float(message["ts"]))
        logger.info(f"loading thread. latest message: {jst_message_datetime}")
        _thread_messages = await app.client.conversations_replies(
            channel=OUTPUT_CHANNEL, ts=message["ts"], limit=100
        )
        thread_messages += _thread_messages["messages"]
        await asyncio.sleep(0.1)
    return thread_messages
