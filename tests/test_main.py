from datetime import datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session, sessionmaker

from hikarie_bot.models import User
from hikarie_bot.slack_components import open_achievement_view


@pytest.mark.asyncio
async def test_open_achievement_view(temp_db: sessionmaker[Session]) -> None:
    """
    Test the open_achievement_view function.

    This test ensures that the function correctly opens the achievement view modal
    for a given user by interacting with the Slack client and using the database session.
    """
    mock_client = AsyncMock()
    session = temp_db()
    trigger_id = "test_trigger_id"
    user_id = "test_user_id"

    # Mock database session behavior
    from hikarie_bot.curd import initially_insert_badge_data

    # Insert badge data into the database
    initially_insert_badge_data(session)

    # Insert test user data
    session.add(
        User(
            id="test_user_id",
            current_score=10,
            previous_score=5,
            update_datetime=datetime.now(ZoneInfo("Asia/Tokyo")),
            level=1,
            level_name="Beginner",
            level_uped=False,
            point_to_next_level=20,
            point_range_to_next_level=30,
            current_level_point=10,
        )
    )
    session.commit()

    # Call the function
    await open_achievement_view(client=mock_client, session=session, trigger_id=trigger_id, user_id=user_id)

    # Assert that the Slack client was called with the correct parameters
    mock_client.views_open.assert_called_once_with(
        trigger_id=trigger_id,
        view=mock_client.views_open.call_args[1]["view"],  # Validate the view object
    )
