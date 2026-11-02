"""Prepare the database on startup and report each step to the log channel.

Each step is posted as its own message when it finishes, so a slow step (the first full
read of the channel) shows how far startup has got.

The report carries only counts, durations, schema revisions and sync positions: never
user IDs, names or message text. A failed step reports its name and exception type;
the exception message (which may contain data) stays in the process log.
"""

import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from loguru import logger
from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy import func, select

from hikarie_bot.engine import JST
from hikarie_bot.exceptions import DatabaseLocationError, InMemoryDatabaseError
from hikarie_bot.migrations import InitResult, UnversionedDatabaseError
from hikarie_bot.models import Achievement, ArrivalEvent, SyncState, User, ensure_database, get_db
from hikarie_bot.settings import get_settings
from hikarie_bot.sync import SlackSource, SyncResult, rebuild_derived_tables, sync_channel

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
    """Describe the schema and badge master data without personal data."""
    if result.revision_before == result.revision:
        schema = f"schema {result.revision} (up to date)"
    else:
        schema = f"schema {result.revision} (migrated from {result.revision_before or 'empty'})"
    master = result.master_data
    return (
        f"{schema} · badge definitions {master.badge_types} types / {master.badges} badges "
        f"({master.badge_types_added + master.badges_added} added, "
        f"{master.badge_types_updated + master.badges_updated} updated)"
    )


def format_ts(ts: str) -> str:
    """Format a Slack ts as JST minutes."""
    return datetime.fromtimestamp(float(ts), UTC).astimezone(JST).strftime("%Y-%m-%d %H:%M JST")


def describe_sync(result: SyncResult) -> str:
    """Describe what a Slack sync read and stored."""
    scope = "whole channel" if result.since is None else f"since {format_ts(result.since)}"
    return f"{scope} · {result.messages} messages · {result.threads} threads · {result.inserted} new events"


async def prepare(reporter: StartupReporter, source: SlackSource, channel: str) -> None:
    """Migrate, sync from Slack and recompute scores, reporting each step."""
    await reporter.post(f"starting application (rev {reporter.revision})")

    async with reporter.step("database") as step:
        step.text = describe_database(ensure_database())

    with get_db() as session:
        if session.get(SyncState, channel) is None:
            await reporter.post(
                "first start: reading the whole channel from Slack (about 10 minutes before the bot answers)"
            )
        async with reporter.step("slack sync") as step:
            step.text = describe_sync(await sync_channel(session, source, channel))

        async with reporter.step("scores") as step:
            arrivals = rebuild_derived_tables(session)
            events = session.scalar(select(func.count()).select_from(ArrivalEvent))
            users = session.scalar(select(func.count()).select_from(User))
            badges = session.scalar(select(func.count()).select_from(Achievement))
            step.text = f"{events} events → {arrivals} arrivals · {users} users · {badges} badges earned"
