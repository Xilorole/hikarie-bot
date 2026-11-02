import os
from collections.abc import Generator
from contextlib import contextmanager
from functools import cache
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.pool import StaticPool

from hikarie_bot.exceptions import DatabaseLocationError, InMemoryDatabaseError
from hikarie_bot.migrations import InitResult, init_database
from hikarie_bot.settings import get_settings


def configure_sqlite(engine: Engine) -> None:
    """Use WAL and a busy timeout on a SQLite file."""

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


def check_sqlite_location(path: Path) -> None:
    """Explain why a SQLite file could not be opened, before SQLite says only "unable to open".

    Raises DatabaseLocationError naming the directory and the likely fix.
    """
    relative = (
        ""
        if path.is_absolute()
        else (
            f" DATABASE_URL has a relative path, resolved from {Path.cwd()}; an absolute path needs four slashes"
            f" (sqlite:////{path})."
        )
    )
    file = path if path.is_absolute() else Path.cwd() / path
    directory = file.parent
    if not directory.is_dir():
        msg = f"{directory} does not exist: mount the persistent volume there or fix DATABASE_URL.{relative}"
        raise DatabaseLocationError(msg)
    target = file if file.exists() else directory
    if not os.access(target, os.W_OK):
        msg = (
            f"{target} is not writable by uid {os.getuid()}: mount the persistent volume at {directory} "
            "(the image's filesystem is read-only in the pod) and set the pod's securityContext.fsGroup to 10001."
            f"{relative}"
        )
        raise DatabaseLocationError(msg)


@cache
def get_engine() -> Engine:
    """Create the application's SQLite engine from DATABASE_URL on first use.

    dev/test may use an in-memory database; elsewhere it must be a file, which loses nothing on restart.
    """
    settings = get_settings()
    settings.require("database_url")
    url = make_url(settings.database_url)
    if url.database in {None, "", ":memory:"}:
        if not settings.local:
            raise InMemoryDatabaseError(settings.database_url)
        # an in-memory database lives in one connection, which worker threads must share
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    check_sqlite_location(Path(url.database))
    engine = create_engine(url, connect_args={"check_same_thread": False})
    configure_sqlite(engine)
    return engine


class BaseSchema(DeclarativeBase):
    """Base class for defining the schema of the database."""


@cache
def ensure_database() -> InitResult:
    """Migrate the schema once per process; return what that first run did."""
    return init_database(get_engine())


@contextmanager
def get_db() -> Generator[Session]:
    """Get the database session, preparing the schema on first use."""
    ensure_database()
    with Session(get_engine(), autoflush=False) as session:
        yield session
