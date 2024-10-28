from collections.abc import Generator
from typing import Any, Self

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy_utils import database_exists, drop_database

from hikarie_bot.database import BaseSchema


class DatabaseExistsError(Exception):
    """Raised when the test database already exists."""

    def __init__(self: Self, url: str) -> None:
        """Initialize the DatabaseExistsError class."""
        super().__init__(f"Test database; {url} already exists. Aborting tests.")


@pytest.fixture
def temp_db() -> Generator[sessionmaker[Session], Any, Any]:
    """Create a test database and tables."""
    import tempfile

    with tempfile.TemporaryFile() as temp_db_file:
        DB_PATH = temp_db_file.name  # noqa: N806

        # settings of test database
        TEST_SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"  # noqa: N806
        engine = create_engine(
            TEST_SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
        )

        if database_exists(TEST_SQLALCHEMY_DATABASE_URL):
            raise DatabaseExistsError(TEST_SQLALCHEMY_DATABASE_URL)

        # Create test database and tables
        BaseSchema.metadata.create_all(engine)
        session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        # Run the tests
        yield session

        # Drop the test database
        drop_database(TEST_SQLALCHEMY_DATABASE_URL)
