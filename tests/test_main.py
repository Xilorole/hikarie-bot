from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from slack_sdk.errors import SlackApiError
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from hikarie_bot import __main__ as bot
from hikarie_bot.constants import JST
from hikarie_bot.models import ArrivalEvent


@pytest.mark.asyncio
async def test_check_achievement_opens_the_users_view(app_database: Engine) -> None:
    """The achievement button opens a modal computed from the stored arrivals."""
    with Session(app_database) as session:
        session.add(ArrivalEvent(user_id="U1", occurred_at=datetime(2024, 1, 1, 7, 0, tzinfo=JST), source="button"))
        session.commit()
    client = AsyncMock()

    await bot.handle_check_achievement(AsyncMock(), {"user": {"id": "U1"}, "trigger_id": "T1"}, client)

    kwargs = client.views_open.await_args.kwargs
    assert kwargs["trigger_id"] == "T1"
    view = kwargs["view"]
    lists = [block for block in view["blocks"] if block["type"] == "rich_text"]
    lines = ["".join(part["text"] for part in item["elements"][0]["elements"]) for item in lists[0]["elements"]]
    assert view["title"]["text"] == "ステータス"
    assert lines[:2] == ["かたがき かけだしのかいしゃいん（Lv1）", "ポイント 7pt（Lv2まで あと13pt）"]
    assert any(
        "総出社回数: 1回" in "".join(p["text"] for p in i["elements"][0]["elements"]) for i in lists[1]["elements"]
    )


@pytest.mark.asyncio
async def test_status_failure_is_told_to_the_user(app_database: Engine) -> None:
    """When Slack refuses the modal, the user gets Slack's reason instead of no response."""
    client = AsyncMock()
    response = {"ok": False, "error": "invalid_arguments", "response_metadata": {"messages": ["[ERROR] bad block"]}}
    client.views_open.side_effect = SlackApiError("refused", response)

    body = {"user": {"id": "U1"}, "trigger_id": "T1", "channel": {"id": "C0OUT"}}
    await bot.handle_check_achievement(AsyncMock(), body, client)

    ephemeral = client.chat_postEphemeral.await_args.kwargs
    assert (ephemeral["channel"], ephemeral["user"]) == ("C0OUT", "U1")
    assert ephemeral["text"] == "ステータスを開けませんでした（invalid_arguments; [ERROR] bad block）"
