import asyncio
from datetime import datetime, timedelta, timezone

import jpholiday
from loguru import logger
from slack_bolt.app.async_app import AsyncApp

from hikarie_bot.modals import InitialMessage
from hikarie_bot.settings import BOT_ID, OUTPUT_CHANNEL


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
