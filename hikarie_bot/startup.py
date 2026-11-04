"""Prepare the database on startup and report each step to the log channel.

Each step is posted as its own message when it finishes, so a slow step (the first full
read of the channel) shows how far startup has got.

The report carries only counts, durations and schema revisions: never
user IDs, names or message text. A failed step reports its name and exception type;
the exception message (which may contain data) stays in the process log.
"""

import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter

from loguru import logger
from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from hikarie_bot.arrivals import compute_arrivals
from hikarie_bot.database import ensure_database, get_db
from hikarie_bot.engine import BadgeEngine
from hikarie_bot.exceptions import DatabaseLocationError, InMemoryDatabaseError
from hikarie_bot.migrations import InitResult, UnversionedDatabaseError
from hikarie_bot.models import ArrivalEvent, ItemPickEvent
from hikarie_bot.settings import get_settings
from hikarie_bot.sync import SlackSource, SyncResult, sync_channel

PUBLIC_ERRORS = (DatabaseLocationError, InMemoryDatabaseError, UnversionedDatabaseError)


def current_revision() -> str:
    """Return the short commit of the running code.

    Images get it from the build (APP_REVISION); a source checkout asks git.
    """
    if revision := get_settings().app_revision:
        return revision[:7]
    try:
        return subprocess.run(  # noqa: RUF100, S603  # fixed git command; older ruff flags it
            ["git", "rev-parse", "--short=7", "HEAD"],  # noqa: S607
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        ).stdout.strip()
    except OSError, subprocess.SubprocessError:
        return "unknown"


@dataclass
class Step:
    """One finished startup step."""

    name: str
    detail: str
    seconds: float


@dataclass
class StepDetail:
    """Filled in by a step while it runs."""

    text: str = ""


@dataclass
class StartupReporter:
    """Post startup progress and a summary to the log channel."""

    client: AsyncWebClient
    channel: str
    revision: str
    steps: list[Step] = field(default_factory=list)
    started: float = field(default_factory=perf_counter)

    async def post(self, text: str) -> None:
        """Post to the log channel; a failure to post never stops startup."""
        try:
            await self.client.chat_postMessage(channel=self.channel, text=text)
        except Exception:  # noqa: BLE001
            logger.exception("Could not post to the log channel")

    @asynccontextmanager
    async def step(self, name: str) -> AsyncIterator[StepDetail]:
        """Time a step and record its detail; report the failure and re-raise if it fails."""
        started = perf_counter()
        detail = StepDetail()
        try:
            yield detail
        except Exception as error:
            # configuration errors explain themselves without data; others may carry data in the message
            reason = str(error) if isinstance(error, PUBLIC_ERRORS) else "details in the process log"
            await self.post(
                f":warning: startup failed at *{name}* after {perf_counter() - started:.1f}s: "
                f"`{type(error).__name__}` ({reason})"
            )
            raise
        step = Step(name, detail.text, perf_counter() - started)
        self.steps.append(step)
        await self.post(f"*{step.name}*: {step.detail} ({step.seconds:.1f}s)")

    def summary(self) -> str:
        """Return the closing message, posted once the bot is ready."""
        return f":white_check_mark: application started (rev {self.revision}) in {perf_counter() - self.started:.1f}s"


def describe_database(result: InitResult) -> str:
    """Describe the schema revision."""
    if result.revision_before == result.revision:
        return f"schema {result.revision} (up to date)"
    return f"schema {result.revision} (migrated from {result.revision_before or 'empty'})"


def describe_sync(result: SyncResult) -> str:
    """Describe what a Slack sync read and stored."""
    return (
        f"whole channel · {result.messages} messages · {result.threads} threads · {result.inserted} new events"
        f" · {result.picks_inserted} new item picks"
    )


def describe_items(session: Session, engine: BadgeEngine) -> str:
    """Describe the item picks and the share of all points that items gave (to watch for inflation)."""
    picks = session.scalar(select(func.count()).select_from(ItemPickEvent)) or 0
    total = sum(result.score_sum for result in engine.results)
    from_items = sum(effect.points for result in engine.results for effect in result.item_effects)
    share = 100 * from_items / total if total else 0
    return f"{picks} item picks · items {share:.1f}% of points"


async def resolve_slack_ids(client: AsyncWebClient) -> None:
    """Fill the bot, workspace and app IDs from Slack with the bot token; a value that is already set wins.

    auth.test gives the bot and workspace IDs and bots.info the app ID. The app ID only builds the link to
    the Home, so if bots.info fails (it needs the users:read scope) the link is left out and startup goes on.
    """
    settings = get_settings()
    if not (settings.bot_id and settings.slack_workspace_id):
        auth = await client.auth_test()
        settings.bot_id = settings.bot_id or auth["bot_id"]
        settings.slack_workspace_id = settings.slack_workspace_id or auth["team_id"]
    if not settings.slack_app_id:
        try:
            settings.slack_app_id = (await client.bots_info(bot=settings.bot_id))["bot"]["app_id"]
        except Exception:  # noqa: BLE001
            logger.warning("Could not read the app ID from Slack (bots.info needs users:read); no link to the Home")


async def prepare(reporter: StartupReporter, source: SlackSource, channel: str) -> None:
    """Migrate, read Slack into an empty database and compute scores once (a check), reporting each step.

    Live arrivals are stored before they are posted, so Slack never holds one the database lacks; only an
    empty database (first start, or a lost volume) needs the channel read.
    """
    await reporter.post(f"starting application (rev {reporter.revision})")

    async with reporter.step("database") as step:
        step.text = describe_database(ensure_database())

    with get_db() as session:
        stored = session.scalar(select(func.count()).select_from(ArrivalEvent)) or 0
        if stored:
            async with reporter.step("slack sync") as step:
                step.text = f"skipped ({stored} events stored)"
        else:
            await reporter.post(
                "first start: reading the whole channel from Slack (about 10 minutes before the bot answers)"
            )
            async with reporter.step("slack sync") as step:
                step.text = describe_sync(await sync_channel(session, source, channel))

        async with reporter.step("scores") as step:
            engine = compute_arrivals(session)
            events = session.scalar(select(func.count()).select_from(ArrivalEvent))
            badges = sum(len(result.badge_ids) for result in engine.results)
            step.text = (
                f"{events} events → {len(engine.results)} arrivals · {len(engine.users)} users · {badges} badges earned"
                f" · {describe_items(session, engine)}"
            )
