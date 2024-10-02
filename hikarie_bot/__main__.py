# アプリを起動します
import os
import sys
from collections.abc import Generator
from datetime import timedelta

import asyncclick as click
from dotenv import load_dotenv
from loguru import logger
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.app.async_app import AsyncApp
from slack_sdk.web import WebClient
from sqlalchemy.orm import Session

from hikarie_bot.curd import insert_arrival_action
from hikarie_bot.database import BaseSchema, SessionLocal, engine
from hikarie_bot.modals import (
    ActionID,
    FastestArrivalMessage,
    PointGetMessage,
    RegistryMessage,
)
from hikarie_bot.slack_helper import MessageFilter, send_daily_message
from hikarie_bot.utils import get_current_jst_datetime, unix_timestamp_to_jst

load_dotenv(override=True)
app = AsyncApp(token=os.environ.get("SLACK_BOT_TOKEN"))


# Dependency
def get_db() -> Generator[Session, None, None]:
    """Get the database session."""
    # create tables
    BaseSchema.metadata.create_all(engine)
    try:
        db = SessionLocal()  # sessionを生成
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
    messages = []

    _messages = await app.client.conversations_history(
        channel=os.environ.get("OUTPUT_CHANNEL")
    )
    messages += _messages["messages"]
    while _messages["has_more"]:
        jst_message_datetime = unix_timestamp_to_jst(
            float(_messages["messages"][-1]["ts"])
        )
        logger.info(f"loading. latest message: {jst_message_datetime}")
        _messages = await app.client.conversations_history(
            channel=os.environ.get("OUTPUT_CHANNEL"),
            cursor=_messages["response_metadata"]["next_cursor"],
        )
        messages += _messages["messages"]
        await asyncio.sleep(0.1)

    # get the threading messages
    thread_messages = []
    for message in messages:
        logger.debug(f"message: {message}")
        if message.get("thread_ts") and (
            message.get("user") == os.environ.get("BOT_ID")
            or message.get("bot_id") == os.environ.get("V1_BOT_ID")
        ):
            jst_message_datetime = unix_timestamp_to_jst(float(message["ts"]))
            logger.info(f"loading thread. latest message: {jst_message_datetime}")
            _thread_messages = await app.client.conversations_replies(
                channel=os.environ.get("OUTPUT_CHANNEL"), ts=message["ts"], limit=100
            )
            thread_messages += _thread_messages["messages"]
            await asyncio.sleep(0.1)
    messages += thread_messages

    message_filter = MessageFilter()
    for message in sorted(messages, key=lambda x: x["ts"]):
        if (
            user_id := (
                message_filter.filter_v1(message) or message_filter.filter_v3(message)
            )
        ) and message.get("subtype") != "channel_join":
            jst_message_datetime = unix_timestamp_to_jst(float(message["ts"]))
            insert_arrival_action(get_db().__next__(), jst_message_datetime, user_id)


@click.command()
@click.option("--dev", is_flag=True, help="Set LOGURU_LEVEL to INFO for development.")
async def main(*, dev: bool = False) -> None:
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

    await initially_create_db(app)

    handler = AsyncSocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    await handler.start_async()


@app.action(ActionID.ARRIVED_OFFICE)
@app.action(ActionID.FASTEST_ARRIVAL)
async def handle_button_click(ack: dict, body: dict, client: WebClient) -> None:
    """Handle the button click event."""
    await ack()
    user_id = body["user"]["id"]
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
            channel=body["channel"]["id"],
            user=body["user"]["id"],
            text="出社申告は当日の6:00から18:00までの間にしてください",
        )
        return
    insert_result = insert_arrival_action(get_db().__next__(), now, user_id)
    if insert_result is False:
        await client.chat_postEphemeral(
            channel=body["channel"]["id"],
            user=body["user"]["id"],
            text="本日は既に出社申告を済ませています",
        )
        return

    if body["actions"][0]["action_id"] == ActionID.FASTEST_ARRIVAL:
        ## send the fastest arrival message
        arrival_message = FastestArrivalMessage(
            user_id=user_id, jst_datetime=get_current_jst_datetime()
        )
        await client.chat_postMessage(
            channel=body["channel"]["id"],
            text=arrival_message.to_text(),
            blocks=arrival_message.render(),
        )

    # send point get message to thread
    point_get_message = PointGetMessage(
        session=get_db().__next__(),
        user_id=user_id,
        jst_datetime=get_current_jst_datetime(),
    )
    await client.chat_postMessage(
        channel=body["channel"]["id"],
        thread_ts=body["message"]["ts"],
        text=point_get_message.to_text(),
        blocks=point_get_message.render(),
    )

    # replace the message with RegistryMessage
    if body["actions"][0]["action_id"] == ActionID.FASTEST_ARRIVAL:
        registry_message = RegistryMessage()
        await client.chat_update(
            channel=body["channel"]["id"],
            ts=body["message"]["ts"],
            text=registry_message.to_text(),
            blocks=registry_message.render(),
        )


if __name__ == "__main__":
    import asyncio

    main(_anyio_backend="asyncio")
