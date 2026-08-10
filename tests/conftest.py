"""Shared pytest fixtures for hikarie-bot."""

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from hikarie_bot.curd import initially_insert_badge_data
from hikarie_bot.database import BaseSchema


@pytest.fixture
def temp_db() -> Generator[sessionmaker[Session], None, None]:
    """Provide a session factory bound to a throwaway in-memory database.

    The database lives only for the duration of a single test, so tests never
    share state and no files are left behind.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    BaseSchema.metadata.create_all(engine)

    try:
        yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
    finally:
        BaseSchema.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def session(temp_db: sessionmaker[Session]) -> Generator[Session, None, None]:
    """Provide a ready-to-use session with the badge master data inserted."""
    with temp_db() as db_session:
        initially_insert_badge_data(db_session)
        yield db_session
