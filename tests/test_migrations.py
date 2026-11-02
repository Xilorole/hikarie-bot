import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from hikarie_bot.constants import JST
from hikarie_bot.database import BaseSchema, configure_sqlite
from hikarie_bot.migrations import SCRIPT_LOCATION, UnversionedDatabaseError, init_database
from hikarie_bot.models import ArrivalEvent


def _file_engine(path: Path) -> Engine:
    engine = create_engine(f"sqlite:///{path}")
    configure_sqlite(engine)
    return engine


def test_upgrade_creates_schema_matching_models(tmp_path: Path) -> None:
    """Migrations produce exactly the models' schema, and rerunning is a no-op."""
    engine = _file_engine(tmp_path / "data.db")

    init_database(engine)
    init_database(engine)

    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), BaseSchema.metadata) == []
        assert connection.execute(text("SELECT version_num FROM alembic_version")).all() == [("0002",)]
        assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"
    engine.dispose()


def test_upgrade_rejects_database_from_before_alembic(tmp_path: Path) -> None:
    """A database with tables but no Alembic version is refused, not adopted."""
    engine = _file_engine(tmp_path / "data.db")
    BaseSchema.metadata.create_all(engine)

    with pytest.raises(UnversionedDatabaseError, match="rebuild the data from Slack"):
        init_database(engine)
    assert "alembic_version" not in inspect(engine).get_table_names()
    engine.dispose()


def test_upgrade_from_0000_drops_unused_tables_and_keeps_events(tmp_path: Path) -> None:
    """Revisions 0001 and 0002 remove the computed and unused tables, and leave the events alone."""
    engine = _file_engine(tmp_path / "data.db")
    config = Config()
    config.set_main_option("script_location", str(SCRIPT_LOCATION))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0000")
        connection.execute(
            text(
                "INSERT INTO arrival_event (user_id, occurred_at, source, recorded_at) "
                "VALUES ('U1', '2026-11-02T00:00:00.000000+00:00', 'button', '2026-11-02T00:00:00.000000+00:00')"
            )
        )

    assert init_database(engine).revision_before == "0000"

    assert set(inspect(engine).get_table_names()) == {"alembic_version", "arrival_event"}
    with Session(engine) as session:
        assert session.query(ArrivalEvent).one().user_id == "U1"
    engine.dispose()


def test_0002_drops_sync_state_and_downgrade_recreates_it_empty(tmp_path: Path) -> None:
    """Revision 0002 drops the sync position; downgrading brings the table back empty."""
    engine = _file_engine(tmp_path / "data.db")
    config = Config()
    config.set_main_option("script_location", str(SCRIPT_LOCATION))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0001")
        connection.execute(
            text("INSERT INTO sync_state VALUES ('C1', '1.1', '2026-11-02T00:00:00.000000+00:00')"),
        )
        command.upgrade(config, "0002")
        assert "sync_state" not in inspect(connection).get_table_names()
        command.downgrade(config, "0001")
        assert connection.execute(text("SELECT count(*) FROM sync_state")).scalar() == 0
    engine.dispose()


def test_arrival_event_stores_utc_and_rejects_naive_datetimes() -> None:
    """Event times round-trip as aware UTC, and slack_ts is unique when present."""
    engine = create_engine("sqlite://")
    init_database(engine)
    with Session(engine) as session:
        occurred_at = datetime(2026, 11, 2, 9, 0, tzinfo=JST)
        session.add_all(
            [
                ArrivalEvent(user_id="U1", occurred_at=occurred_at, source="button", slack_ts="1.1"),
                ArrivalEvent(user_id="U1", occurred_at=occurred_at, source="button"),
                ArrivalEvent(user_id="U2", occurred_at=occurred_at, source="button"),
            ]
        )
        session.commit()
        session.expire_all()

        stored = session.query(ArrivalEvent).first()
        assert stored.occurred_at == occurred_at
        assert stored.occurred_at.tzinfo == UTC

        session.add(ArrivalEvent(user_id="U3", occurred_at=occurred_at, source="slack_v3", slack_ts="1.1"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(ArrivalEvent(user_id="U3", occurred_at=datetime(2026, 11, 2, 9, 0), source="button"))  # noqa: DTZ001
        with pytest.raises(StatementError, match="timezone-aware"):
            session.commit()


def test_read_only_open_of_wal_database(tmp_path: Path) -> None:
    """A WAL database can still be opened read-only (as the preview command does) after use."""
    database = tmp_path / "data.db"
    engine = _file_engine(database)
    init_database(engine)
    engine.dispose()

    with sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == ("0002",)
