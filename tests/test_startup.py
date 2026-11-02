from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import Engine

from hikarie_bot import startup
from hikarie_bot.models import ensure_database
from hikarie_bot.settings import Settings
from hikarie_bot.startup import StartupReporter, prepare

CHANNEL = "C0OUT"
BOT = "B0BOT"
SECRET_USERS = ["U0SECRETA", "U0SECRETB"]
T0 = 1_760_000_000.0  # 2025-10-09 17:53 JST


class Source:
    """A channel with one daily thread where both users arrived."""

    def __init__(self) -> None:
        """Build the channel."""
        self.parent = {
            "ts": f"{T0:.6f}",
            "bot_id": BOT,
            "text": "ヒカリエに出社してる？",
            "thread_ts": f"{T0:.6f}",
            "reply_count": 2,
        }
        self.thread = [
            {
                "ts": f"{T0 + 60 * (i + 1):.6f}",
                "bot_id": BOT,
                "text": f"*09:00* 出社登録しました！ <@{user}>さんのポイント",
            }
            for i, user in enumerate(SECRET_USERS)
        ]

    async def history(self, channel: str):  # noqa: ANN201
        """Yield the daily post."""
        yield self.parent

    async def replies(self, channel: str, ts: str) -> list[dict[str, Any]]:
        """Return the thread."""
        return [self.parent, *self.thread]


@pytest.fixture
def client(app_database: Engine, settings: Settings) -> AsyncMock:
    """Run startup against a fresh database and capture what is posted."""
    settings.bot_id = BOT
    client = AsyncMock()
    client.restart = ensure_database.cache_clear  # a new process initializes the database again
    return client


def posted(client: AsyncMock) -> list[str]:
    """Return the texts posted to the log channel."""
    assert all(call.kwargs["channel"] == "C0LOG" for call in client.chat_postMessage.await_args_list)
    return [call.kwargs["text"] for call in client.chat_postMessage.await_args_list]


@pytest.mark.asyncio
async def test_first_start_reports_each_step_without_personal_data(client: AsyncMock) -> None:
    """The first start announces the full read and summarizes every step with counts only."""
    reporter = StartupReporter(client=client, channel="C0LOG", revision="abc1234")

    await prepare(reporter, Source(), CHANNEL)
    await reporter.post(reporter.summary())

    texts = posted(client)
    assert len(texts) == 6  # one message per section
    assert texts[0] == "starting application (rev abc1234)"
    assert texts[1].startswith("*database*: schema 0002 (migrated from empty) (")
    assert texts[2].startswith("first start: reading the whole channel")
    assert texts[3].startswith("*slack sync*: whole channel · 1 messages · 1 threads · 2 new events (")
    assert texts[4].startswith("*scores*: 2 events → 2 arrivals · 2 users · ")
    assert texts[5].startswith(":white_check_mark: application started (rev abc1234) in ")
    assert not any(user in text for text in texts for user in SECRET_USERS)


@pytest.mark.asyncio
async def test_restart_skips_the_sync_and_reports_only_a_count(client: AsyncMock) -> None:
    """With events stored there is no full-read notice and Slack is not read."""
    await prepare(StartupReporter(client=client, channel="C0LOG", revision="abc1234"), Source(), CHANNEL)
    client.chat_postMessage.reset_mock()
    client.restart()
    source = Source()
    source.history = Mock(side_effect=AssertionError("Slack must not be read"))
    reporter = StartupReporter(client=client, channel="C0LOG", revision="abc1234")

    await prepare(reporter, source, CHANNEL)

    texts = posted(client)
    assert not any(text.startswith("first start") for text in texts)
    assert texts[1].startswith("*database*: schema 0002 (up to date)")
    assert texts[2].startswith("*slack sync*: skipped (2 events stored) (")
    assert texts[3].startswith("*scores*: 2 events → 2 arrivals")
    assert not any(user in text for text in texts for user in SECRET_USERS)


@pytest.mark.asyncio
async def test_failed_step_reports_only_its_name_and_error_type(client: AsyncMock) -> None:
    """The exception message may contain data, so only the step and the error type are posted."""
    source = Source()
    source.replies = AsyncMock(side_effect=RuntimeError(f"bad reply from {SECRET_USERS[0]}"))
    reporter = StartupReporter(client=client, channel="C0LOG", revision="abc1234")

    with pytest.raises(RuntimeError):
        await prepare(reporter, source, CHANNEL)

    warning = posted(client)[-1]
    assert warning.startswith(":warning: startup failed at *slack sync* after ")
    assert "`RuntimeError`" in warning
    assert SECRET_USERS[0] not in warning


@pytest.mark.asyncio
async def test_posting_failure_does_not_stop_startup(client: AsyncMock) -> None:
    """If the log channel cannot be reached, startup still completes."""
    client.chat_postMessage.side_effect = RuntimeError("channel_not_found")
    reporter = StartupReporter(client=client, channel="C0LOG", revision="abc1234")

    await prepare(reporter, Source(), CHANNEL)

    assert [step.name for step in reporter.steps] == ["database", "slack sync", "scores"]


def test_current_revision_prefers_the_build_argument(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    """Images report the commit they were built from; a checkout falls back to git."""
    settings.app_revision = "6709a7d1234567890"
    assert startup.current_revision() == "6709a7d"

    settings.app_revision = ""
    monkeypatch.setattr(startup.subprocess, "run", Mock(side_effect=FileNotFoundError("git")))
    assert startup.current_revision() == "unknown"
