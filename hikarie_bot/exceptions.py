from typing import Self


class EnvironmentVariableNotFoundError(Exception):
    """Raised when the environment variable is not found."""

    def __init__(self: Self, env_var: str) -> None:
        """Initialize the EnvironmentVariableNotFoundError class."""
        super().__init__(f"Environment variable not found: {env_var}")


class DatabaseLocationError(Exception):
    """Raised when the SQLite file cannot be created or written where DATABASE_URL points.

    The message describes only paths and permissions, so it may be shown in Slack.
    """


class InMemoryDatabaseError(Exception):
    """Raised when production is configured with an in-memory database."""

    def __init__(self: Self, url: str) -> None:
        """Initialize the InMemoryDatabaseError class."""
        super().__init__(
            f"DATABASE_URL={url} keeps no data across restarts (each start re-reads the whole channel); "
            "use a file on a persistent volume, e.g. sqlite:////opt/.db/data.db"
        )
