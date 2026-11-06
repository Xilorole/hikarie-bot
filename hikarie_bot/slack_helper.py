"""Post the daily question on Japanese business days at 06:00 JST, and the weekly usage to the log channel."""

import asyncio
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from slack_sdk.web.async_client import AsyncWebClient

from hikarie_bot.arrivals import compute_arrivals
from hikarie_bot.constants import JST
from hikarie_bot.database import get_db
from hikarie_bot.engine import TeamProgress
from hikarie_bot.modals import BlockID, home_url, initial_message, render, to_text
from hikarie_bot.settings import get_settings
from hikarie_bot.usage import describe_usage, last_full_week, usage_report
from hikarie_bot.utils import is_jp_bizday

# runs every day; days off are skipped by the same rule the streak badges use
DAILY_MESSAGE_TRIGGER = CronTrigger(hour=6, timezone=JST)
# the week before, reported on Monday morning (a holiday too: the log channel is for the maintainers)
WEEKLY_USAGE_TRIGGER = CronTrigger(day_of_week="mon", hour=7, timezone=JST)
DAILY_POST_BLOCKS = {BlockID.FASTEST_ARRIVAL, BlockID.ARRIVED_OFFICE}


def team_progress_now() -> TeamProgress | None:
    """Return the week's team progress up to now (None before the team goal applies)."""
    with get_db() as session:
        engine = compute_arrivals(session)
    return engine.team_progress(datetime.now(JST))


async def send_daily_message(client: AsyncWebClient, channel: str) -> None:
    """Post the daily question on Japanese business days (not weekends, holidays, Dec 31 or Jan 1-3)."""
    if not is_jp_bizday(datetime.now(JST).date()):
        return
    settings = get_settings()
    message = initial_message(
        await asyncio.to_thread(team_progress_now), home_url(settings.slack_workspace_id, settings.slack_app_id)
    )
    await client.chat_postMessage(channel=channel, blocks=render(message), text=to_text(message))


async def find_daily_post(client: AsyncWebClient, channel: str, now: datetime) -> str | None:
    """Return the ts of the day's daily post (the earliest, if posted twice), or None if there is none yet."""
    start_of_day = now.astimezone(JST).replace(hour=0, minute=0, second=0, microsecond=0)
    response = await client.conversations_history(channel=channel, oldest=f"{start_of_day.timestamp():.6f}", limit=200)
    bot_id = get_settings().bot_id
    posts = [
        message["ts"]
        for message in response.get("messages", [])
        if message.get("bot_id") == bot_id
        and message.get("thread_ts", message["ts"]) == message["ts"]  # not a broadcast thread reply
        and any(block.get("block_id") in DAILY_POST_BLOCKS for block in message.get("blocks", []))
    ]
    return min(posts, key=float) if posts else None


async def send_weekly_usage(client: AsyncWebClient, channel: str) -> None:
    """Post last week's usage (counts only, never user IDs) to the log channel."""

    def report() -> str:
        with get_db() as session:
            engine = compute_arrivals(session)
        return describe_usage(usage_report(engine, last_full_week(datetime.now(JST).date())))

    try:
        await client.chat_postMessage(channel=channel, text=await asyncio.to_thread(report))
    except Exception:  # noqa: BLE001  # a report never stops the bot
        logger.exception("Could not post the weekly usage")


def schedule_daily_message(client: AsyncWebClient, channel: str) -> AsyncIOScheduler:
    """Post the daily question on schedule from now on (call from the running event loop)."""
    scheduler = AsyncIOScheduler(timezone=JST)
    # a run held up by a busy event loop still posts within the minute
    scheduler.add_job(send_daily_message, DAILY_MESSAGE_TRIGGER, args=[client, channel], misfire_grace_time=60)
    scheduler.start()
    return scheduler


def schedule_weekly_usage(client: AsyncWebClient, channel: str) -> AsyncIOScheduler:
    """Post last week's usage to the log channel every Monday from now on (call from the running event loop)."""
    scheduler = AsyncIOScheduler(timezone=JST)
    scheduler.add_job(send_weekly_usage, WEEKLY_USAGE_TRIGGER, args=[client, channel], misfire_grace_time=3600)
    scheduler.start()
    return scheduler
