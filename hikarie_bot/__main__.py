# アプリを起動します
import os
from collections.abc import Generator

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from sqlalchemy.orm import Session

from hikarie_bot.database import BaseSchema, SessionLocal, engine


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


if __name__ == "__main__":
    # ボットトークンとソケットモードハンドラーを使ってアプリを初期化します
    app = App(token=os.environ.get("SLACK_BOT_TOKEN"))
    session = get_db()

    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
