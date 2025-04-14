from loguru import logger
from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy.orm import Session

from hikarie_bot.modals import AchievementView


async def open_achievement_view(client: AsyncWebClient, session: Session, trigger_id: str, user_id: str) -> None:
    """Open the achievement view modal."""
    achievement_view = AchievementView(session=session, user_id=user_id)
    logger.info(f"Opening achievement view for user {user_id}")
    await client.views_open(
        trigger_id=trigger_id,
        view=achievement_view,
    )
