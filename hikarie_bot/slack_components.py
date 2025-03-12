from loguru import logger
from slack_sdk.web.async_client import AsyncWebClient

from hikarie_bot.database import SessionLocal
from hikarie_bot.modals import AchievementView


async def open_achievement_view(
    client: AsyncWebClient, trigger_id: str, user_id: str
) -> None:
    """Open the achievement view modal."""
    db = SessionLocal()
    achievement_view = AchievementView(session=db, user_id=user_id)
    logger.info(f"Opening achievement view for user {user_id}")
    await client.views_open(
        trigger_id=trigger_id,
        view=achievement_view,
    )
