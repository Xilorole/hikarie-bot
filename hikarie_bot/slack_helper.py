"""Post the daily question to the output channel on Japanese business days at 06:00 JST."""

from datetime import datetime

import jpholiday
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from slack_sdk.web.async_client import AsyncWebClient

from hikarie_bot.engine import JST
from hikarie_bot.modals import InitialMessage
from hikarie_bot.settings import OUTPUT_CHANNEL

# holidays are skipped when the job runs
DAILY_MESSAGE_TRIGGER = CronTrigger(day_of_week="mon-fri", hour=6, timezone=JST)


async def send_daily_message(client: AsyncWebClient) -> None:
    """Post the daily question, unless today is a holiday in Japan."""
    if jpholiday.is_holiday(datetime.now(JST).date()):
        return
    message = InitialMessage()
    await client.chat_postMessage(channel=OUTPUT_CHANNEL, blocks=message.render(), text=message.to_text())


def schedule_daily_message(client: AsyncWebClient) -> AsyncIOScheduler:
    """Post the daily question on schedule from now on (call from the running event loop)."""
    scheduler = AsyncIOScheduler(timezone=JST)
    # a run held up by a busy event loop still posts within the minute
    scheduler.add_job(send_daily_message, DAILY_MESSAGE_TRIGGER, args=[client], misfire_grace_time=60)
    scheduler.start()
    return scheduler
