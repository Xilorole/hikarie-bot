import os
from functools import cache
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from hikarie_bot.exceptions import EnvironmentVariableNotFoundError

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
    # the app's ID (Basic Information in the app settings): with the workspace ID, the daily post links to the Home
    slack_app_id: str = ""

    # auth
    slack_bot_token: str = ""
    slack_app_token: str = ""

    # database (dev/test fall back to an in-memory database)
    database_url: str = ""

    # the commit the running image was built from (set by the Docker build)
    app_revision: str = ""

    @property
    def local(self) -> bool:
        """Tell whether this is a dev or test run, where nothing is required."""
        return self.env in {"dev", "test"}

    @model_validator(mode="after")
    def _in_memory_database_for_dev_and_test(self) -> Self:
        if self.local:
            self.database_url = self.database_url or "sqlite:///:memory:"
        return self

    def require(self, *names: str) -> None:
        """Raise for the first named value that is unset, unless this is a dev or test run."""
        if not self.local and (missing := [name for name in names if not getattr(self, name)]):
            raise EnvironmentVariableNotFoundError(missing[0].upper())


def env_file() -> str | None:
    """Return the env file: DOTENV_PATH (e.g. .env.dev for `slack run`), else ./.env; none in tests.

    A parent directory's file is never read, and environment variables win over the file.
    """
    return None if os.environ.get("ENV") == "test" else os.environ.get("DOTENV_PATH", ".env")


@cache
def get_settings() -> Settings:
    """Read the settings on first use, so importing the package needs no configuration."""
    return Settings(_env_file=env_file())
