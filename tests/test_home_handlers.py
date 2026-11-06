"""The App Home on Slack: publishing it, switching its tabs and its buttons."""

from collections.abc import Iterator
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from hikarie_bot import __main__ as bot
from hikarie_bot.constants import JST
from hikarie_bot.home import HomeActionID, HomeTab
from hikarie_bot.modals import ActionID, CallbackID
from hikarie_bot.models import ArrivalEvent
from hikarie_bot.picks import NOT_ARRIVED_NOTICE
from hikarie_bot.settings import Settings

DAILY_POST = datetime(2025, 6, 2, 6, 0, tzinfo=JST)
NOW = datetime(2025, 6, 2, 9, 10, tzinfo=JST)
POST_TS = f"{DAILY_POST.timestamp():.6f}"


@pytest.fixture
def database(app_database: Engine, settings: Settings) -> Iterator[Engine]:
    """Give the handlers a fresh database, the output channel and a frozen clock."""
    settings.bot_id = "B0BOT"
    settings.output_channel = "C0OUT"
    with freeze_time(NOW):
        yield app_database


def slack(*, daily_post: bool = True) -> AsyncMock:
    """Return a client whose channel history holds today's daily post (or nothing)."""
    client = AsyncMock()
    client.views_open.return_value = {"ok": True, "view": {"id": "V1"}}
    post = {"ts": POST_TS, "bot_id": "B0BOT", "blocks": [{"type": "actions", "block_id": "FASTEST_ARRIVAL"}]}
    client.conversations_history.return_value = {"ok": True, "messages": [post] if daily_post else []}
    client.chat_postMessage.return_value = {"ok": True, "ts": "1748822999.000100"}
    return client


def home_action(action_id: str, user_id: str = "U1") -> dict:
    """Return a block action payload for a button on the Home."""
    return {"user": {"id": user_id}, "trigger_id": "T1", "actions": [{"action_id": action_id}], "view": {}}


def arrival_click(user_id: str = "U1") -> dict:
    """Return a press of the arrival button on today's daily post."""
    return {
        "user": {"id": user_id},
        "channel": {"id": "C0OUT"},
        "trigger_id": "T1",
        "actions": [{"action_id": ActionID.ARRIVED_OFFICE}],
        "message": {"ts": POST_TS},
    }


def published(client: AsyncMock) -> tuple[str, dict]:
    """Return the user and the view of the last Home publish."""
    kwargs = client.views_publish.await_args.kwargs
    return kwargs["user_id"], kwargs["view"]


def selected_tab(view: dict) -> str:
    """Return the tab highlighted in the tab bar."""
    return next(button["action_id"] for button in view["blocks"][0]["elements"] if button.get("style") == "primary")


@pytest.mark.asyncio
async def test_opening_the_home_publishes_my_page(database: Engine) -> None:
    """The first open shows my page; the messages tab publishes nothing."""
    client = slack()

    await bot.handle_app_home_opened({"user": "U1", "tab": "messages"}, client)
    client.views_publish.assert_not_awaited()

    await bot.handle_app_home_opened({"user": "U1", "tab": "home"}, client)
    user_id, view = published(client)
    assert (user_id, view["type"], selected_tab(view)) == ("U1", "home", HomeTab.MY_PAGE)


@pytest.mark.asyncio
async def test_reopening_the_home_keeps_the_tab_it_was_left_on(database: Engine) -> None:
    """The published view remembers its tab, so reopening renders it fresh on the same tab."""
    client = slack()

    event = {"user": "U1", "tab": "home", "view": {"private_metadata": HomeTab.RANKING}}
    await bot.handle_app_home_opened(event, client)

    assert selected_tab(published(client)[1]) == HomeTab.RANKING


@pytest.mark.asyncio
@pytest.mark.parametrize("tab", list(HomeTab.LABELS))
async def test_tab_buttons_switch_the_page(database: Engine, tab: str) -> None:
    """Each tab button publishes the Home on that tab."""
    client = slack()

    await bot.handle_home_tab(AsyncMock(), home_action(tab), client)

    assert selected_tab(published(client)[1]) == tab


@pytest.mark.asyncio
async def test_home_arrival_is_announced_on_the_daily_post_and_refreshes_the_home(database: Engine) -> None:
    """The Home's button records the arrival like the shortcut, then shows it on my page."""
    client = slack()

    await bot.handle_arrive_shortcut(AsyncMock(), home_action(HomeActionID.ARRIVE), client)

    assert client.chat_postMessage.await_args.kwargs["thread_ts"] == POST_TS
    assert client.views_update.await_args.kwargs["view"]["blocks"][0]["text"]["text"].startswith(
        "*09:10* に出社登録しました"
    )
    with Session(database) as session:
        assert session.query(ArrivalEvent).one().user_id == "U1"
    user_id, view = published(client)
    assert user_id == "U1"
    assert "出社登録済み" in str(view)


@pytest.mark.asyncio
async def test_a_refused_arrival_does_not_refresh_the_home(database: Engine) -> None:
    """Without a daily post nothing is recorded, so the Home stays as it is."""
    client = slack(daily_post=False)

    await bot.handle_arrive_shortcut(AsyncMock(), home_action(HomeActionID.ARRIVE), client)

    assert client.views_update.await_args.kwargs["view"]["blocks"][0]["text"]["text"] == bot.NO_DAILY_POST
    client.views_publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_home_item_button_shows_the_offers_before_arriving(database: Engine) -> None:
    """Before arriving the Home's item button opens the offers to look at."""
    client = slack()

    await bot.handle_home_pick_item(AsyncMock(), home_action(HomeActionID.PICK_ITEM), client)

    view = client.views_open.await_args.kwargs["view"]
    assert view["callback_id"] == CallbackID.ITEM_REVIEW
    assert NOT_ARRIVED_NOTICE in str(view)


@pytest.mark.asyncio
async def test_home_item_button_offers_a_pick_under_the_daily_post_after_arriving(database: Engine) -> None:
    """After arriving the pick modal opens with today's daily post to announce the pick under."""
    client = slack()
    await bot.handle_button_click(AsyncMock(), arrival_click(), client)

    await bot.handle_home_pick_item(AsyncMock(), home_action(HomeActionID.PICK_ITEM), client)

    view = client.views_open.await_args.kwargs["view"]
    assert view["callback_id"] == CallbackID.ITEM_PICK
    assert '"thread_ts": "' + POST_TS + '"' in view["private_metadata"]


@pytest.mark.asyncio
async def test_a_failed_home_refresh_does_not_fail_the_arrival(database: Engine) -> None:
    """The arrival is announced before the Home is refreshed, so a failed publish only logs."""
    client = slack()
    client.views_publish.side_effect = RuntimeError("publish failed")

    await bot.handle_button_click(AsyncMock(), arrival_click(), client)

    client.chat_postMessage.assert_awaited_once()
    client.views_publish.assert_awaited_once()
