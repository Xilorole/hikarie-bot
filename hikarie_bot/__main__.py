# アプリを起動します
import asyncio
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

import asyncclick as click
from loguru import logger
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.app.async_app import AsyncApp
from slack_bolt.context.ack.async_ack import AsyncAck
from slack_sdk.http_retry.builtin_async_handlers import AsyncRateLimitErrorRetryHandler
from slack_sdk.web.async_client import AsyncWebClient

from hikarie_bot.arrivals import attach_slack_ts, record_button_arrival
from hikarie_bot.modals import (
    ActionID,
    PointGetMessage,
    RegistryMessage,
    ShortcutID,
)
from hikarie_bot.models import get_db
from hikarie_bot.preview import preview
from hikarie_bot.settings import (
    ADMIN,
    LOG_CHANNEL,
    OUTPUT_CHANNEL,
    SLACK_APP_TOKEN,
    SLACK_BOT_TOKEN,
)
from hikarie_bot.slack_components import open_achievement_view
from hikarie_bot.slack_helper import (
    send_daily_message,
)
from hikarie_bot.startup import StartupReporter, current_revision, prepare
from hikarie_bot.sync import (
    CachedSlackSource,
    LiveSlackSource,
    RecordingSlackSource,
    arrival_metadata,
    rebuild_derived_tables,
    sync_channel,
)
from hikarie_bot.utils import get_current_jst_datetime, unix_timestamp_to_jst

app = AsyncApp(token=SLACK_BOT_TOKEN)
# Wait out Slack rate limits (e.g. the first full sync) instead of failing.
app.client.retry_handlers.append(AsyncRateLimitErrorRetryHandler(max_retry_count=10))


@click.group()
def cli() -> None:
    """Hikarie Bot CLI."""


@cli.command()
@click.option("--dev", is_flag=True, help="Set LOGURU_LEVEL to INFO for development.")
async def start(*, dev: bool = False) -> None:
    """Run the app."""
    log_level = "DEBUG" if dev else "INFO"  # Default log level
    # Configure loguru logger
    logger.remove()
    logger.add(sys.stderr, level=log_level)

    # migrate, read arrivals posted while the bot was stopped (the whole channel on first start)
    # and recompute scores before any task touches the database; each step goes to the log channel
    reporter = StartupReporter(client=app.client, channel=LOG_CHANNEL, revision=current_revision())
    await prepare(reporter, LiveSlackSource(app.client), OUTPUT_CHANNEL)

    background_task = set()

    # get now in JST for now
    if dev:
        now = get_current_jst_datetime()
        f = send_daily_message(
            app=app,
            at_hour=now.hour,
            at_minute=now.minute,
            check_interval=50,
            force_send=True,
        )
    else:
        f = send_daily_message(app=app)

    a = asyncio.ensure_future(f)

    # makes a strong reference not to GC
    background_task.add(a)

    await reporter.post(reporter.summary())

    handler = AsyncSocketModeHandler(app, SLACK_APP_TOKEN)
    await handler.start_async()


@cli.command()
@click.option(
    "--from-cache",
    "cache_dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
    help="Read recorded Slack responses from this directory instead of Slack (offline).",
)
@click.option(
    "--record",
    "record_dir",
    type=click.Path(path_type=Path, file_okay=False),
    help="Also save the raw Slack responses into this directory.",
)
@click.option("--rebuild/--no-rebuild", default=True, show_default=True, help="Recompute scores and badges afterwards.")
async def sync(cache_dir: Path | None, record_dir: Path | None, *, rebuild: bool) -> None:
    """Read arrival events from the channel into the database (read-only on Slack)."""
    if cache_dir and record_dir:
        msg = "--from-cache and --record cannot be combined"
        raise click.UsageError(msg)
    if cache_dir:
        source = CachedSlackSource(cache_dir)
    elif record_dir:
        source = RecordingSlackSource(app.client, record_dir)
    else:
        source = LiveSlackSource(app.client)
    with get_db() as session:
        result = await sync_channel(session, source, OUTPUT_CHANNEL)
        click.echo(f"synced: {result}")
        if rebuild:
            click.echo(f"rebuilt from {rebuild_derived_tables(session)} events")


@app.action(ActionID.ARRIVED_OFFICE)
@app.action(ActionID.FASTEST_ARRIVAL)
async def handle_button_click(ack: AsyncAck, body: dict[str, Any], client: AsyncWebClient) -> None:
    """Handle the button click event."""
    await ack()
    user_id = body["user"]["id"]
    channel_id = body["channel"]["id"]
    action_id = body["actions"][0]["action_id"]
    message_ts = body["message"]["ts"]
    jst_message_datetime = unix_timestamp_to_jst(float(message_ts))

    logger.debug(f"user_id: {user_id}, action_id: {action_id}, jst_message_datetime: {jst_message_datetime}")
    now = get_current_jst_datetime()

    # replace the message datetime at 6AM
    jst_message_datetime_at6 = jst_message_datetime.replace(hour=6, minute=0, second=0, microsecond=0)

    # check if the message was sent within a day
    # the action is only valid from 6AM to 6PM JST
    # if not, send a ephemeral message to the user
    if not (jst_message_datetime_at6 < now < jst_message_datetime_at6 + timedelta(hours=12)):
        await client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text="出社申告は当日の6時から18時までの間にしてください",
        )
        return

    with get_db() as session:
        event = record_button_arrival(session, user_id, now)
        event_id = event.id if event else None
    if event_id is None:
        await client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text="本日は既に出社申告を済ませています",
        )
        return

    # recompute scores and badges from the events (well under a second), then announce them
    with get_db() as session:
        rebuild_derived_tables(session)
        point_get_message = PointGetMessage(
            session=session,
            user_id=user_id,
            jst_datetime=now,
            initial_arrival=action_id == ActionID.FASTEST_ARRIVAL,
        )
        registry_message = RegistryMessage(
            session=session,
            jst_datetime=now,
        )
    response = await client.chat_postMessage(
        channel=channel_id,
        thread_ts=message_ts,
        text=point_get_message.to_text(),
        blocks=point_get_message.render(),
        reply_broadcast=action_id == ActionID.FASTEST_ARRIVAL,
        metadata=arrival_metadata(user_id, now),
    )
    with get_db() as session:
        attach_slack_ts(session, event_id, response["ts"])

    # replace the message with RegistryMessage
    await client.chat_update(
        channel=channel_id,
        ts=message_ts,
        text=registry_message.to_text(),
        blocks=registry_message.render(),
    )


@app.action(ActionID.CHECK_ACHIEVEMENT)
async def handle_check_achievement(ack: AsyncAck, body: dict[str, Any], client: AsyncWebClient) -> None:
    """Handle the check achievement button click event."""
    await ack()
    user_id = body["user"]["id"]

    with get_db() as session:
        await open_achievement_view(client, session, body["trigger_id"], user_id)


# Moved to a new file: hikarie_bot/slack_components.py


@app.shortcut(ShortcutID.REBOOT)
async def handle_reboot(ack: AsyncAck, body: dict[str, Any]) -> None:
    """Handle the reboot shortcut event."""
    await ack()
    user_id = body["user"]["id"]

    if user_id == ADMIN:
        await app.client.chat_postEphemeral(
            channel=body["channel"]["id"],
            user=user_id,
            text="rebooting...",
        )
        sys.exit(0)
    else:
        await app.client.chat_postEphemeral(
            channel=body["channel"]["id"],
            user=user_id,
            text="not authorized to reboot the application",
        )


cli.add_command(preview)
# Kept for existing usage; renders the same previews.
cli.add_command(preview, name="build-modals")


if __name__ == "__main__":
    cli(_anyio_backend="asyncio")
