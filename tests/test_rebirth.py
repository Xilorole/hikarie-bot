"""Rebirth: when it is allowed, what it resets, the multiplier and the marks (docs/design/rebirth.md)."""

from collections.abc import AsyncIterator
from datetime import date, datetime, time, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from hikarie_bot import __main__ as bot
from hikarie_bot.constants import JST
from hikarie_bot.engine import MAX_POINTS, BadgeEngine, compute, format_multiplier, multiplied
from hikarie_bot.home import HomeActionID, HomeTab, home_view
from hikarie_bot.modals import mark_text, registry_message, render
from hikarie_bot.models import ArrivalEvent, RebirthEvent
from hikarie_bot.rebirths import REBORN_TODAY, record_rebirth
from hikarie_bot.settings import Settings
from hikarie_bot.sync import parse_rebirth, rebirth_metadata, sync_channel
from hikarie_bot.utils import is_jp_bizday

MONDAY, TUESDAY, WEDNESDAY = date(2026, 11, 9), date(2026, 11, 10), date(2026, 11, 11)


def at(day: date, hour: int, minute: int = 0) -> datetime:
    """Return a JST time on a day."""
    return datetime.combine(day, time(hour, minute), tzinfo=JST)


def with_points(points: int, user_id: str = "U1") -> BadgeEngine:
    """Return an engine where the user has arrived once and holds `points` in the current lap."""
    engine = compute([(user_id, at(MONDAY, 9))])
    engine.users[user_id].score = points
    return engine


def test_multiplied_rounds_up_and_formats() -> None:
    """Points times tenths are rounded up: 2 x 1.5 = 3, 3 x 1.5 = 5."""
    assert [multiplied(points, 15) for points in (1, 2, 3, 4)] == [2, 3, 5, 6]
    assert multiplied(3, 10) == 3
    assert (format_multiplier(10), format_multiplier(15), format_multiplier(22)) == ("1.0倍", "1.5倍", "2.2倍")


def test_the_first_rebirth_needs_level_5_and_starts_the_points_over() -> None:
    """Below Lv5 (111pt) nothing happens; at Lv5 the points go to 0 and the multiplier will be 1.5."""
    engine = with_points(110)
    assert engine.rebirth("U1", at(MONDAY, 12)) is None
    assert engine.rebirth_status("U1", at(MONDAY, 12)).points_to_go == 1

    engine = with_points(111)
    rebirth = engine.rebirth("U1", at(MONDAY, 12))
    assert (rebirth.number, rebirth.level, rebirth.multiplier) == (1, 5, 15)
    status = engine.rebirth_status("U1", at(MONDAY, 13))
    assert (status.points, status.level, status.multiplier, status.reborn_today, status.can) == (0, 1, 15, True, False)


def test_a_later_rebirth_needs_a_higher_level_than_the_previous_one() -> None:
    """After a rebirth at Lv5, Lv5 again is not enough; Lv6 is, and adds 0.6."""
    engine = with_points(111)
    engine.rebirth("U1", at(MONDAY, 12))
    engine.users["U1"].score = 166  # Lv5
    assert engine.rebirth("U1", at(TUESDAY, 12)) is None
    assert engine.rebirth_status("U1", at(TUESDAY, 12)).required_level == 6
    engine.users["U1"].score = 167  # Lv6
    assert engine.rebirth("U1", at(TUESDAY, 12)).multiplier == 21


def test_the_top_level_allows_a_rebirth_every_time() -> None:
    """At Lv12 the user may be reborn again and again (one a day), each adding 1.2."""
    engine = with_points(MAX_POINTS)
    engine.rebirth("U1", at(MONDAY, 12))
    engine.users["U1"].score = 1098  # Lv12 again
    assert engine.rebirth_status("U1", at(TUESDAY, 12)).required_level == 12
    assert engine.rebirth("U1", at(TUESDAY, 12)).multiplier == 10 + 12 + 12


def test_one_rebirth_a_day() -> None:
    """A second rebirth the same day is refused even with the level for it."""
    engine = with_points(MAX_POINTS)
    engine.rebirth("U1", at(MONDAY, 12))
    engine.users["U1"].score = MAX_POINTS
    assert engine.rebirth("U1", at(MONDAY, 13)) is None


def test_the_multiplier_acts_from_the_day_after_the_rebirth() -> None:
    """An arrival on the rebirth's day keeps the old multiplier; the next day's is multiplied and rounded up."""
    arrivals = [("U1", at(MONDAY, 9)), ("U1", at(TUESDAY, 9)), ("U1", at(WEDNESDAY, 9))]
    plain = compute(arrivals)
    engine = compute(arrivals[:1])
    engine.users["U1"].score = 111
    engine.rebirth("U1", at(TUESDAY, 8))
    tuesday, wednesday = (engine.add(user_id, time) for user_id, time in arrivals[1:])

    assert (tuesday.multiplier, tuesday.score_sum) == (10, plain.results[1].score_sum)
    assert tuesday.previous_score == 0
    assert (wednesday.multiplier, wednesday.score_sum) == (15, multiplied(plain.results[2].score_sum, 15))


def test_reaching_the_upper_limit_earns_a_mark_kept_through_rebirths() -> None:
    """Each lap that reaches MAX_POINTS earns a mark; the arrival that reaches it says so."""
    engine = compute([("U1", at(MONDAY, 9))])
    engine.users["U1"].score = MAX_POINTS - 1
    result = engine.add("U1", at(TUESDAY, 9))
    assert (result.earned_mark, result.marks) == (True, 1)
    engine.rebirth("U1", at(TUESDAY, 12))
    assert engine.rebirth_status("U1", at(TUESDAY, 13)).marks == 1
    assert engine.add("U1", at(WEDNESDAY, 9)).marks == 1


def test_compute_ignores_a_rebirth_the_rules_do_not_allow() -> None:
    """A stored rebirth without the level for it (after a rule change) does nothing."""
    engine = compute([("U1", at(MONDAY, 9)), ("U1", at(TUESDAY, 9))], rebirths=[("U1", at(MONDAY, 12))])
    assert engine.users["U1"].rebirths == []
    assert engine.results[1].previous_score == engine.results[0].current_score


# --- stored rebirths, the button and the views ---


@pytest.fixture
def database(app_database: Engine, settings: Settings) -> Engine:
    """Give the handlers a fresh database and the output channel."""
    settings.bot_id = "B0BOT"
    settings.output_channel = "C0OUT"
    return app_database


def level_5_arrivals() -> list[datetime]:
    """Return arrivals of U1 on the business days before MONDAY, just enough to reach Lv5 (111pt)."""
    times: list[datetime] = []
    day = MONDAY - timedelta(days=120)
    while not times or compute([("U1", time) for time in times]).users["U1"].score < 111:
        if is_jp_bizday(day):
            times.append(at(day, 6, 30))
        day += timedelta(days=1)
    return times


def store_arrivals(database: Engine, times: list[datetime]) -> None:
    """Store U1's arrivals."""
    with Session(database) as session:
        session.add_all(ArrivalEvent(user_id="U1", occurred_at=time, source="button") for time in times)
        session.commit()


def test_record_rebirth_stores_once_a_day(database: Engine) -> None:
    """A rebirth at Lv5 is stored; a second press that day is refused; below the level it says what is needed."""
    with Session(database) as session:
        assert record_rebirth(session, "U1", at(MONDAY, 12)).refusal == "転生は Lv5 からできます（あと 111pt）"
    store_arrivals(database, level_5_arrivals())
    with Session(database) as session:
        gate = record_rebirth(session, "U1", at(MONDAY, 12))
        assert gate.unannounced is not None
        assert record_rebirth(session, "U1", at(MONDAY, 12)).unannounced == gate.unannounced  # not announced yet
        session.get(RebirthEvent, gate.unannounced.id).slack_ts = "1.000001"
        session.commit()
        assert record_rebirth(session, "U1", at(MONDAY, 13)).refusal == REBORN_TODAY


def daily_post_client() -> AsyncMock:
    """Return a client whose history holds MONDAY's daily post."""
    client = AsyncMock()
    post = {
        "ts": f"{at(MONDAY, 6).timestamp():.6f}",
        "bot_id": "B0BOT",
        "blocks": [{"type": "actions", "block_id": "FASTEST_ARRIVAL"}],
    }
    client.conversations_history.return_value = {"ok": True, "messages": [post]}
    client.chat_postMessage.return_value = {"ok": True, "ts": "1762729200.000100"}
    return client


@pytest.mark.asyncio
async def test_the_rebirth_button_announces_it_under_the_daily_post(database: Engine) -> None:
    """The button stores the rebirth, posts it with metadata in the thread, and my page shows the new lap."""
    store_arrivals(database, level_5_arrivals())
    client = daily_post_client()
    body = {"user": {"id": "U1"}, "trigger_id": "T1", "actions": [{"action_id": HomeActionID.REBIRTH}]}

    with freeze_time(at(MONDAY, 12)):
        await bot.handle_home_rebirth(AsyncMock(), body, client)

    post = client.chat_postMessage.await_args.kwargs
    assert post["text"] == "<@U1>さんが Lv5 で転生しました！ 2しゅうめ・倍率 1.5倍（次の営業日の出社から）"
    assert post["metadata"]["event_type"] == "hikarie_rebirth"
    with Session(database) as session:
        assert session.query(RebirthEvent).one().slack_ts == "1762729200.000100"
    assert "今日転生しました" in str(client.views_publish.await_args.kwargs["view"])


class ThreadSource:
    """A channel with MONDAY's daily post, whose thread holds the given replies."""

    def __init__(self, replies: list[dict[str, Any]]) -> None:
        """Keep the replies."""
        self.replies_ = replies

    async def history(self, _channel: str) -> AsyncIterator[dict[str, Any]]:
        """Yield the daily post."""
        yield {"ts": f"{at(MONDAY, 6).timestamp():.6f}", "bot_id": "B0BOT", "reply_count": len(self.replies_)}

    async def replies(self, _channel: str, _ts: str) -> list[dict[str, Any]]:
        """Return the parent and the replies."""
        return [{"ts": f"{at(MONDAY, 6).timestamp():.6f}"}, *self.replies_]


@pytest.mark.asyncio
async def test_a_rebirth_is_rebuilt_from_its_post_in_the_thread(database: Engine) -> None:
    """After the database loses the rebirth, a sync of the thread brings it back with the same lap and multiplier."""
    store_arrivals(database, level_5_arrivals())
    client = daily_post_client()
    body = {"user": {"id": "U1"}, "trigger_id": "T1", "actions": [{"action_id": HomeActionID.REBIRTH}]}
    with freeze_time(at(MONDAY, 12)):
        await bot.handle_home_rebirth(AsyncMock(), body, client)
    post = client.chat_postMessage.await_args.kwargs
    reply = {"ts": "1762729200.000100", "bot_id": "B0BOT", "metadata": post["metadata"], "text": post["text"]}
    with Session(database) as session:
        session.query(RebirthEvent).delete()
        session.commit()

        first = await sync_channel(session, ThreadSource([reply]), "C0OUT")
        second = await sync_channel(session, ThreadSource([reply]), "C0OUT")

        assert (first.rebirths_inserted, second.rebirths_inserted) == (1, 0)
        rebirth = session.query(RebirthEvent).one()
        assert (rebirth.user_id, rebirth.day, rebirth.slack_ts) == ("U1", MONDAY, "1762729200.000100")
        events = [(event.user_id, event.occurred_at) for event in session.query(ArrivalEvent)]
    engine = compute(events, rebirths=[(rebirth.user_id, rebirth.occurred_at)])
    status = engine.rebirth_status("U1", at(MONDAY, 13))
    assert (status.points, len(status.rebirths), status.multiplier) == (0, 1, 15)


@pytest.mark.asyncio
async def test_a_refused_rebirth_opens_a_notice(database: Engine) -> None:
    """Below the level nothing is stored and a modal says why."""
    client = daily_post_client()
    body = {"user": {"id": "U1"}, "trigger_id": "T1", "actions": [{"action_id": HomeActionID.REBIRTH}]}

    with freeze_time(at(MONDAY, 12)):
        await bot.handle_home_rebirth(AsyncMock(), body, client)

    client.chat_postMessage.assert_not_awaited()
    assert "Lv5 からできます" in str(client.views_open.await_args.kwargs["view"])


def test_my_page_offers_the_rebirth_with_a_confirmation_once_allowed() -> None:
    """Below the level my page says what it needs; at Lv5 it shows the button with a confirmation dialog."""
    view = home_view(with_points(100), "U1", at(MONDAY, 12))
    assert "*Lv5* になると転生できます（あと 11pt）" in str(view)
    assert "転生できる Lv5 まで あと11pt" in str(view)

    view = home_view(with_points(111), "U1", at(MONDAY, 12))
    button = next(
        block["accessory"]
        for block in view["blocks"]
        if block.get("accessory", {}).get("action_id") == HomeActionID.REBIRTH
    )
    assert button["confirm"]["confirm"]["text"] == "転生する"
    assert "倍率が *1.0倍 → 1.5倍* になります" in str(view)


def test_the_collection_lists_the_rebirths() -> None:
    """The collection tabulates each rebirth: which one, the day, the level and the multiplier."""
    engine = with_points(111)
    engine.rebirth("U1", at(MONDAY, 12))
    view = home_view(engine, "U1", at(MONDAY, 13), HomeTab.COLLECTION)
    table = next(block for block in view["blocks"] if block["type"] == "table" and "1回目" in str(block))
    assert [cell["elements"][0]["elements"][0]["text"] for cell in table["rows"][1]] == [
        "1回目",
        "26/11/09",
        "Lv5 いちにんまえのかいしゃいん",
        "1.5倍",
    ]


def test_a_rebirth_post_is_read_back_from_its_metadata(settings: Settings) -> None:
    """A sync restores a rebirth from the bot's thread post; other bots' posts are ignored."""
    settings.bot_id = "B0BOT"
    message = {"ts": "1.000001", "bot_id": "B0BOT", "metadata": rebirth_metadata("U1", MONDAY, at(MONDAY, 12))}

    rebirth = parse_rebirth(message)

    assert (rebirth.user_id, rebirth.day, rebirth.occurred_at, rebirth.slack_ts) == (
        "U1",
        MONDAY,
        at(MONDAY, 12),
        "1.000001",
    )
    assert parse_rebirth({**message, "bot_id": "B0OTHER"}) is None


def test_marks_follow_the_name_in_the_daily_post() -> None:
    """The day's arrivals list shows each user's marks after their name."""
    engine = compute([("U1", at(MONDAY, 9))])
    engine.users["U1"].score = MAX_POINTS - 1
    result = engine.add("U1", at(TUESDAY, 9))

    text = render(registry_message([result]))[3]["text"]["text"]

    assert text.endswith("<@U1> 🌟")
    assert [mark_text(n) for n in (0, 3, 4, 12)] == ["", "🌟🌟🌟", "🌟4", "🌟12"]
