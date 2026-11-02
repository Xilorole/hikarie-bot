import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from hikarie_bot.database import check_sqlite_location, get_engine
from hikarie_bot.exceptions import DatabaseLocationError, InMemoryDatabaseError
from hikarie_bot.settings import Settings
from hikarie_bot.startup import StartupReporter


def test_writable_directory_passes(tmp_path: Path) -> None:
    """A writable directory needs nothing more."""
    check_sqlite_location(tmp_path / "data.db")


@pytest.mark.parametrize("url", ["sqlite://", "sqlite:///:memory:"])
def test_production_refuses_an_in_memory_database(url: str, settings: Settings) -> None:
    """An in-memory database would re-read the whole channel on every restart; dev/test may use one."""
    settings.env, settings.database_url = "production", url
    get_engine.cache_clear()

    with pytest.raises(InMemoryDatabaseError, match="persistent volume"):
        get_engine()

    settings.env = "test"
    assert get_engine().url.database in {None, ":memory:"}
    get_engine.cache_clear()


def test_missing_directory_names_it(tmp_path: Path) -> None:
    """A directory that does not exist (no volume mounted there) is named."""
    with pytest.raises(DatabaseLocationError, match=f"{tmp_path}/volume does not exist: mount the persistent volume"):
        check_sqlite_location(tmp_path / "volume" / "data.db")


def test_relative_path_suggests_four_slashes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Three slashes make the path relative; the message shows where it resolved and the absolute form."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(DatabaseLocationError, match=r"needs four slashes \(sqlite:////opt/\.db/data\.db\)"):
        check_sqlite_location(Path("opt/.db/data.db"))


@pytest.mark.skipif(os.getuid() == 0, reason="root can write anywhere")
def test_unwritable_directory_points_to_fs_group(tmp_path: Path) -> None:
    """A root-owned volume without fsGroup is reported with the fix."""
    directory = tmp_path / "volume"
    directory.mkdir(mode=0o555)
    try:
        with pytest.raises(DatabaseLocationError, match=r"is not writable by uid .*fsGroup to 10001"):
            check_sqlite_location(directory / "data.db")
    finally:
        directory.chmod(0o755)


@pytest.mark.asyncio
async def test_location_error_is_posted_with_its_explanation() -> None:
    """Configuration errors carry no data, so their message goes to the log channel."""
    client = AsyncMock()
    reporter = StartupReporter(client=client, channel="C0LOG", revision="abc1234")

    async def fail() -> None:
        async with reporter.step("database"):
            msg = "/opt/.db is not writable by uid 10001: …"
            raise DatabaseLocationError(msg)

    with pytest.raises(DatabaseLocationError):
        await fail()

    text = client.chat_postMessage.await_args.kwargs["text"]
    assert text.startswith(":warning: startup failed at *database* after ")
    assert "`DatabaseLocationError` (/opt/.db is not writable by uid 10001: …)" in text
