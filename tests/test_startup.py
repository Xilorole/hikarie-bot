from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hikarie_bot import slack_helper, startup, sync
from hikarie_bot.migrations import init_database
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
            "latest_reply": f"{T0 + 120:.6f}",
        }
        self.thread = [
            {
                "ts": f"{T0 + 60 * (i + 1):.6f}",
                "bot_id": BOT,
                "text": f"*09:00* 出社登録しました！ <@{user}>さんのポイント",
            }
            for i, user in enumerate(SECRET_USERS)
        ]

    async def history(self, channel: str, oldest: str | None):  # noqa: ANN201
        """Yield the daily post."""
        if oldest is None or float(self.parent["ts"]) >= float(oldest):
            yield self.parent

    async def replies(self, channel: str, ts: str) -> list[dict[str, Any]]:
        """Return the thread."""
        return [self.parent, *self.thread]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Run startup against a fresh database and capture what is posted."""
    engine = create_engine("sqlite://")
    initialized: list = []

    def ensure_database() -> Any:  # noqa: ANN401
        if not initialized:
            initialized.append(init_database(engine))
        return initialized[0]

    @contextmanager
    def get_db() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(startup, "ensure_database", ensure_database)
    monkeypatch.setattr(startup, "get_db", get_db)
    for module in (slack_helper, sync):
        monkeypatch.setattr(module, "BOT_ID", BOT)
        monkeypatch.setattr(module, "V1_BOT_ID", "B0V1")
        monkeypatch.setattr(module, "V2_BOT_ID", "B0V2")
    client = AsyncMock()
    client.restart = initialized.clear  # a new process initializes the database again
    return client


def posted(client: AsyncMock) -> list[str]:
    """Return the texts posted to the log channel."""
    assert all(call.kwargs["channel"] == "C0LOG" for call in client.chat_postMessage.await_args_list)
    return [call.kwargs["text"] for call in client.chat_postMessage.await_args_list]


@pytest.mark.asyncio
async def test_first_start_reports_each_step_without_personal_data(client: AsyncMock) -> None:
    """The first start announces the full read and summarizes every step with counts only."""
    reporter = StartupReporter(client=client, channel="C0LOG", version="1.2.3")

    await prepare(reporter, Source(), CHANNEL)
    await reporter.post(reporter.summary())

    texts = posted(client)
    assert texts[0] == "starting application (v1.2.3)"
    assert texts[1].startswith("first start: reading the whole channel")
    summary = texts[-1]
    assert summary.startswith(":white_check_mark: application started (v1.2.3) in ")
    assert "*database*: schema 0000 (migrated from empty) · badge definitions 19 types / 287 badges" in summary
    assert "*slack sync*: whole channel · 1 messages · 1 threads · 2 new events" in summary
    assert "*scores*: 2 events → 2 arrivals · 2 users · " in summary
    assert not any(user in text for text in texts for user in SECRET_USERS)


@pytest.mark.asyncio
async def test_restart_reports_the_catch_up(client: AsyncMock) -> None:
    """A restart has no full-read notice and reports where the catch-up started."""
    await prepare(StartupReporter(client=client, channel="C0LOG", version="1.2.3"), Source(), CHANNEL)
    client.chat_postMessage.reset_mock()
    client.restart()
    reporter = StartupReporter(client=client, channel="C0LOG", version="1.2.3")

    await prepare(reporter, Source(), CHANNEL)
    summary = reporter.summary()

    assert not any(text.startswith("first start") for text in posted(client))
    assert "*slack sync*: since 2025-10-08 17:55 JST · 1 messages · 0 threads · 0 new events" in summary
    assert "*database*: schema 0000 (up to date)" in summary


@pytest.mark.asyncio
async def test_failed_step_reports_only_its_name_and_error_type(client: AsyncMock) -> None:
    """The exception message may contain data, so only the step and the error type are posted."""
    source = Source()
    source.replies = AsyncMock(side_effect=RuntimeError(f"bad reply from {SECRET_USERS[0]}"))
    reporter = StartupReporter(client=client, channel="C0LOG", version="1.2.3")

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
    reporter = StartupReporter(client=client, channel="C0LOG", version="1.2.3")

    await prepare(reporter, Source(), CHANNEL)

    assert [step.name for step in reporter.steps] == ["database", "slack sync", "scores"]
