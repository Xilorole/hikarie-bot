"""Apply Alembic migrations and prepare the database on startup.

Revision 0000 is the baseline. Databases from before Alembic are not upgraded: the data
is rebuilt from Slack, so such a database should be removed instead.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from hikarie_bot.curd import sync_badge_master_data

SCRIPT_LOCATION = Path(__file__).parent / "alembic"


class UnversionedDatabaseError(RuntimeError):
    """Raised for a database that has tables but no Alembic version."""

    def __init__(self, url: str) -> None:
        """Initialize the UnversionedDatabaseError class."""
        super().__init__(f"{url} predates schema versioning; delete it and rebuild the data from Slack")


def upgrade_database(engine: Engine) -> None:
    """Upgrade the schema to the latest Alembic revision."""
    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        if tables and "alembic_version" not in tables:
            raise UnversionedDatabaseError(engine.url.render_as_string(hide_password=True))
        config = Config()
        config.set_main_option("script_location", str(SCRIPT_LOCATION))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def init_database(engine: Engine) -> None:
    """Bring the schema up to date and synchronize master data from code."""
    upgrade_database(engine)
    with Session(engine) as session:
        sync_badge_master_data(session)
