import os
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from hikarie_bot.exceptions import EnvironmentVariableNotFoundError

REQUIRED = [
    "output_channel",
    "log_channel",
    "bot_id",
    "v1_bot_id",
    "v2_bot_id",
    "admin",
    "slack_bot_token",
    "slack_app_token",
    "database_url",
]


class Settings(BaseSettings):
    """Application settings from environment variables, then an env file.

    The env file is DOTENV_PATH (e.g. .env.dev for `slack run`) or the working directory's
    .env; a parent directory's file is never read, and tests (ENV=test) read none.
    Environment variables win over the file. Outside dev/test every REQUIRED value must be set.
    """

    model_config = SettingsConfigDict(
        env_file=None if os.environ.get("ENV") == "test" else os.environ.get("DOTENV_PATH", ".env"),
        extra="ignore",
    )

    env: str = ""

    # slack.channel
    output_channel: str = ""
    log_channel: str = ""

    # slack.user
    bot_id: str = ""
    v1_bot_id: str = ""
    v2_bot_id: str = ""
    admin: str = ""

    # slack.workspace
    slack_workspace_id: str = ""

    # auth
    slack_bot_token: str = ""
    slack_app_token: str = ""

    # database (dev/test fall back to an in-memory database)
    database_url: str = ""

    # log
    loguru_level: str = "DEBUG"

    @model_validator(mode="after")
    def _require_production_values(self) -> Self:
        if self.env in {"dev", "test"}:
            self.database_url = self.database_url or "sqlite:///:memory:"
        elif missing := [name for name in REQUIRED if not getattr(self, name)]:
            raise EnvironmentVariableNotFoundError(missing[0].upper())
        return self


settings = Settings()

OUTPUT_CHANNEL = settings.output_channel
LOG_CHANNEL = settings.log_channel
BOT_ID = settings.bot_id
V1_BOT_ID = settings.v1_bot_id
V2_BOT_ID = settings.v2_bot_id
ADMIN = settings.admin
SLACK_WORKSPACE_ID = settings.slack_workspace_id
SLACK_BOT_TOKEN = settings.slack_bot_token
SLACK_APP_TOKEN = settings.slack_app_token
DATABASE_URL = settings.database_url
LOGURU_LEVEL = settings.loguru_level
