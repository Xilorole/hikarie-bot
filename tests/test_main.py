from datetime import datetime
from unittest.mock import AsyncMock

import pytest
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
    assert "• *総出社回数*: 1回" in kwargs["view"].blocks[1].text.text
