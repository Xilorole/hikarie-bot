import asyncio
import os
import re
from datetime import UTC, datetime, timedelta, timezone

from loguru import logger
from slack_bolt import App
from slack_bolt.app.async_app import AsyncApp


class ActionId:
    """Class for storing the action IDs used in the Slack app."""

    ARRIVED_OFFICE = "ARRIVED_OFFICE"
    FASTEST_ARRIVAL = "FASTEST_ARRIVAL"
    POINT_GET = "POINT_GET"


class BlockId:
    """Class for storing the block IDs used in the Slack app."""

    ARRIVED_OFFICE = "ARRIVED_OFFICE"


class Text:
    """Class for storing the text used in the Slack app."""

    QUESTION = "ヒカリエに出社してる？"  # noqa: RUF001
    ARRIVED_OFFICE = "出社ポイント獲得"
    FASTEST_ARRIVAL = "最速出社"


class Pattern:
    """Class for storing the regular expression patterns used in the Slack app."""

    QUESTION = r"ヒカリエに出社してる？"  # noqa: RUF001
    ARRIVED_OFFICE = r"\d{2}:\d{2} 出社登録しました！"  # noqa: RUF001
    FASTEST_ARRIVAL = r"本日の最速出社: <@\w+>"


def filter_question_message(message: dict) -> bool:
    """Filter question messages from a Slack message.

    Parameters
    ----------
    message : dict
        The Slack message to filter.

    Returns
    -------
        bool: True if the message is a question message, False otherwise.

    """
    text = message.get("text")
    return (
        message.get("bot_id")
        and isinstance(text, str)
        and (
            re.match(Pattern.ARRIVED_OFFICE, text)
            or re.match(Pattern.FASTEST_ARRIVAL, text)
        )
        or False
    )


def fetch_todays_initial_message(
    app: App,
    channel_id: str,
    today: datetime | None = None,
) -> str | None:
    """Fetch the timestamp of the initial message sent today.

    This function retrieves the initial message sent today in a specified Slack channel.
    It fetches the message history for the current day, filters the messages based on a
    specific criterion, and returns the timestamp of the initial message.

    Args:
    ----
        app (App): The Slack app instance used to interact with the Slack API.
        channel_id (str): The ID of the Slack channel to fetch the message history.
        today (datetime, optional): The current date and time. Defaults to None,
            in which case the current date and time in JST (UTC+9) is used.

    Returns:
    -------
        str | None: The timestamp of the initial message sent today, or None if no such
            message exists.

    """
    if today is None:
        today = datetime.now(UTC).astimezone(timezone(timedelta(hours=9)))
    # Get the latest message
    oldest = today.replace(hour=0, minute=0, second=0, microsecond=0)
    latest = today.replace(hour=23, minute=59, second=59, microsecond=0)
    logger.info(
        f"fetching data from {
            oldest:%Y-%m-%d %H:%M:%S} to {latest:%Y-%m-%d %H:%M:%S}"
    )
    response = app.client.conversations_history(
        channel=channel_id,
        limit=1000,
        oldest=oldest.timestamp(),
        latest=latest.timestamp(),
    )
    logger.info(f"response: {response.data}")

    # Filter the message
    filtered_messages = list(
        filter(filter_question_message, response.data.get("messages"))
    )
    # Check whether the message has been sent today
    if filtered_messages:
        # If not, send the message
        if len(filtered_messages) != 1:
            logger.warning("There are multiple initial messages today")
        # get the latest message
        return sorted(filtered_messages, key=lambda message: float(message["ts"]))[
            -1
        ].get("ts")
    return None


async def send_daily_message(
    app: AsyncApp, at_hour: int = 6, at_minute: int = 0
) -> None:
    "Run task every weekday 06:00 JST."
    # タイムゾーンの生成
    JST = timezone(timedelta(hours=+9), "JST")  # noqa: N806
    channel_id = os.environ.get("DEV")

    logger.info("started task")
    while True:
        # check if the time is 06:00 JST
        now = datetime.now(JST)
        next_day = now + timedelta(days=1)
        logger.info(f"now is {now}")
        if now.hour == at_hour and now.minute == at_minute:
            logger.info("tring to fetch message")
            # check if the BOT already sent to channel
            messages = await app.client.conversations_history(
                channel=channel_id,
                oldest=datetime(
                    year=now.year,
                    month=now.month,
                    day=now.day,
                    tzinfo=JST,
                ).timestamp(),
                latest=datetime(
                    year=next_day.year,
                    month=next_day.month,
                    day=next_day.day,
                    tzinfo=JST,
                ).timestamp(),
            )

            app_user_id = os.environ.get("BOT_ID")
            if any(app_user_id == message["user"] for message in messages["messages"]):
                logger.info("message already sent")
            else:
                logger.info("sending message to channel")
                await app.client.chat_postMessage(
                    channel=channel_id,
                    text="Hi there!",
                )
        await asyncio.sleep(5)
