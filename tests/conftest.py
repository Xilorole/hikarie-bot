from collections.abc import Iterator

import pytest
from loguru import logger
from sqlalchemy import Engine

from hikarie_bot.database import get_engine
from hikarie_bot.models import ensure_database
from hikarie_bot.settings import Settings, get_settings

# Disable loguru logging during tests for better performance
logger.disable("hikarie_bot")


@pytest.fixture(autouse=True)
def settings() -> Iterator[Settings]:
    """Give each test fresh application settings (ENV=test reads no env file); assign fields freely."""
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture
def app_database() -> Iterator[Engine]:
    """Give the application (get_db) a fresh, migrated in-memory database."""
    get_engine.cache_clear()
    ensure_database.cache_clear()
    ensure_database()
    yield get_engine()
    get_engine.cache_clear()
    ensure_database.cache_clear()
