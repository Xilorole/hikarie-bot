import os
from functools import cache
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

from hikarie_bot.exceptions import DatabaseLocationError
from hikarie_bot.settings import get_settings


def configure_sqlite(engine: Engine) -> None:
    """Use WAL and a busy timeout for file-backed SQLite databases."""
    url = make_url(str(engine.url))
    if url.get_backend_name() != "sqlite" or url.database in {None, "", ":memory:"} or "mode=ro" in str(url):
        return

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


def check_sqlite_location(url: str) -> None:
    """Explain why a SQLite file could not be opened, before SQLite says only "unable to open".

    Raises DatabaseLocationError naming the directory and the likely fix.
    """
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" or parsed.database in {None, "", ":memory:"} or "mode=ro" in url:
        return
    path = Path(parsed.database)
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
    """Create the application's engine from DATABASE_URL on first use."""
    settings = get_settings()
    settings.require("database_url")
    url = settings.database_url
    check_sqlite_location(url)
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False},
        # an in-memory database (dev/test) lives in one connection, which worker threads must share
        **({"poolclass": StaticPool} if make_url(url).database in {None, "", ":memory:"} else {}),
    )
    configure_sqlite(engine)
    return engine


class BaseSchema(DeclarativeBase):
    """Base class for defining the schema of the database."""
