from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from hikarie_bot import __main__ as bot
from hikarie_bot.constants import JST
from hikarie_bot.models import ArrivalEvent
from hikarie_bot.settings import Settings


@pytest.mark.asyncio
async def test_an_old_status_button_points_to_my_page(app_database: Engine, settings: Settings) -> None:
    """The status button of an older daily post says the status moved, links the Home and shows my page there."""
    settings.slack_workspace_id, settings.slack_app_id = "T0", "A0"
    with Session(app_database) as session:
        session.add(ArrivalEvent(user_id="U1", occurred_at=datetime(2024, 1, 1, 7, 0, tzinfo=JST), source="button"))
        session.commit()
    client = AsyncMock()

    await bot.handle_status_moved(AsyncMock(), {"user": {"id": "U1"}, "channel": {"id": "C0OUT"}}, client)

    ephemeral = client.chat_postEphemeral.await_args.kwargs
    assert (ephemeral["channel"], ephemeral["user"]) == ("C0OUT", "U1")
    assert ephemeral["text"] == bot.STATUS_MOVED + "（<slack://app?team=T0&id=A0&tab=home|マイページを開く>）"
    published = client.views_publish.await_args.kwargs
    assert (published["user_id"], published["view"]["type"]) == ("U1", "home")
