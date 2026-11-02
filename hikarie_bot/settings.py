import os
from functools import cache
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from hikarie_bot.exceptions import EnvironmentVariableNotFoundError, InMemoryDatabaseError

REQUIRED = [
    "output_channel",
    "log_channel",
    "bot_id",
    "admin",
    "slack_bot_token",
    "slack_app_token",
    "database_url",
]


class Settings(BaseSettings):
    """Application settings from environment variables, then an env file (see get_settings).

    Nothing is required to construct them; a command checks what it needs with require().
    dev/test fall back to an in-memory database.
    """

    model_config = SettingsConfigDict(extra="ignore")

    env: str = ""

    # slack.channel
    output_channel: str = ""
    log_channel: str = ""

    # slack.user
    bot_id: str = ""
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

    # the commit the running image was built from (set by the Docker build)
    app_revision: str = ""

    @model_validator(mode="after")
    def _in_memory_database_for_dev_and_test(self) -> Self:
        if self.env in {"dev", "test"}:
            self.database_url = self.database_url or "sqlite:///:memory:"
        return self

    def require(self, *names: str) -> None:
        """Raise for the first named value that is unset, outside dev/test.

        A required database must also be a file: an in-memory one loses everything on restart.
        """
        if self.env in {"dev", "test"}:
            return
        if missing := [name for name in names if not getattr(self, name)]:
            raise EnvironmentVariableNotFoundError(missing[0].upper())
        if "database_url" in names and make_url(self.database_url).database in {None, "", ":memory:"}:
            raise InMemoryDatabaseError(self.database_url)


def env_file() -> str | None:
    """Return the env file: DOTENV_PATH (e.g. .env.dev for `slack run`), else ./.env; none in tests.

    A parent directory's file is never read, and environment variables win over the file.
    """
    return None if os.environ.get("ENV") == "test" else os.environ.get("DOTENV_PATH", ".env")


@cache
def get_settings() -> Settings:
    """Read the settings on first use, so importing the package needs no configuration."""
    return Settings(_env_file=env_file())
