from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from hikarie_bot.settings import DATABASE_URL

SQLALCHEMY_DATABASE_URL = DATABASE_URL


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


engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
configure_sqlite(engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class BaseSchema(DeclarativeBase):
    """Base class for defining the schema of the database."""
