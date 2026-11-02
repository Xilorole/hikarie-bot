"""Read arrival events from the Slack channel into arrival_event.

The first run reads the whole channel. Later runs read top-level messages from one day
before the stored position (the newest ts seen; thread replies arrive within the same
day) and fetch only the bot threads whose latest reply is newer than that position. A thread whose
replies were not all read (e.g. missing from a recorded cache) holds the position back, so it is read
again next time. Events are keyed by the Slack message ts, so syncing is idempotent.

Slack data comes from a SlackSource: the live API, the API while recording raw
responses, or a recorded cache (offline). Recorded files have the shape
``{"request": {...}, "fetched_at": ..., "response": <Slack JSON body>}``.
"""

import json
import re
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from loguru import logger
from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from hikarie_bot.engine import JST, UserLevel, compute, to_jst_wall_clock
from hikarie_bot.models import (
    Achievement,
    ArrivalEvent,
    GuestArrivalInfo,
    SyncState,
    User,
    UserBadge,
    UserInfoRaw,
)
from hikarie_bot.settings import BOT_ID

Message = dict[str, Any]

PAGE_SIZE = 200
ARRIVAL_EVENT_TYPE = "hikarie_arrival"
THREAD_OVERLAP = timedelta(days=1)

# Posts without arrival metadata are read from their text. The retired v1/v2 bots posted only the day's
# fastest arrival; their history is closed, so its time window identifies them without their bot IDs.
CURRENT_ARRIVAL = re.compile(r"(?:出社登録しました！|本日の最速出社:).*?<@([A-Z0-9]+)>")
LEGACY_ARRIVAL = re.compile(r"最速出社申告ユーザ：<@([A-Z0-9]+)>")
V1_START = datetime(2022, 5, 30, tzinfo=JST)  # earlier posts are a trial run
V2_START = datetime(2023, 11, 1, tzinfo=JST)
V3_START = datetime(2024, 10, 3, tzinfo=JST)


class SlackSource(Protocol):
    """Where channel messages come from."""

    def history(self, channel: str, oldest: str | None) -> AsyncIterator[Message]:
        """Yield top-level messages with ts >= oldest (all when None)."""
        ...

    async def replies(self, channel: str, ts: str) -> list[Message]:
        """Return a thread's messages, the parent first."""
        ...


class LiveSlackSource:
    """Read from the Slack Web API. Rate limits are left to the client's retry handlers."""

    def __init__(self, client: AsyncWebClient) -> None:
        """Initialize the LiveSlackSource class."""
        self.client = client

    async def history_pages(self, channel: str, oldest: str | None) -> AsyncIterator[tuple[dict, dict]]:
        """Yield (request params, response body) for each history page."""
        cursor = None
        while True:
            params: dict[str, Any] = {"channel": channel, "limit": PAGE_SIZE, "include_all_metadata": True}
            if oldest:
                params["oldest"] = oldest
            if cursor:
                params["cursor"] = cursor
            body = (await self.client.conversations_history(**params)).data
            yield params, body
            cursor = body.get("response_metadata", {}).get("next_cursor")
            if not body.get("has_more") or not cursor:
                return

    async def reply_pages(self, channel: str, ts: str) -> AsyncIterator[tuple[dict, dict]]:
        """Yield (request params, response body) for each page of a thread."""
        cursor = None
        while True:
            params: dict[str, Any] = {"channel": channel, "ts": ts, "limit": PAGE_SIZE, "include_all_metadata": True}
            if cursor:
                params["cursor"] = cursor
            body = (await self.client.conversations_replies(**params)).data
            yield params, body
            cursor = body.get("response_metadata", {}).get("next_cursor")
            if not body.get("has_more") or not cursor:
                return

    async def history(self, channel: str, oldest: str | None) -> AsyncIterator[Message]:
        """Yield top-level messages with ts >= oldest."""
        async for _, body in self.history_pages(channel, oldest):
            for message in body.get("messages", []):
                yield message

    async def replies(self, channel: str, ts: str) -> list[Message]:
        """Return a thread's messages."""
        return [message async for _, body in self.reply_pages(channel, ts) for message in body.get("messages", [])]


class RecordingSlackSource(LiveSlackSource):
    """Read from the Slack Web API and save every raw response under cache_dir/<channel>/."""

    def __init__(self, client: AsyncWebClient, cache_dir: Path) -> None:
        """Initialize the RecordingSlackSource class."""
        super().__init__(client)
        self.cache_dir = cache_dir
        self.run = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")

    def _save(self, path: Path, method: str, params: dict, body: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "request": {"method": method, "params": params},
            "fetched_at": datetime.now(UTC).isoformat(),
            "response": body,
        }
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, ensure_ascii=False))
        temporary.rename(path)

    async def history(self, channel: str, oldest: str | None) -> AsyncIterator[Message]:
        """Yield top-level messages and record each page."""
        directory = self.cache_dir / channel / "conversations.history"
        number = 0
        async for params, body in self.history_pages(channel, oldest):
            number += 1
            self._save(directory / f"page-{self.run}-{number:04d}.json", "conversations.history", params, body)
            for message in body.get("messages", []):
                yield message

    async def replies(self, channel: str, ts: str) -> list[Message]:
        """Return a thread's messages and record each page (newest recording wins)."""
        directory = self.cache_dir / channel / "conversations.replies"
        messages: list[Message] = []
        page = 0
        async for params, body in self.reply_pages(channel, ts):
            page += 1
            name = f"{ts}.json" if page == 1 else f"{ts}.p{page}.json"
            self._save(directory / name, "conversations.replies", params, body)
            messages += body.get("messages", [])
        return messages


class CachedSlackSource:
    """Read recorded responses from cache_dir/<channel>/ without network access.

    History pages from several recordings are merged by ts; the latest fetch wins.
    """

    def __init__(self, cache_dir: Path) -> None:
        """Initialize the CachedSlackSource class."""
        self.cache_dir = cache_dir

    @staticmethod
    def _records(paths: Iterable[Path]) -> list[dict]:
        records = [json.loads(path.read_text()) for path in paths]
        return sorted(records, key=lambda record: record["fetched_at"])

    async def history(self, channel: str, oldest: str | None) -> AsyncIterator[Message]:
        """Yield recorded top-level messages with ts >= oldest, newest first like the API."""
        pages = (self.cache_dir / channel / "conversations.history").glob("page-*.json")
        messages = {
            message["ts"]: message for record in self._records(pages) for message in record["response"]["messages"]
        }
        for ts in sorted(messages, key=float, reverse=True):
            if oldest is None or float(ts) >= float(oldest):
                yield messages[ts]

    async def replies(self, channel: str, ts: str) -> list[Message]:
        """Return a recorded thread, or an empty list if it was never recorded."""
        directory = self.cache_dir / channel / "conversations.replies"
        first = directory / f"{ts}.json"
        if not first.exists():
            return []
        pages = [first, *sorted(directory.glob(f"{ts}.p*.json"), key=lambda path: int(path.stem.split(".p")[-1]))]
        return [message for path in pages for message in json.loads(path.read_text())["response"]["messages"]]


@dataclass
class ParsedArrival:
    """An arrival read from a Slack message."""

    user_id: str
    occurred_at: datetime
    source: str
    slack_ts: str


def arrival_metadata(user_id: str, occurred_at: datetime) -> dict[str, Any]:
    """Return the Slack message metadata the bot attaches to an arrival's thread post.

    It records the button press time, so a rebuild from Slack restores it exactly
    instead of using the post's (slightly later) ts.
    """
    return {
        "event_type": ARRIVAL_EVENT_TYPE,
        "event_payload": {"user_id": user_id, "occurred_at": occurred_at.astimezone(UTC).isoformat()},
    }


def parse_arrival(message: Message) -> ParsedArrival | None:
    """Return the arrival a bot message records, if any.

    The bot's arrival metadata wins; older posts are read from their text and ts.
    """
    metadata = message.get("metadata") or {}
    if message.get("bot_id") == BOT_ID and metadata.get("event_type") == ARRIVAL_EVENT_TYPE:
        payload = metadata["event_payload"]
        return ParsedArrival(
            user_id=payload["user_id"],
            occurred_at=datetime.fromisoformat(payload["occurred_at"]),
            source="slack_v3",
            slack_ts=message["ts"],
        )
    text = message.get("text") or ""
    posted_at = datetime.fromtimestamp(float(message["ts"]), UTC)
    if message.get("bot_id") == BOT_ID and (match := CURRENT_ARRIVAL.search(text)):
        source = "slack_v3"
    elif (
        message.get("subtype") == "bot_message"
        and V1_START <= posted_at < V3_START
        and (match := LEGACY_ARRIVAL.search(text))
    ):
        source = "slack_v1" if posted_at < V2_START else "slack_v2"
    else:
        return None
    return ParsedArrival(user_id=match.group(1), occurred_at=posted_at, source=source, slack_ts=message["ts"])


@dataclass
class SyncResult:
    """What one sync read and stored."""

    messages: int = 0
    threads: int = 0
    inserted: int = 0
    since: str | None = None  # the oldest ts read; None for a full read of the channel


async def sync_channel(session: Session, source: SlackSource, channel: str) -> SyncResult:
    """Ingest new arrival events from the channel and advance its sync position."""
    if not BOT_ID:
        # Without it no current arrival is recognized and the sync would silently store almost nothing.
        msg = "BOT_ID must be set to sync"
        raise ValueError(msg)
    state = session.get(SyncState, channel)
    synced_until = float(state.synced_until) if state else None
    oldest = None if synced_until is None else str(synced_until - THREAD_OVERLAP.total_seconds())
    logger.info("Syncing {} from {}", channel, oldest or "the beginning")

    result = SyncResult(since=oldest)
    arrivals: list[ParsedArrival] = []
    # The position is the newest ts seen, replies included, so unchanged threads are skipped next time.
    seen = [state.synced_until] if state else []
    unread_threads: list[str] = []
    async for message in source.history(channel, oldest):
        result.messages += 1
        seen.append(message["ts"])
        if arrival := parse_arrival(message):
            arrivals.append(arrival)
        has_new_replies = synced_until is None or float(message.get("latest_reply", "0")) > synced_until
        if message.get("bot_id") == BOT_ID and message.get("reply_count") and has_new_replies:
            result.threads += 1
            replies = (await source.replies(channel, message["ts"]))[1:]
            if len(replies) < message["reply_count"]:
                logger.warning(
                    "Thread {} returned {}/{} replies; reading it again next time",
                    message["ts"],
                    len(replies),
                    message["reply_count"],
                )
                unread_threads.append(message["ts"])
            seen += [reply["ts"] for reply in replies]
            arrivals += [arrival for reply in replies if (arrival := parse_arrival(reply))]
    latest_ts = min(unread_threads, key=float) if unread_threads else max(seen, key=float, default=None)

    if arrivals:
        statement = insert(ArrivalEvent).on_conflict_do_nothing(index_elements=["slack_ts"])
        recorded_at = datetime.now(UTC)
        rows = [
            {
                "user_id": arrival.user_id,
                "occurred_at": arrival.occurred_at,
                "source": arrival.source,
                "slack_ts": arrival.slack_ts,
                "recorded_at": recorded_at,
            }
            for arrival in arrivals
        ]
        count = select(func.count()).select_from(ArrivalEvent)
        before = session.scalar(count) or 0
        session.execute(statement, rows)
        result.inserted = (session.scalar(count) or 0) - before
    if latest_ts is not None:
        session.merge(SyncState(channel_id=channel, synced_until=latest_ts, updated_at=datetime.now(UTC)))
    session.commit()
    logger.info("Synced {}: {}", channel, result)
    return result


DERIVED_TABLES = [Achievement, UserBadge, UserInfoRaw, GuestArrivalInfo, User]


def rebuild_derived_tables(session: Session) -> int:
    """Recompute ranks, badges and scores from arrival_event, replacing the derived tables.

    Returns the number of counted arrivals (the first of each user's day).
    """
    events = session.execute(
        select(ArrivalEvent.user_id, ArrivalEvent.occurred_at).order_by(ArrivalEvent.occurred_at, ArrivalEvent.id)
    ).all()
    engine = compute((user_id, to_jst_wall_clock(occurred_at)) for user_id, occurred_at in events)

    # Core inserts skip the ORM hooks that copy user_id into user_info_raw_id, so set it here.
    arrivals, achievements, snapshots, users = [], [], [], {}
    for result in engine.results:
        level = vars(UserLevel.of(result.previous_score, result.current_score))
        scores = {"current_score": result.current_score, "previous_score": result.previous_score}
        arrivals.append(
            {
                "id": result.id,
                "user_id": result.user_id,
                "user_info_raw_id": result.user_id,
                "arrival_time": result.time,
                "arrival_rank": result.rank,
                "acquired_score_sum": result.score_sum,
            }
        )
        achievements += [
            {
                "user_id": result.user_id,
                "user_info_raw_id": result.user_id,
                "arrival_id": result.id,
                "badge_id": badge_id,
                "achieved_time": result.time,
            }
            for badge_id in result.badge_ids
        ]
        snapshots.append({"user_id": result.user_id, "update_datetime": result.time, **scores, **level})
        users[result.user_id] = {"id": result.user_id, "update_datetime": result.time, **scores, **level}
    user_badges = [
        {
            "user_id": user_id,
            "user_info_raw_id": user_id,
            "badge_id": badge_id,
            "initially_acquired_datetime": tally.first,
            "last_acquired_datetime": tally.last,
            "count": tally.count,
        }
        for (user_id, badge_id), tally in engine.user_badges.items()
    ]

    for model in DERIVED_TABLES:
        session.execute(delete(model))
    for model, rows in (
        (User, list(users.values())),
        (GuestArrivalInfo, arrivals),
        (Achievement, achievements),
        (UserInfoRaw, snapshots),
        (UserBadge, user_badges),
    ):
        if rows:
            session.execute(insert(model), rows)
    session.commit()
    logger.info("Rebuilt derived tables from {} events ({} counted arrivals)", len(events), len(engine.results))
    return len(engine.results)
