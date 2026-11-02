# アプリを起動します
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, NamedTuple

import asyncclick as click
from loguru import logger
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.app.async_app import AsyncApp
from slack_bolt.context.ack.async_ack import AsyncAck
from slack_sdk.http_retry.builtin_async_handlers import AsyncRateLimitErrorRetryHandler
from slack_sdk.web.async_client import AsyncWebClient

from hikarie_bot.arrivals import attach_slack_ts, compute_arrivals, record_button_arrival
from hikarie_bot.engine import JST
from hikarie_bot.modals import (
    AchievementView,
    ActionID,
    PointGetMessage,
    RegistryMessage,
    ShortcutID,
)
from hikarie_bot.models import get_db
from hikarie_bot.preview import preview
from hikarie_bot.settings import REQUIRED, get_settings
from hikarie_bot.slack_helper import schedule_daily_message, send_daily_message
from hikarie_bot.startup import StartupReporter, current_revision, prepare
from hikarie_bot.sync import (
    CachedSlackSource,
    LiveSlackSource,
    RecordingSlackSource,
    arrival_metadata,
    sync_channel,
)
from hikarie_bot.utils import get_current_jst_datetime, unix_timestamp_to_jst


def create_client() -> AsyncWebClient:
    """Return a Slack Web API client that waits out rate limits (e.g. the first full sync) instead of failing."""
    client = AsyncWebClient(token=get_settings().slack_bot_token)
    client.retry_handlers.append(AsyncRateLimitErrorRetryHandler(max_retry_count=10))
    return client


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

    settings = get_settings()
    settings.require(*REQUIRED)
    app = create_app()

    # migrate, read arrivals posted while the bot was stopped (the whole channel on first start)
    # and recompute scores before any task touches the database; each step goes to the log channel
    reporter = StartupReporter(client=app.client, channel=settings.log_channel, revision=current_revision())
    await prepare(reporter, LiveSlackSource(app.client), settings.output_channel)

    if dev:
        await send_daily_message(app.client, settings.output_channel)  # post right away to try the buttons
    schedule_daily_message(app.client, settings.output_channel)

    await reporter.post(reporter.summary())

    handler = AsyncSocketModeHandler(app, settings.slack_app_token)
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
async def sync(cache_dir: Path | None, record_dir: Path | None) -> None:
    """Read arrival events from the channel into the database (read-only on Slack)."""
    if cache_dir and record_dir:
        msg = "--from-cache and --record cannot be combined"
        raise click.UsageError(msg)
    if cache_dir:
        source = CachedSlackSource(cache_dir)
    elif record_dir:
        source = RecordingSlackSource(create_client(), record_dir)
    else:
        source = LiveSlackSource(create_client())
    with get_db() as session:
        result = await sync_channel(session, source, get_settings().output_channel)
        click.echo(f"synced: {result}")


ARRIVAL_LOCK = asyncio.Lock()


class Registration(NamedTuple):
    """An arrival to announce: its event, the time it records, and its messages."""

    event_id: int
    occurred_at: datetime
    point_get: PointGetMessage
    registry: RegistryMessage


def register_arrival(user_id: str, now: datetime) -> Registration | None:
    """Record a press and compute scores; return the arrival to announce, or None if already announced."""
    with get_db() as session:
        event = record_button_arrival(session, user_id, now)
        if event is None:
            return None
        event_id, occurred_at = event.id, event.occurred_at
        engine = compute_arrivals(session)
    today = now.astimezone(JST).date()
    arrival = engine.arrival_of(user_id, today)
    if arrival is None:  # the day's first event is the one just found, so the engine counts it
        msg = f"no counted arrival for event {event_id}"
        raise RuntimeError(msg)
    return Registration(event_id, occurred_at, PointGetMessage(arrival), RegistryMessage(engine.arrivals_on(today)))


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

    # One press at a time, until it is announced: a second press retries an arrival only if it was not
    # announced. The database work and the computation run off the event loop.
    async with ARRIVAL_LOCK:
        registration = await asyncio.to_thread(register_arrival, user_id, now)
        if registration is None:
            await client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text="本日は既に出社申告を済ませています",
            )
            return

        response = await client.chat_postMessage(
            channel=channel_id,
            thread_ts=message_ts,
            text=registration.point_get.to_text(),
            blocks=registration.point_get.render(),
            reply_broadcast=registration.point_get.initial_arrival,
            metadata=arrival_metadata(user_id, registration.occurred_at),
        )
        with get_db() as session:
            attach_slack_ts(session, registration.event_id, response["ts"])

    # replace the message with RegistryMessage
    await client.chat_update(
        channel=channel_id,
        ts=message_ts,
        text=registration.registry.to_text(),
        blocks=registration.registry.render(),
    )


def build_achievement_view(user_id: str) -> AchievementView:
    """Compute scores and render the user's achievements."""
    with get_db() as session:
        engine = compute_arrivals(session)
    return AchievementView(engine, user_id)


async def handle_check_achievement(ack: AsyncAck, body: dict[str, Any], client: AsyncWebClient) -> None:
    """Handle the check achievement button click event."""
    await ack()
    user_id = body["user"]["id"]
    view = await asyncio.to_thread(build_achievement_view, user_id)
    logger.info(f"Opening achievement view for user {user_id}")
    await client.views_open(trigger_id=body["trigger_id"], view=view)


async def handle_reboot(ack: AsyncAck, body: dict[str, Any], client: AsyncWebClient) -> None:
    """Handle the reboot shortcut event."""
    await ack()
    user_id = body["user"]["id"]

    if user_id == get_settings().admin:
        await client.chat_postEphemeral(
            channel=body["channel"]["id"],
            user=user_id,
            text="rebooting...",
        )
        sys.exit(0)
    else:
        await client.chat_postEphemeral(
            channel=body["channel"]["id"],
            user=user_id,
            text="not authorized to reboot the application",
        )


def create_app() -> AsyncApp:
    """Create the Slack app with its handlers; only running the bot needs it."""
    app = AsyncApp(client=create_client())
    app.action(ActionID.ARRIVED_OFFICE)(handle_button_click)
    app.action(ActionID.FASTEST_ARRIVAL)(handle_button_click)
    app.action(ActionID.CHECK_ACHIEVEMENT)(handle_check_achievement)
    app.shortcut(ShortcutID.REBOOT)(handle_reboot)
    return app


cli.add_command(preview)


if __name__ == "__main__":
    cli(_anyio_backend="asyncio")
