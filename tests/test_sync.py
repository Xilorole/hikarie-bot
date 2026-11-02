import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from asyncclick.testing import CliRunner
from loguru import logger
from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hikarie_bot import __main__ as bot
from hikarie_bot.arrivals import compute_arrivals
from hikarie_bot.migrations import init_database
from hikarie_bot.models import ArrivalEvent
from hikarie_bot.settings import Settings
from hikarie_bot.sync import (
    CachedSlackSource,
    LiveSlackSource,
    RecordingSlackSource,
    arrival_metadata,
    parse_arrival,
    sync_channel,
)

CHANNEL = "C0TEST"
BOT = "B0V3"
DAY = 86400.0
T0 = 1_760_000_000.0  # 2025-10-09 (JST morning)
V1_ERA = datetime(2023, 6, 1, 0, 30, tzinfo=UTC).timestamp()
V2_ERA = datetime(2024, 6, 3, 0, 30, tzinfo=UTC).timestamp()


@pytest.fixture(autouse=True)
def bot_id(settings: Settings) -> None:
    """Give the bot an ID (it is empty under ENV=test)."""
    settings.bot_id = BOT


@pytest.fixture
def session() -> Iterator[Session]:
    """Provide a migrated in-memory database."""
    engine = create_engine("sqlite://")
    init_database(engine)
    with Session(engine) as db:
        yield db


def ts(value: float) -> str:
    """Format a Slack ts."""
    return f"{value:.6f}"


def daily_post(at: float, replies: list[str] | None = None) -> dict[str, Any]:
    """Return a v3 daily question, with thread metadata when it has replies."""
    message: dict[str, Any] = {"ts": ts(at), "bot_id": BOT, "text": "ヒカリエに出社してる？"}
    if replies:
        message |= {"thread_ts": ts(at), "reply_count": len(replies), "latest_reply": replies[-1]}
    return message


def legacy_post(at: float, user: str) -> dict[str, Any]:
    """Return a v1/v2 fastest-arrival post."""
    return {
        "ts": ts(at),
        "subtype": "bot_message",
        "bot_id": "B0LEGACY",
        "text": f"ヒカリエは正義 :hikarie:\n本日の最速出社申告ユーザ：<@{user}> @ 9:30",
    }


def point_reply(at: float, parent: float, user: str) -> dict[str, Any]:
    """Return a v3 point-get reply in a daily thread."""
    return {
        "ts": ts(at),
        "thread_ts": ts(parent),
        "bot_id": BOT,
        "text": f"*09:00* 出社登録しました！ <@{user}>さんのポイント 10 → *12* (*+2*)",
    }


class FakeSource:
    """In-memory SlackSource that records which threads were fetched."""

    def __init__(self, history: list[dict[str, Any]], threads: dict[str, list[dict[str, Any]]]) -> None:
        """Hold the channel's top-level messages and threads."""
        self.messages = history
        self.threads = threads
        self.fetched: list[str] = []

    async def history(self, channel: str):  # noqa: ANN201
        """Yield messages newest first, like the API."""
        for message in sorted(self.messages, key=lambda m: float(m["ts"]), reverse=True):
            yield message

    async def replies(self, channel: str, thread_ts: str) -> list[dict[str, Any]]:
        """Return the parent and its replies."""
        self.fetched.append(thread_ts)
        parent = next(message for message in self.messages if message["ts"] == thread_ts)
        return [parent, *self.threads[thread_ts]]


def channel_with_two_days() -> FakeSource:
    """Two daily threads, a v1-era arrival, a human thread, and a channel join."""
    day1, day2 = T0, T0 + DAY
    threads = {
        ts(day1): [point_reply(day1 + 3600, day1, "U1"), point_reply(day1 + 7200, day1, "U2")],
        ts(day2): [point_reply(day2 + 3600, day2, "U1")],
        ts(day1 + 100): [point_reply(day1 + 200, day1 + 100, "U9")],  # not a bot thread: ignored
    }
    history = [
        legacy_post(V1_ERA, "U3"),
        daily_post(day1, [m["ts"] for m in threads[ts(day1)]]),
        {
            "ts": ts(day1 + 100),
            "user": "U9",
            "text": "おはよう",
            "thread_ts": ts(day1 + 100),
            "reply_count": 1,
            "latest_reply": ts(day1 + 200),
        },
        threads[ts(day1)][0] | {"subtype": "thread_broadcast"},  # broadcast: also in history
        daily_post(day2, [m["ts"] for m in threads[ts(day2)]]),
        {"ts": ts(day2 + 10), "subtype": "channel_join", "user": "U4", "text": "<@U4> has joined"},
    ]
    return FakeSource(history, threads)


def test_parse_arrival_reads_only_bot_arrivals() -> None:
    """Point-get replies and v1/v2 posts are arrivals; the daily question, people and joins are not."""
    arrival = parse_arrival(point_reply(T0, T0 - 60, "U1"))
    assert arrival is not None
    assert (arrival.user_id, arrival.source, arrival.slack_ts) == ("U1", "slack_v3", ts(T0))
    assert arrival.occurred_at == datetime.fromtimestamp(T0, UTC)
    assert parse_arrival(legacy_post(V1_ERA, "U2")).source == "slack_v1"
    assert parse_arrival(legacy_post(V2_ERA, "U2")).source == "slack_v2"
    assert parse_arrival(daily_post(T0)) is None
    assert parse_arrival({"ts": ts(T0), "user": "U1", "text": "<@U2> おはよう"}) is None
    assert parse_arrival({"ts": ts(T0), "bot_id": BOT, "subtype": "channel_join", "text": "<@U4>"}) is None


def test_parse_arrival_reads_legacy_posts_only_from_their_era() -> None:
    """The fastest-arrival text counts only in the v1/v2 era and only from a bot; v1 click notices do not."""
    assert parse_arrival(legacy_post(T0, "U2")) is None  # a bot posting the old text today
    assert parse_arrival(legacy_post(V1_ERA - 400 * DAY, "U2")) is None  # the trial run before v1
    assert parse_arrival(legacy_post(V1_ERA, "U2") | {"subtype": None, "user": "U9"}) is None
    click = legacy_post(V1_ERA, "U2") | {"text": "ヒカリエに出社してる？ <@U2>さんが出社してるをクリックしました"}
    assert parse_arrival(click) is None


def test_parse_arrival_prefers_the_bots_arrival_metadata() -> None:
    """The press time in the metadata wins over the post's ts; other apps' metadata is ignored."""
    pressed = datetime(2025, 10, 9, 0, 30, 1, 250000, tzinfo=UTC)
    reply = point_reply(T0, T0 - 60, "U1") | {"metadata": arrival_metadata("U1", pressed)}

    arrival = parse_arrival(reply)

    assert arrival is not None
    assert (arrival.user_id, arrival.occurred_at, arrival.slack_ts) == ("U1", pressed, ts(T0))
    assert arrival.occurred_at.tzinfo == UTC
    spoofed = {"ts": ts(T0), "bot_id": "B0OTHER", "text": "hello", "metadata": arrival_metadata("U9", pressed)}
    assert parse_arrival(spoofed) is None


@pytest.mark.asyncio
async def test_sync_reads_whole_channel_and_bot_threads_and_is_idempotent(session: Session) -> None:
    """A sync reads everything and fetches only bot threads; running it again stores nothing new."""
    source = channel_with_two_days()

    result = await sync_channel(session, source, CHANNEL)

    assert sorted(source.fetched) == [ts(T0), ts(T0 + DAY)]
    events = session.query(ArrivalEvent).order_by(ArrivalEvent.occurred_at).all()
    assert [(e.user_id, e.source) for e in events] == [
        ("U3", "slack_v1"),
        ("U1", "slack_v3"),
        ("U2", "slack_v3"),
        ("U1", "slack_v3"),
    ]
    assert (result.messages, result.threads, result.inserted) == (6, 2, 4)  # the broadcast is stored once

    source.fetched.clear()
    again = await sync_channel(session, source, CHANNEL)

    assert sorted(source.fetched) == [ts(T0), ts(T0 + DAY)]  # the whole channel is read every time
    assert again.inserted == 0
    assert session.query(ArrivalEvent).count() == 4


@pytest.mark.asyncio
async def test_sync_stores_replies_that_arrive_later(session: Session) -> None:
    """A manual sync after a gap picks up new threads and late replies, and keeps the stored events."""
    source = channel_with_two_days()
    await sync_channel(session, source, CHANNEL)
    day2, day3 = T0 + DAY, T0 + 2 * DAY
    source.threads[ts(day2)].append(point_reply(day2 + 9000, day2, "U2"))
    source.messages[4] = daily_post(day2, [m["ts"] for m in source.threads[ts(day2)]])
    source.threads[ts(day3)] = [point_reply(day3 + 60, day3, "U5")]
    source.messages.append(daily_post(day3, [source.threads[ts(day3)][0]["ts"]]))

    result = await sync_channel(session, source, CHANNEL)

    assert result.inserted == 2
    assert session.query(ArrivalEvent).count() == 6


@pytest.mark.asyncio
async def test_a_thread_with_fewer_replies_than_counted_warns(session: Session) -> None:
    """A thread missing replies (e.g. from a partial cache) is stored as far as it goes, with a warning."""
    source = channel_with_two_days()
    day2 = ts(T0 + DAY)
    full_thread = source.threads[day2]
    source.threads[day2] = []
    messages: list[str] = []
    logger.enable("hikarie_bot")  # disabled for the test run in conftest
    sink = logger.add(messages.append, level="WARNING", format="{message}")

    try:
        result = await sync_channel(session, source, CHANNEL)
    finally:
        logger.remove(sink)
        logger.disable("hikarie_bot")

    assert result.inserted == 3
    assert [message.strip() for message in messages] == [
        f"Thread {day2} returned 0/1 replies; run the sync again to read the rest"
    ]

    source.threads[day2] = full_thread
    assert (await sync_channel(session, source, CHANNEL)).inserted == 1


class FakeClient(AsyncWebClient):
    """A real AsyncWebClient (so the SDK paginates) whose HTTP layer serves a FakeSource, two messages per page."""

    def __init__(self, source: FakeSource) -> None:
        """Serve the given channel."""
        super().__init__(token="test")  # noqa: S106
        self.source = source
        self.requests: list[dict[str, Any]] = []

    async def _request(self, *, http_verb: str, api_url: str, req_args: dict) -> dict[str, Any]:
        """Return one page of history or of a thread."""
        params = dict(req_args["params"])
        self.requests.append(params)
        if api_url.endswith("conversations.history"):
            messages = [m async for m in self.source.history(params["channel"])]
        else:
            messages = await self.source.replies(params["channel"], params["ts"])
        start = int(params.get("cursor") or 0)
        more = start + 2 < len(messages)
        metadata = {"next_cursor": str(start + 2) if more else ""}
        data = {"ok": True, "messages": messages[start : start + 2], "has_more": more, "response_metadata": metadata}
        return {"data": data, "headers": {}, "status_code": 200}


@pytest.mark.asyncio
async def test_recorded_cache_replays_the_same_sync(tmp_path: Path) -> None:
    """Recording while syncing live, then syncing from the cache, stores identical events."""
    live, cached = create_engine("sqlite://"), create_engine("sqlite://")
    init_database(live)
    init_database(cached)
    client = FakeClient(channel_with_two_days())

    with Session(live) as session:
        await sync_channel(session, RecordingSlackSource(client, tmp_path), CHANNEL)
        live_events = [
            (e.slack_ts, e.user_id, e.source) for e in session.query(ArrivalEvent).order_by(ArrivalEvent.slack_ts)
        ]
    with Session(cached) as session:
        await sync_channel(session, CachedSlackSource(tmp_path), CHANNEL)
        cached_events = [
            (e.slack_ts, e.user_id, e.source) for e in session.query(ArrivalEvent).order_by(ArrivalEvent.slack_ts)
        ]

    assert cached_events == live_events
    pages = sorted((tmp_path / CHANNEL / "conversations.history").glob("page-*.json"))
    assert len(pages) == 3  # 6 messages, 2 per page
    record = json.loads(pages[0].read_text())
    assert record["request"]["method"] == "conversations.history"
    assert record["response"]["ok"] is True
    replies = tmp_path / CHANNEL / "conversations.replies"
    assert (replies / f"{ts(T0)}.json").exists()
    second = json.loads((replies / f"{ts(T0)}.p2.json").read_text())  # the parent and 2 replies take 2 pages
    assert second["request"]["params"]["cursor"] == "2"
    assert second["response"]["has_more"] is False
    assert await CachedSlackSource(tmp_path).replies(CHANNEL, "1.000000") == []


@pytest.mark.asyncio
async def test_live_source_pages_until_the_end() -> None:
    """The live source follows next_cursor across pages of history and of a thread."""
    source = channel_with_two_days()
    client = FakeClient(source)
    live = LiveSlackSource(client)

    messages = [m async for m in live.history(CHANNEL)]
    thread = await live.replies(CHANNEL, ts(T0))

    assert [m["ts"] for m in messages] == [m["ts"] async for m in source.history(CHANNEL)]
    assert [m["ts"] for m in thread] == [m["ts"] for m in await source.replies(CHANNEL, ts(T0))]
    assert [request.get("cursor") for request in client.requests] == [None, "2", "4", None, "2"]


@pytest.mark.asyncio
async def test_synced_events_count_once_per_user_and_day(session: Session) -> None:
    """Syncing again stores nothing new, so the computed arrivals stay the same."""
    await sync_channel(session, channel_with_two_days(), CHANNEL)
    first = [(a.user_id, a.rank, a.score_sum) for a in compute_arrivals(session).results]
    await sync_channel(session, channel_with_two_days(), CHANNEL)
    second = [(a.user_id, a.rank, a.score_sum) for a in compute_arrivals(session).results]

    assert first == second
    assert len(first) == 4
    assert {user_id for user_id, _, _ in first} == {"U1", "U2", "U3"}


@pytest.mark.asyncio
async def test_sync_requires_bot_id(session: Session, settings: Settings) -> None:
    """A sync without the bot ID fails instead of silently storing almost nothing."""
    settings.bot_id = ""

    with pytest.raises(ValueError, match="must be set"):
        await sync_channel(session, channel_with_two_days(), CHANNEL)
    assert session.query(ArrivalEvent).count() == 0


@pytest.mark.asyncio
async def test_sync_command_rejects_conflicting_sources(tmp_path: Path) -> None:
    """--from-cache and --record are mutually exclusive."""
    result = await CliRunner().invoke(bot.sync, ["--from-cache", str(tmp_path), "--record", str(tmp_path)])

    assert result.exit_code != 0
    assert "cannot be combined" in result.output
