# アプリを起動します
import os
from collections.abc import Generator

from dotenv import load_dotenv
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.app.async_app import AsyncApp
from sqlalchemy.orm import Session

from hikarie_bot.database import BaseSchema, SessionLocal, engine
from hikarie_bot.slack_helper import send_daily_message

load_dotenv()
app = AsyncApp(token=os.environ.get("SLACK_BOT_TOKEN"))


# Dependency
def get_db() -> Generator[Session, None, None]:
    """Get the database session."""
    # create tables
    BaseSchema.metadata.create_all(engine)
    try:
        db = SessionLocal()  # sessionを生成
        yield db
    finally:
        db.close()


async def main() -> None:
    """Run the app."""
    background_task = set()

    f = send_daily_message(app=app)
    a = asyncio.ensure_future(f)

    # makes a strong reference not to GC
    background_task.add(a)

    handler = AsyncSocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    await handler.start_async()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
