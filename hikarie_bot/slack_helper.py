"""Post the daily question to the output channel on Japanese business days at 06:00 JST."""

from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from slack_sdk.web.async_client import AsyncWebClient

from hikarie_bot.engine import JST
from hikarie_bot.modals import InitialMessage
from hikarie_bot.utils import is_jp_bizday

# runs every day; days off are skipped by the same rule the streak badges use
DAILY_MESSAGE_TRIGGER = CronTrigger(hour=6, timezone=JST)


async def send_daily_message(client: AsyncWebClient, channel: str) -> None:
    """Post the daily question on Japanese business days (not weekends, holidays, Dec 31 or Jan 1-3)."""
    if not is_jp_bizday(datetime.now(JST).date()):
        return
    message = InitialMessage()
    await client.chat_postMessage(channel=channel, blocks=message.render(), text=message.to_text())


def schedule_daily_message(client: AsyncWebClient, channel: str) -> AsyncIOScheduler:
    """Post the daily question on schedule from now on (call from the running event loop)."""
    scheduler = AsyncIOScheduler(timezone=JST)
    # a run held up by a busy event loop still posts within the minute
    scheduler.add_job(send_daily_message, DAILY_MESSAGE_TRIGGER, args=[client, channel], misfire_grace_time=60)
    scheduler.start()
    return scheduler
