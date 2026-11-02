"""Read arrival events from the Slack channel into arrival_event.

A sync always reads the whole channel: every top-level message and every bot thread. The bot stores
an arrival before it posts it, so a running database never lacks an arrival that Slack has; startup
syncs only into an empty database (first start, or a lost volume), and the ``sync`` command is the
manual full read (e.g. after restoring an older backup). Events are keyed by the Slack message ts, so
syncing is idempotent.

Slack data comes from a SlackSource: the live API, the API while recording raw
responses, or a recorded cache (offline). Recorded files have the shape
``{"request": {...}, "fetched_at": ..., "response": <Slack JSON body>}``.
"""

import json
import re
from collections.abc import AsyncIterator, Awaitable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from loguru import logger
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.web.async_slack_response import AsyncSlackResponse
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from hikarie_bot.engine import JST
from hikarie_bot.models import ArrivalEvent
from hikarie_bot.settings import get_settings

Message = dict[str, Any]

PAGE_SIZE = 200
ARRIVAL_EVENT_TYPE = "hikarie_arrival"

# Posts without arrival metadata are read from their text. The retired v1/v2 bots posted only the day's
# fastest arrival; their history is closed, so its time window identifies them without their bot IDs.
CURRENT_ARRIVAL = re.compile(r"(?:出社登録しました！|本日の最速出社:).*?<@([A-Z0-9]+)>")
LEGACY_ARRIVAL = re.compile(r"最速出社申告ユーザ：<@([A-Z0-9]+)>")
V1_START = datetime(2022, 5, 30, tzinfo=JST)  # earlier posts are a trial run
V2_START = datetime(2023, 11, 1, tzinfo=JST)
V3_START = datetime(2024, 10, 3, tzinfo=JST)


class SlackSource(Protocol):
    """Where channel messages come from."""

    def history(self, channel: str) -> AsyncIterator[Message]:
        """Yield every top-level message."""
        ...

    async def replies(self, channel: str, ts: str) -> list[Message]:
        """Return a thread's messages, the parent first."""
        ...


async def _pages(request: Awaitable[AsyncSlackResponse]) -> AsyncIterator[tuple[dict, dict]]:
    """Yield (request params, response body) for each page, following next_cursor.

    The SDK follows the cursor through the client, so its retry handlers (rate limits) apply to every
    page. It reuses one response object and updates its request params in place, so they are copied.
    """
    async for page in await request:
        yield dict(page.req_args["params"]), page.data


class LiveSlackSource:
    """Read from the Slack Web API. Rate limits are left to the client's retry handlers."""

    def __init__(self, client: AsyncWebClient) -> None:
        """Initialize the LiveSlackSource class."""
        self.client = client

    def history_pages(self, channel: str) -> AsyncIterator[tuple[dict, dict]]:
        """Yield (request params, response body) for each history page."""
        return _pages(self.client.conversations_history(channel=channel, limit=PAGE_SIZE, include_all_metadata=True))

    def reply_pages(self, channel: str, ts: str) -> AsyncIterator[tuple[dict, dict]]:
        """Yield (request params, response body) for each page of a thread."""
        return _pages(
            self.client.conversations_replies(channel=channel, ts=ts, limit=PAGE_SIZE, include_all_metadata=True)
        )

    async def history(self, channel: str) -> AsyncIterator[Message]:
        """Yield every top-level message."""
        async for _, body in self.history_pages(channel):
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

    async def history(self, channel: str) -> AsyncIterator[Message]:
        """Yield top-level messages and record each page."""
        directory = self.cache_dir / channel / "conversations.history"
        number = 0
        async for params, body in self.history_pages(channel):
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

    async def history(self, channel: str) -> AsyncIterator[Message]:
        """Yield recorded top-level messages, newest first like the API."""
        pages = (self.cache_dir / channel / "conversations.history").glob("page-*.json")
        messages = {
            message["ts"]: message for record in self._records(pages) for message in record["response"]["messages"]
        }
        for ts in sorted(messages, key=float, reverse=True):
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
    from_bot = message.get("bot_id") == get_settings().bot_id
    if from_bot and metadata.get("event_type") == ARRIVAL_EVENT_TYPE:
        payload = metadata["event_payload"]
        return ParsedArrival(
            user_id=payload["user_id"],
            occurred_at=datetime.fromisoformat(payload["occurred_at"]),
            source="slack_v3",
            slack_ts=message["ts"],
        )
    text = message.get("text") or ""
    posted_at = datetime.fromtimestamp(float(message["ts"]), UTC)
    if from_bot and (match := CURRENT_ARRIVAL.search(text)):
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


async def sync_channel(session: Session, source: SlackSource, channel: str) -> SyncResult:
    """Read the whole channel and store the arrival events that are not stored yet."""
    if not (bot_id := get_settings().bot_id):
        # Without it no current arrival is recognized and the sync would silently store almost nothing.
        msg = "BOT_ID must be set to sync"
        raise ValueError(msg)
    logger.info("Syncing {}", channel)

    result = SyncResult()
    arrivals: list[ParsedArrival] = []
    async for message in source.history(channel):
        result.messages += 1
        if arrival := parse_arrival(message):
            arrivals.append(arrival)
        if message.get("bot_id") == bot_id and message.get("reply_count"):
            result.threads += 1
            replies = (await source.replies(channel, message["ts"]))[1:]
            if len(replies) < message["reply_count"]:
                logger.warning(
                    "Thread {} returned {}/{} replies; run the sync again to read the rest",
                    message["ts"],
                    len(replies),
                    message["reply_count"],
                )
            arrivals += [arrival for reply in replies if (arrival := parse_arrival(reply))]

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
    session.commit()
    logger.info("Synced {}: {}", channel, result)
    return result
