from collections.abc import Generator
from typing import Any, Self

import pytest
from loguru import logger
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from hikarie_bot.database import BaseSchema

# Disable loguru logging during tests for better performance
logger.disable("hikarie_bot")


class DatabaseExistsError(Exception):
    """Raised when the test database already exists."""

    def __init__(self: Self, url: str) -> None:
        """Initialize the DatabaseExistsError class."""
        super().__init__(f"Test database; {url} already exists. Aborting tests.")


@pytest.fixture(scope="session")
def test_engine() -> Generator[Engine, Any, Any]:
    """Create a test database engine for the entire test session."""
    # Use in-memory SQLite database for faster tests
    TEST_SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"  # noqa: N806
    engine = create_engine(
        TEST_SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        # Optimization: reduce SQL echo overhead
        echo=False,
    )

    # Create test database and tables
    BaseSchema.metadata.create_all(engine)

    # Run the tests
    yield engine

    # Cleanup
    BaseSchema.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="session")
def session_factory(test_engine: Engine) -> sessionmaker[Session]:
    """Create a session factory for the test session."""
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session")
def seed_badge_data(session_factory: sessionmaker[Session]) -> None:
    """Seed the badge data once for all tests."""
    from hikarie_bot.curd import initially_insert_badge_data

    with session_factory() as session:
        initially_insert_badge_data(session)


@pytest.fixture
def temp_db(
    session_factory: sessionmaker[Session], seed_badge_data: None
) -> Generator[sessionmaker[Session], Any, Any]:
    """Create a test database session with pre-seeded badge data.

    This fixture uses the session-scoped engine and badge data,
    but uses transaction rollback for fast cleanup after each test.
    """
    # Start a transaction
    connection = session_factory.kw["bind"].connect()
    transaction = connection.begin()

    # Create a session bound to the transaction
    test_session_factory = sessionmaker(bind=connection)

    # Run the test
    yield test_session_factory

    # Rollback the transaction to clean up test data (much faster than DELETE)
    transaction.rollback()
    connection.close()
