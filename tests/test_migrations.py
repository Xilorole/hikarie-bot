import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from hikarie_bot.curd import sync_badge_master_data
from hikarie_bot.database import BaseSchema, configure_sqlite
from hikarie_bot.db_data import Badges, BadgeTypes
from hikarie_bot.migrations import UnversionedDatabaseError, init_database, upgrade_database
from hikarie_bot.models import ArrivalEvent, Badge, BadgeType, SyncState

JST = timezone(timedelta(hours=9))


def _file_engine(path: Path) -> Engine:
    engine = create_engine(f"sqlite:///{path}")
    configure_sqlite(engine)
    return engine


def test_upgrade_creates_schema_matching_models(tmp_path: Path) -> None:
    """Migrations produce exactly the models' schema, and rerunning is a no-op."""
    engine = _file_engine(tmp_path / "data.db")

    upgrade_database(engine)
    upgrade_database(engine)

    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), BaseSchema.metadata) == []
        assert connection.execute(text("SELECT version_num FROM alembic_version")).all() == [("0000",)]
        assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"
    engine.dispose()


def test_upgrade_rejects_database_from_before_alembic(tmp_path: Path) -> None:
    """A database with tables but no Alembic version is refused, not adopted."""
    engine = _file_engine(tmp_path / "data.db")
    BaseSchema.metadata.create_all(engine)

    with pytest.raises(UnversionedDatabaseError, match="rebuild the data from Slack"):
        upgrade_database(engine)
    assert "alembic_version" not in inspect(engine).get_table_names()
    engine.dispose()


def test_sync_badge_master_data_updates_persistent_database(tmp_path: Path) -> None:
    """Badges added or changed in code reach an existing database; unknown rows are kept."""
    engine = _file_engine(tmp_path / "data.db")
    init_database(engine)
    missing, changed = Badges[0], Badges[1]
    with Session(engine) as session:
        session.query(Badge).filter(Badge.id == missing.id).delete()
        session.query(Badge).filter(Badge.id == changed.id).one().message = "old message"
        session.add(Badge(id=999999, message="retired", condition="", level=1, score=0, badge_type_id=1))
        session.commit()

    init_database(engine)

    with Session(engine) as session:
        assert session.query(Badge).filter(Badge.id == missing.id).one().message == missing.message
        assert session.query(Badge).filter(Badge.id == changed.id).one().message == changed.message
        assert session.query(Badge).filter(Badge.id == 999999).one_or_none() is not None
        assert session.query(Badge).count() == len(Badges) + 1
        assert session.query(BadgeType).count() == len(BadgeTypes)
    engine.dispose()


def test_sync_badge_master_data_leaves_unchanged_rows_alone() -> None:
    """Timezone-aware apply_start values compare equal to their stored wall-clock form."""
    engine = create_engine("sqlite://")
    upgrade_database(engine)
    with Session(engine) as session:
        sync_badge_master_data(session)
        session.expire_all()
        sync_badge_master_data(session)
        assert not session.dirty
        assert not session.new


def test_arrival_event_stores_utc_and_rejects_naive_datetimes() -> None:
    """Event times round-trip as aware UTC, and slack_ts is unique when present."""
    engine = create_engine("sqlite://")
    upgrade_database(engine)
    with Session(engine) as session:
        occurred_at = datetime(2026, 11, 2, 9, 0, tzinfo=JST)
        session.add_all(
            [
                ArrivalEvent(user_id="U1", occurred_at=occurred_at, source="button", slack_ts="1.1"),
                ArrivalEvent(user_id="U1", occurred_at=occurred_at, source="button"),
                ArrivalEvent(user_id="U2", occurred_at=occurred_at, source="button"),
            ]
        )
        session.add(SyncState(channel_id="C1", synced_until="1.1"))
        session.commit()
        session.expire_all()

        stored = session.query(ArrivalEvent).first()
        assert stored.occurred_at == occurred_at
        assert stored.occurred_at.tzinfo == UTC
        assert session.query(SyncState).one().updated_at.tzinfo == UTC

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
        assert connection.execute("SELECT COUNT(*) FROM badges").fetchone()[0] == len(Badges)
