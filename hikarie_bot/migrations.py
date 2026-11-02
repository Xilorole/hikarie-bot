"""Apply Alembic migrations and prepare the database on startup.

Revision 0000 is the baseline. Databases from before Alembic are not upgraded: the data
is rebuilt from Slack, so such a database should be removed instead.
"""

from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

SCRIPT_LOCATION = Path(__file__).parent / "alembic"


class UnversionedDatabaseError(RuntimeError):
    """Raised for a database that has tables but no Alembic version."""

    def __init__(self, url: str) -> None:
        """Initialize the UnversionedDatabaseError class."""
        super().__init__(f"{url} predates schema versioning; delete it and rebuild the data from Slack")


@dataclass
class InitResult:
    """The schema revision before and after startup."""

    revision_before: str | None
    revision: str


def init_database(engine: Engine) -> InitResult:
    """Upgrade the schema to the latest Alembic revision; return the revisions before and after."""
    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        if tables and "alembic_version" not in tables:
            raise UnversionedDatabaseError(engine.url.render_as_string(hide_password=True))
        config = Config()
        config.set_main_option("script_location", str(SCRIPT_LOCATION))
        config.attributes["connection"] = connection
        before = MigrationContext.configure(connection).get_current_revision()
        command.upgrade(config, "head")
        return InitResult(before, ScriptDirectory.from_config(config).get_current_head())
