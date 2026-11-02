import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from asyncclick.testing import CliRunner
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hikarie_bot import slack_helper, sync
from hikarie_bot.migrations import init_database
from hikarie_bot.models import ArrivalEvent, GuestArrivalInfo, SyncState, User
from hikarie_bot.sync import (
    CachedSlackSource,
    LiveSlackSource,
    RecordingSlackSource,
    parse_arrival,
    rebuild_derived_tables,
    sync_channel,
)

CHANNEL = "C0TEST"
BOT, V1, V2 = "B0V3", "B0V1", "B0V2"
DAY = 86400.0
T0 = 1_760_000_000.0  # 2025-10-09 (JST morning)


@pytest.fixture(autouse=True)
def bot_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give the three bot generations distinct IDs (they are empty under ENV=test)."""
    for module in (slack_helper, sync):
        monkeypatch.setattr(module, "BOT_ID", BOT)
        monkeypatch.setattr(module, "V1_BOT_ID", V1)
        monkeypatch.setattr(module, "V2_BOT_ID", V2)


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
        self.oldest: list[str | None] = []

    async def history(self, channel: str, oldest: str | None):  # noqa: ANN201
        """Yield messages newest first, like the API."""
        self.oldest.append(oldest)
        for message in sorted(self.messages, key=lambda m: float(m["ts"]), reverse=True):
            if oldest is None or float(message["ts"]) >= float(oldest):
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
        {"ts": ts(T0 - 400 * DAY), "bot_id": V1, "text": "<@U3> 最速出社"},
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
    assert parse_arrival({"ts": ts(T0), "bot_id": V2, "text": "<@U2> さん"}).source == "slack_v2"
    assert parse_arrival(daily_post(T0)) is None
    assert parse_arrival({"ts": ts(T0), "user": "U1", "text": "<@U2> おはよう"}) is None
    assert parse_arrival({"ts": ts(T0), "bot_id": BOT, "subtype": "channel_join", "text": "<@U4>"}) is None


@pytest.mark.asyncio
async def test_first_sync_reads_whole_channel_and_bot_threads(session: Session) -> None:
    """The first sync reads everything once and fetches only bot threads."""
    source = channel_with_two_days()

    result = await sync_channel(session, source, CHANNEL)

    assert source.oldest == [None]
    assert sorted(source.fetched) == [ts(T0), ts(T0 + DAY)]
    events = session.query(ArrivalEvent).order_by(ArrivalEvent.occurred_at).all()
    assert [(e.user_id, e.source) for e in events] == [
        ("U3", "slack_v1"),
        ("U1", "slack_v3"),
        ("U2", "slack_v3"),
        ("U1", "slack_v3"),
    ]
    assert result.inserted == 4  # the broadcast is stored once
    assert session.get(SyncState, CHANNEL).synced_until == ts(T0 + DAY + 3600)  # newest reply


@pytest.mark.asyncio
async def test_catch_up_reads_one_day_back_and_only_threads_with_new_replies(session: Session) -> None:
    """Later syncs overlap by a day, skip unchanged threads, and stay idempotent."""
    source = channel_with_two_days()
    await sync_channel(session, source, CHANNEL)
    synced_until = float(session.get(SyncState, CHANNEL).synced_until)

    # a late reply arrives in day 2's thread, and day 3 is posted
    day2, day3 = T0 + DAY, T0 + 2 * DAY
    late = point_reply(day2 + 9000, day2, "U2")
    source.threads[ts(day2)].append(late)
    source.messages[4] = daily_post(day2, [m["ts"] for m in source.threads[ts(day2)]])
    source.threads[ts(day3)] = [point_reply(day3 + 60, day3, "U5")]
    source.messages.append(daily_post(day3, [source.threads[ts(day3)][0]["ts"]]))
    source.fetched.clear()

    result = await sync_channel(session, source, CHANNEL)

    assert source.oldest[-1] == str(synced_until - DAY)
    assert sorted(source.fetched) == [ts(day2), ts(day3)]  # day 1's thread is unchanged
    assert result.inserted == 2
    assert session.query(ArrivalEvent).count() == 6

    source.fetched.clear()
    again = await sync_channel(session, source, CHANNEL)
    assert again.inserted == 0
    assert source.fetched == []


class FakeClient:
    """AsyncWebClient stand-in that pages history two messages at a time."""

    def __init__(self, source: FakeSource) -> None:
        """Serve the given channel."""
        self.source = source

    async def conversations_history(self, **params: Any) -> SimpleNamespace:  # noqa: ANN401
        """Return one page of history."""
        messages = [m async for m in self.source.history(params["channel"], params.get("oldest"))]
        start = int(params.get("cursor") or 0)
        page = messages[start : start + 2]
        more = start + 2 < len(messages)
        cursor = str(start + 2) if more else ""
        data = {"ok": True, "messages": page, "has_more": more, "response_metadata": {"next_cursor": cursor}}
        return SimpleNamespace(data=data)

    async def conversations_replies(self, **params: Any) -> SimpleNamespace:  # noqa: ANN401
        """Return a whole thread."""
        return SimpleNamespace(
            data={"ok": True, "messages": await self.source.replies(params["channel"], params["ts"]), "has_more": False}
        )


@pytest.mark.asyncio
async def test_recorded_cache_replays_the_same_sync(tmp_path: Path) -> None:
    """Recording while syncing live, then syncing from the cache, stores identical events."""
    live, cached = create_engine("sqlite://"), create_engine("sqlite://")
    init_database(live)
    init_database(cached)
    client = FakeClient(channel_with_two_days())

    with Session(live) as session:
        await sync_channel(session, RecordingSlackSource(client, tmp_path), CHANNEL)  # type: ignore[arg-type]
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
    assert (tmp_path / CHANNEL / "conversations.replies" / f"{ts(T0)}.json").exists()
    assert await CachedSlackSource(tmp_path).replies(CHANNEL, "1.000000") == []


@pytest.mark.asyncio
async def test_live_source_pages_until_the_end() -> None:
    """The live source follows next_cursor across pages."""
    source = channel_with_two_days()
    messages = [m async for m in LiveSlackSource(FakeClient(source)).history(CHANNEL, None)]  # type: ignore[arg-type]
    assert [m["ts"] for m in messages] == [m["ts"] async for m in source.history(CHANNEL, None)]


@pytest.mark.asyncio
async def test_rebuild_derived_tables_is_repeatable(session: Session) -> None:
    """Derived tables are replaced, not appended to, on every rebuild."""
    await sync_channel(session, channel_with_two_days(), CHANNEL)

    assert rebuild_derived_tables(session) == 4
    first = [(a.user_id, a.arrival_rank, a.acquired_score_sum) for a in session.query(GuestArrivalInfo)]
    rebuild_derived_tables(session)
    second = [(a.user_id, a.arrival_rank, a.acquired_score_sum) for a in session.query(GuestArrivalInfo)]

    assert first == second
    assert len(first) == 4
    assert {user.id for user in session.query(User)} == {"U1", "U2", "U3"}


@pytest.mark.asyncio
async def test_sync_requires_bot_ids(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """A sync without bot IDs fails instead of silently storing nothing."""
    monkeypatch.setattr(sync, "V2_BOT_ID", "")

    with pytest.raises(ValueError, match="must be set"):
        await sync_channel(session, channel_with_two_days(), CHANNEL)
    assert session.get(SyncState, CHANNEL) is None


@pytest.mark.asyncio
async def test_sync_command_rejects_conflicting_sources(tmp_path: Path) -> None:
    """--from-cache and --record are mutually exclusive."""
    from hikarie_bot.__main__ import sync as sync_command  # imports the Slack app

    result = await CliRunner().invoke(sync_command, ["--from-cache", str(tmp_path), "--record", str(tmp_path)])

    assert result.exit_code != 0
    assert "cannot be combined" in result.output
