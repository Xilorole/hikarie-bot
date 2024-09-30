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
from hikarie_bot.slack_helper import send_daily_message
from hikarie_bot.utils import get_current_jst_datetime, unix_timestamp_to_jst

load_dotenv()
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

    handler = AsyncSocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    await handler.start_async()


@app.action(ActionID.FASTEST_ARRIVAL)
async def handle_button_click(ack: dict, body: dict, client: WebClient) -> None:
    """Handle the button click event."""
    await ack()
    user_id = body["user"]["id"]

    # check if the message was sent within a day
    # the action is only valid from 6AM to 6PM JST
    # if not, send a ephemeral message to the user

    message_ts = body["message"]["ts"]
    jst_message_datetime = unix_timestamp_to_jst(float(message_ts))
    now = get_current_jst_datetime()
    insert_result = insert_arrival_action(get_db().__next__(), now, user_id)
    if insert_result is False:
        await client.chat_postEphemeral(
            channel=body["channel"]["id"],
            user=body["user"]["id"],
            text="本日は既に出社申告を済ませています",
        )
        return

    # replace the message datetime at 6AM
    jst_message_datetime_at6 = jst_message_datetime.replace(
        hour=6, minute=0, second=0, microsecond=0
    )

    if not (
        jst_message_datetime_at6 < now < jst_message_datetime_at6 + timedelta(hours=12)
    ):
        await client.chat_postEphemeral(
            channel=body["channel"]["id"],
            user=body["user"]["id"],
            text="出社申告は当日の6:00から18:00までの間にしてください",
        )
        return

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

    registry_message = RegistryMessage()
    await client.chat_update(
        channel=body["channel"]["id"],
        ts=body["message"]["ts"],
        text=registry_message.to_text(),
        blocks=registry_message.render(),
    )


@app.action(ActionID.ARRIVED_OFFICE)
async def handle_arrived_office(ack: dict, body: dict, client: WebClient) -> None:
    """Handle the arrived office action."""
    await ack()
    user_id = body["user"]["id"]

    message_ts = body["message"]["ts"]
    jst_message_datetime = unix_timestamp_to_jst(float(message_ts))
    now = get_current_jst_datetime()
    insert_result = insert_arrival_action(get_db().__next__(), now, user_id)
    if insert_result is False:
        await client.chat_postEphemeral(
            channel=body["channel"]["id"],
            user=body["user"]["id"],
            text="本日は既に出社申告を済ませています",
        )
        return

    # replace the message datetime at 6AM
    jst_message_datetime = jst_message_datetime.replace(
        hour=6, minute=0, second=0, microsecond=0
    )

    if not (jst_message_datetime < now < jst_message_datetime + timedelta(hours=12)):
        await client.chat_postEphemeral(
            channel=body["channel"]["id"],
            user=body["user"]["id"],
            text="出社申告は当日の6:00から18:00までの間にしてください",
        )
        return

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


if __name__ == "__main__":
    import asyncio

    main(_anyio_backend="asyncio")
