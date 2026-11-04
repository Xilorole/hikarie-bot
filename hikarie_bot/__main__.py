# アプリを起動します
import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, NamedTuple

import asyncclick as click
from loguru import logger
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.app.async_app import AsyncApp
from slack_bolt.context.ack.async_ack import AsyncAck
from slack_sdk.errors import SlackApiError
from slack_sdk.http_retry.builtin_async_handlers import AsyncRateLimitErrorRetryHandler
from slack_sdk.web.async_client import AsyncWebClient

from hikarie_bot.arrivals import attach_slack_ts, compute_arrivals, record_button_arrival
from hikarie_bot.constants import JST
from hikarie_bot.database import get_db
from hikarie_bot.engine import ArrivalResult, Outlook, TeamProgress
from hikarie_bot.modals import (
    ActionID,
    BlockID,
    CallbackID,
    ShortcutID,
    achievement_view,
    goals_message,
    goals_text,
    item_pick_view,
    item_picked_message,
    item_picked_text,
    item_review_view,
    notice_view,
    point_get_message,
    registry_message,
    render,
    to_text,
)
from hikarie_bot.picks import PickGate, StoredPick, attach_pick_ts, pick_gate, record_pick
from hikarie_bot.preview import preview
from hikarie_bot.settings import REQUIRED, get_settings
from hikarie_bot.slack_helper import find_daily_post, schedule_daily_message, schedule_weekly_usage, send_daily_message
from hikarie_bot.startup import StartupReporter, current_revision, prepare
from hikarie_bot.sync import (
    CachedSlackSource,
    LiveSlackSource,
    RecordingSlackSource,
    arrival_metadata,
    item_pick_metadata,
    sync_channel,
)
from hikarie_bot.usage import describe_usage, last_full_week, usage_report


def create_client() -> AsyncWebClient:
    """Return a Slack Web API client that waits out rate limits (e.g. the first full sync) instead of failing."""
    client = AsyncWebClient(token=get_settings().slack_bot_token)
    client.retry_handlers.append(AsyncRateLimitErrorRetryHandler(max_retry_count=10))
    return client


@click.group()
def cli() -> None:
    """Hikarie Bot CLI."""


@cli.command()
@click.option("--dev", is_flag=True, help="Log at DEBUG and post the daily message right away.")
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
    schedule_weekly_usage(app.client, settings.log_channel)

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
    """Read the whole channel into the database (read-only on Slack; stored events are skipped)."""
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


@cli.command()
@click.option(
    "--week-of",
    "week_of",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="A day in the week to report (default: last full week).",
)
@click.option("--weeks", default=8, show_default=True, help="Weeks in the trend.")
async def stats(week_of: datetime | None, weeks: int) -> None:
    """Print the usage of a week from the database (counts only; no Slack token needed)."""
    with get_db() as session:
        engine = compute_arrivals(session)
    week = week_of.date() if week_of else last_full_week(datetime.now(JST).date())
    click.echo(describe_usage(usage_report(engine, week, weeks)))


ARRIVAL_LOCK = asyncio.Lock()


class Registration(NamedTuple):
    """An arrival to announce: its event, the time it records, and its messages."""

    event_id: int
    occurred_at: datetime
    arrival: ArrivalResult
    arrivals_today: list[ArrivalResult]
    outlook: Outlook
    team: TeamProgress | None  # the week so far, for the daily post


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
    return Registration(
        event_id, occurred_at, arrival, engine.arrivals_on(today), engine.outlook(arrival), engine.team_progress(now)
    )


OUTSIDE_WINDOW = "出社申告は当日の6時から18時までの間にしてください"
ALREADY_ARRIVED = "本日は既に出社申告を済ませています"
NO_DAILY_POST = "今日の出社確認の投稿がまだありません（営業日の6時から18時まで）"


class Arrival(NamedTuple):
    """How a press went: why it was refused, or what the user can aim for after the announced arrival."""

    refusal: str | None
    outlook: Outlook | None = None


async def arrive(client: AsyncWebClient, user_id: str, channel_id: str, post_ts: str) -> Arrival:
    """Record and announce an arrival on the daily post; return why it was refused, or its outlook."""
    now = datetime.now(JST)
    # the action is only valid from 6AM to 6PM JST of the post's day
    post_at6 = datetime.fromtimestamp(float(post_ts), JST).replace(hour=6, minute=0, second=0, microsecond=0)
    if not (post_at6 < now < post_at6 + timedelta(hours=12)):
        return Arrival(OUTSIDE_WINDOW)

    # One press at a time, until it is announced and the daily post is updated: a second press retries an
    # arrival only if it was not announced, and the updates must land in the order the lists were computed,
    # or a delayed one would overwrite a later list. The database work and the computation run off the
    # event loop.
    async with ARRIVAL_LOCK:
        registration = await asyncio.to_thread(register_arrival, user_id, now)
        if registration is None:
            return Arrival(ALREADY_ARRIVED)

        point_get = point_get_message(registration.arrival)
        response = await client.chat_postMessage(
            channel=channel_id,
            thread_ts=post_ts,
            text=to_text(point_get),
            blocks=render(point_get),
            reply_broadcast=registration.arrival.rank == 1,
            metadata=arrival_metadata(user_id, registration.occurred_at),
        )
        with get_db() as session:
            attach_slack_ts(session, registration.event_id, response["ts"])

        # replace the message with the day's arrivals
        registry = registry_message(registration.arrivals_today, registration.team)
        await client.chat_update(channel=channel_id, ts=post_ts, text=to_text(registry), blocks=render(registry))
    return Arrival(None, registration.outlook)


async def send_goals(client: AsyncWebClient, channel_id: str, user_id: str, outlook: Outlook) -> None:
    """Tell the user alone what to aim for next; the arrival is announced already, so a failure only logs."""
    message = goals_message(outlook)
    if not message:
        return
    try:
        await client.chat_postEphemeral(channel=channel_id, user=user_id, text=to_text(message), blocks=render(message))
    except Exception:  # noqa: BLE001
        logger.exception("Could not send the next goals")


async def handle_button_click(ack: AsyncAck, body: dict[str, Any], client: AsyncWebClient) -> None:
    """Handle a press of the arrival button on the daily post."""
    await ack()
    user_id = body["user"]["id"]
    channel_id = body["channel"]["id"]
    logger.debug(f"user_id: {user_id}, action_id: {body['actions'][0]['action_id']}")
    arrival = await arrive(client, user_id, channel_id, body["message"]["ts"])
    if arrival.refusal is not None:
        await client.chat_postEphemeral(channel=channel_id, user=user_id, text=arrival.refusal)
    elif arrival.outlook is not None:
        await send_goals(client, channel_id, user_id, arrival.outlook)


async def handle_arrive_shortcut(ack: AsyncAck, body: dict[str, Any], client: AsyncWebClient) -> None:
    """Record an arrival from the global shortcut, on today's daily post, and reply in a modal.

    The modal opens first (a trigger expires in 3 seconds) and shows the outcome, with the next goals,
    when it is known.
    """
    await ack()
    user_id = body["user"]["id"]
    channel_id = get_settings().output_channel
    opened = await client.views_open(trigger_id=body["trigger_id"], view=notice_view("出社登録しています…"))
    view_id = opened["view"]["id"]
    try:
        post_ts = await find_daily_post(client, channel_id, datetime.now(JST))
        arrival = Arrival(NO_DAILY_POST) if post_ts is None else await arrive(client, user_id, channel_id, post_ts)
    except Exception:
        await client.views_update(view_id=view_id, view=notice_view("出社登録に失敗しました。もう一度試してください"))
        raise
    if arrival.refusal is not None:
        text = arrival.refusal
    else:
        text = f"出社登録しました。<#{channel_id}> の今日の投稿のスレッドに記録しています"
        if arrival.outlook is not None and (goals := goals_text(arrival.outlook)):
            text += f"\n\n*つぎのもくひょう*\n{goals}"
    await client.views_update(view_id=view_id, view=notice_view(text))


def build_achievement_view(user_id: str) -> dict:
    """Compute scores and render the user's achievements."""
    with get_db() as session:
        engine = compute_arrivals(session)
    return achievement_view(engine, user_id)


def describe_error(error: Exception) -> str:
    """Describe an error for the user who hit it: Slack's error code and its messages, or the exception type."""
    if isinstance(error, SlackApiError):
        messages = error.response.get("response_metadata", {}).get("messages", [])
        return "; ".join([error.response.get("error", "slack_error"), *messages])
    return type(error).__name__


async def handle_check_achievement(ack: AsyncAck, body: dict[str, Any], client: AsyncWebClient) -> None:
    """Open the status modal; if it fails, tell the user why in an ephemeral message instead of nothing."""
    await ack()
    user_id = body["user"]["id"]
    try:
        view = await asyncio.to_thread(build_achievement_view, user_id)
        logger.info(f"Opening achievement view for user {user_id}")
        await client.views_open(trigger_id=body["trigger_id"], view=view)
    except Exception as error:
        logger.exception("Could not open the status modal")
        channel = body.get("channel", {}).get("id")
        if channel is None:
            raise
        await client.chat_postEphemeral(
            channel=channel, user=user_id, text=f"ステータスを開けませんでした（{describe_error(error)}）"
        )


ITEM_LOCK = asyncio.Lock()


def check_pick(user_id: str, now: datetime) -> PickGate:
    """Check whether the user may pick an item now."""
    with get_db() as session:
        return pick_gate(session, user_id, now)


def store_pick(user_id: str, item_id: str, now: datetime) -> PickGate:
    """Store the pick if the user may pick it now."""
    with get_db() as session:
        return record_pick(session, user_id, item_id, now)


async def announce_pick(client: AsyncWebClient, channel_id: str, thread_ts: str, pick: StoredPick) -> None:
    """Post the pick in the daily post's thread with its metadata, and link the post to the pick."""
    response = await client.chat_postMessage(
        channel=channel_id,
        thread_ts=thread_ts,
        text=item_picked_text(pick.user_id, pick.item),
        blocks=render(item_picked_message(pick.user_id, pick.item)),
        metadata=item_pick_metadata(pick.user_id, pick.day, pick.item_id, pick.occurred_at),
    )
    with get_db() as session:
        attach_pick_ts(session, pick.id, response["ts"])


async def handle_pick_item(ack: AsyncAck, body: dict[str, Any], client: AsyncWebClient) -> None:
    """Open today's item offers to pick from, or to look at once picked or while an item is held."""
    await ack()
    user_id = body["user"]["id"]
    channel_id = body["channel"]["id"]
    message_ts = body["message"]["ts"]
    now = datetime.now(JST)
    if datetime.fromtimestamp(float(message_ts), JST).date() != now.date():
        await client.chat_postEphemeral(channel=channel_id, user=user_id, text="アイテムは今日の投稿から選んでください")
        return

    async with ITEM_LOCK:
        gate = await asyncio.to_thread(check_pick, user_id, now)
        if gate.unannounced is not None:  # stored but its announcement failed: announce it now
            await announce_pick(client, channel_id, message_ts, gate.unannounced)
            return
    if gate.refusal is not None:
        await client.chat_postEphemeral(channel=channel_id, user=user_id, text=gate.refusal)
        return
    if gate.notice is not None:  # picked today, or holding an item: the offers to look at
        view = item_review_view(gate.offers, gate.notice, gate.picked_item_id)
    else:
        view = item_pick_view(gate.offers, channel_id, message_ts, now.date())
    logger.info(f"Opening item offers for user {user_id}")
    await client.views_open(trigger_id=body["trigger_id"], view=view)


async def handle_item_submission(ack: AsyncAck, body: dict[str, Any], client: AsyncWebClient) -> None:
    """Store the picked item if the user still may pick it, and announce it in the thread."""
    user_id = body["user"]["id"]
    view = body["view"]
    metadata = json.loads(view["private_metadata"])
    selected = view["state"]["values"][BlockID.ITEM_CHOICE][ActionID.ITEM_CHOICE]["selected_option"]
    now = datetime.now(JST)
    if metadata["day"] != now.date().isoformat():
        await ack(
            response_action="errors",
            errors={BlockID.ITEM_CHOICE: "日付が変わりました。今日の投稿から選び直してください"},
        )
        return

    # one pick at a time: the gate is checked again here, as the modal may have stayed open
    async with ITEM_LOCK:
        gate = await asyncio.to_thread(store_pick, user_id, selected["value"], now)
        if gate.unannounced is None:
            await ack(response_action="errors", errors={BlockID.ITEM_CHOICE: gate.refusal})
            return
        await ack()
        await announce_pick(client, metadata["channel"], metadata["thread_ts"], gate.unannounced)


async def handle_item_review(ack: AsyncAck) -> None:
    """Close a read-only item modal opened before its OK button was removed: it submits nothing."""
    await ack()


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
    app.action(ActionID.PICK_ITEM)(handle_pick_item)
    app.view(CallbackID.ITEM_PICK)(handle_item_submission)
    app.view(CallbackID.ITEM_REVIEW)(handle_item_review)
    app.shortcut(ShortcutID.REBOOT)(handle_reboot)
    app.shortcut(ShortcutID.ARRIVE)(handle_arrive_shortcut)
    return app


cli.add_command(preview)


if __name__ == "__main__":
    cli(_anyio_backend="asyncio")
