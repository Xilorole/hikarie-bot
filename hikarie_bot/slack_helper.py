import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import jpholiday
from loguru import logger
from slack_bolt.app.async_app import AsyncApp
from sqlalchemy.orm import Session

from hikarie_bot.modals import InitialMessage, WeeklyMessage
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

    v3_message = r"^(?!.*ヒカリエに出社してる).*" r"<@([A-Z0-9]+)>"


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
        if (
            message.get("bot_id") == BOT_ID
            and message.get("text")
            and (match := re.search(Pattern.v3_message, message["text"]))
        ):
            return match.group(1)
        return None


async def check_bot_has_sent_message(
    app: AsyncApp, channel_id: str, from_datetime: datetime, to_datetime: datetime
) -> bool:
    """Check if the bot has sent a message in the channel.

    Parameters
    ----------
    app : AsyncApp
        The Slack application instance used to interact with the Slack API.
    channel_id : str
        The ID of the Slack channel to check.
    from_datetime : datetime
        The start datetime to check for messages.
    to_datetime : datetime
        The end datetime to check for messages.

    Returns
    -------
    bool
        True if the bot has sent a message, False otherwise.

    """
    try:
        messages = await app.client.conversations_history(
            channel=channel_id,
            oldest=str(from_datetime.timestamp()),
            latest=str(to_datetime.timestamp()),
        )
        return any(message.get("bot_id") == BOT_ID for message in messages.get("messages", []))
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error checking conversation history: {e}")
        return False


async def send_daily_message(
    app: AsyncApp,
    at_hour: int = 6,
    at_minute: int = 0,
    check_interval: int = 50,
    force_send: bool = False,  # noqa: FBT001, FBT002
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
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
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
                if (
                    await check_bot_has_sent_message(
                        app=app,
                        channel_id=channel_id,
                        from_datetime=day_start,
                        to_datetime=now,
                    )
                    and not force_send
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


async def send_weekly_message(  # noqa: PLR0913
    app: AsyncApp,
    session: Session,
    at_hour: int = 6,
    at_minute: int = 0,
    check_interval: int = 50,
    weekday: int = 0,
    force_send: bool = False,  # noqa: FBT001, FBT002
) -> None:
    """Run task every Monday 06:00 JST.

    Parameters
    ----------
    app : AsyncApp
        The Slack application instance used to interact with the Slack API.
    session : Session
        The SQLAlchemy session used to interact with the database.
    at_hour : int, optional
        The hour of the day to send the message (default is 6).
    at_minute : int, optional
        The minute of the hour to send the message (default is 0).
    check_interval : int, optional
        The interval in seconds to check the time (default is 60).
    weekday : int, optional
        The day of the week to send the message (default is 0, which is Monday).
    force_send : bool, optional
        Whether to force send the message even if it has already been sent (default is False).

    """
    # タイムゾーンの生成
    JST = ZoneInfo("Asia/Tokyo")  # noqa: N806
    channel_id = OUTPUT_CHANNEL

    logger.info("Started task")
    while True:
        # check if the time is 06:00 JST
        now = datetime.now(JST)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        logger.debug(f"Current time: {now}")
        logger.debug(f"{now.hour} == {at_hour} and {now.minute} == {at_minute} and {now.weekday()} == {weekday}")
        if now.hour == at_hour and now.minute == at_minute and now.weekday() == weekday:
            logger.info("Attempting to fetch weekly summary message")
            message = WeeklyMessage(session=session, report_date=now)
            if (
                await check_bot_has_sent_message(
                    app=app,
                    channel_id=channel_id,
                    from_datetime=day_start,
                    to_datetime=now,
                )
                and not force_send
            ):
                logger.info("Weekly summary message already sent")
            else:
                logger.info("Sending weekly summary message to channel")
                logger.debug(f"Channel ID: {channel_id}")
                logger.debug(f"Message: {message.render()}")
                await app.client.chat_postMessage(
                    channel=OUTPUT_CHANNEL,
                    blocks=message.render(),
                    text="weekly message",  # to_text()関数はなんだか処理が重すぎるみたい
                )
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
    messages += _messages.get("messages", [])
    while _messages["has_more"]:
        jst_message_datetime = unix_timestamp_to_jst(float(_messages["messages"][-1]["ts"]))
        logger.info(f"loading. latest message: {jst_message_datetime}")
        _messages = await app.client.conversations_history(
            channel=OUTPUT_CHANNEL,
            cursor=_messages["response_metadata"]["next_cursor"],
            oldest="1651363200",  # 2022-05-01 00:00:00
        )
        messages += _messages.get("messages", [])
        await asyncio.sleep(1)  # Tier 3: 50+ requests per minute
    return messages


async def retrieve_thread_messages(app: AsyncApp, message: dict[str, Any]) -> list[dict[str, Any]]:
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
        _thread_messages = await app.client.conversations_replies(channel=OUTPUT_CHANNEL, ts=message["ts"], limit=100)
        thread_messages += _thread_messages.get("messages", [])
        await asyncio.sleep(1)  # Tier 3: 50+ requests per minute
    return thread_messages
