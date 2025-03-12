# アプリを起動します
import os
import sys
from collections.abc import Generator
from datetime import timedelta
from typing import Any

import asyncclick as click
from dotenv import load_dotenv
from loguru import logger
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.app.async_app import AsyncApp
from slack_bolt.context.ack.async_ack import AsyncAck
from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy.orm import Session

from hikarie_bot._version import version
from hikarie_bot.curd import initially_insert_badge_data, insert_arrival_action
from hikarie_bot.database import BaseSchema, SessionLocal, engine
from hikarie_bot.modals import (
    ActionID,
    PointGetMessage,
    RegistryMessage,
)
from hikarie_bot.settings import (
    LOG_CHANNEL,
    SLACK_BOT_TOKEN,
)
from hikarie_bot.slack_helper import (
    MessageFilter,
    get_messages,
    retrieve_thread_messages,
    send_daily_message,
)
from hikarie_bot.utils import get_current_jst_datetime, unix_timestamp_to_jst

load_dotenv(override=True)
app = AsyncApp(token=SLACK_BOT_TOKEN)


# Dependency
def get_db() -> Generator[Session, None, None]:
    """Get the database session."""
    # create tables
    BaseSchema.metadata.create_all(engine)
    db = SessionLocal()  # sessionを生成
    try:
        yield db
    finally:
        db.close()


async def initially_create_db(app: AsyncApp) -> None:
    """Asynchronously initializes the database by fetching and processing messages from a Slack channel.

    This function retrieves the message history from a specified Slack channel, including threaded messages,
    and processes them to filter and insert relevant data into the database.

    Args:
    ----
        app (AsyncApp): The Slack application instance used to interact with the Slack API.

    Returns:
    -------
        None
    Raises:
        SlackApiError: If there is an error with the Slack API request.
        asyncio.TimeoutError: If the request to the Slack API times out.

    """  # noqa: E501
    messages = await get_messages(app=app)

    # get the threading messages
    thread_messages = []
    for message in messages:
        thread_messages += await retrieve_thread_messages(app=app, message=message)

    messages += thread_messages

    for message in sorted(messages, key=lambda x: x["ts"]):
        if (user_id := MessageFilter.extract_user_id(message)) and message.get(
            "subtype"
        ) != "channel_join":
            jst_message_datetime = unix_timestamp_to_jst(float(message["ts"]))
            insert_arrival_action(get_db().__next__(), jst_message_datetime, user_id)


@click.command()
@click.option("--dev", is_flag=True, help="Set LOGURU_LEVEL to INFO for development.")
@click.option(
    "--skip-db-create", is_flag=True, help="Set LOGURU_LEVEL to INFO for development."
)
async def main(*, dev: bool = False, skip_db_create: bool = False) -> None:
    """Run the app."""
    log_level = "DEBUG" if dev else "INFO"  # Default log level
    # Configure loguru logger
    logger.remove()
    logger.add(sys.stderr, level=log_level)

    background_task = set()

    # get now in JST for now
    if dev:
        now = get_current_jst_datetime()
        f = send_daily_message(
            app=app, at_hour=now.hour, at_minute=now.minute, check_interval=50
        )
    else:
        f = send_daily_message(app=app, at_hour=6, at_minute=0, check_interval=50)

    a = asyncio.ensure_future(f)

    # makes a strong reference not to GC
    background_task.add(a)
    initially_insert_badge_data(get_db().__next__())
    if not skip_db_create:
        await initially_create_db(app)
    await app.client.chat_postMessage(
        channel=LOG_CHANNEL,
        text=f"application started (v{version})",
    )

    handler = AsyncSocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    await handler.start_async()


@app.action(ActionID.ARRIVED_OFFICE)
@app.action(ActionID.FASTEST_ARRIVAL)
async def handle_button_click(
    ack: AsyncAck, body: dict[str, Any], client: AsyncWebClient
) -> None:
    """Handle the button click event."""
    await ack()
    user_id = body["user"]["id"]
    channel_id = body["channel"]["id"]
    action_id = body["actions"][0]["action_id"]
    message_ts = body["message"]["ts"]
    jst_message_datetime = unix_timestamp_to_jst(float(message_ts))

    logger.debug(
        f"user_id: {user_id}, action_id: {action_id}, "
        f"jst_message_datetime: {jst_message_datetime}"
    )
    now = get_current_jst_datetime()

    # replace the message datetime at 6AM
    jst_message_datetime_at6 = jst_message_datetime.replace(
        hour=6, minute=0, second=0, microsecond=0
    )

    # check if the message was sent within a day
    # the action is only valid from 6AM to 6PM JST
    # if not, send a ephemeral message to the user
    if not (
        jst_message_datetime_at6 < now < jst_message_datetime_at6 + timedelta(hours=12)
    ):
        await client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text="出社申告は当日の6時から18時までの間にしてください",
        )
        return
    insert_result = insert_arrival_action(get_db().__next__(), now, user_id)
    if insert_result is False:
        await client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text="本日は既に出社申告を済ませています",
        )
        return

    # send point get message to thread
    point_get_message = PointGetMessage(
        session=get_db().__next__(),
        user_id=user_id,
        jst_datetime=get_current_jst_datetime(),
        initial_arrival=action_id == ActionID.FASTEST_ARRIVAL,
    )
    await client.chat_postMessage(
        channel=channel_id,
        thread_ts=message_ts,
        text=point_get_message.to_text(),
        blocks=point_get_message.render(),
        reply_broadcast=action_id == ActionID.FASTEST_ARRIVAL,
    )

    # replace the message with RegistryMessage
    registry_message = RegistryMessage(session=get_db().__next__(), jst_datetime=now)
    await client.chat_update(
        channel=channel_id,
        ts=message_ts,
        text=registry_message.to_text(),
        blocks=registry_message.render(),
    )


@app.action(ActionID.CHECK_ACHIEVEMENT)
async def handle_check_achievement(
    ack: AsyncAck, body: dict[str, Any], client: AsyncWebClient
) -> None:
    """Handle the check achievement button click event."""
    await ack()
    user_id = body["user"]["id"]
    from hikarie_bot.slack_components import open_achievement_view

    await open_achievement_view(
        client, get_db().__next__(), body["trigger_id"], user_id
    )


# Moved to a new file: hikarie_bot/slack_components.py


if __name__ == "__main__":
    import asyncio

    main(_anyio_backend="asyncio")
