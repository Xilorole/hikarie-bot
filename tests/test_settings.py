from pathlib import Path

import pytest

from hikarie_bot.exceptions import EnvironmentVariableNotFoundError, InMemoryDatabaseError
from hikarie_bot.settings import REQUIRED, Settings, env_file

REQUIRED_SLACK = ["OUTPUT_CHANNEL", "LOG_CHANNEL", "BOT_ID", "ADMIN"]


def test_settings_require_database_url_outside_dev_and_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """Production never falls back to an in-memory database; dev/test do."""
    for name in REQUIRED_SLACK:
        monkeypatch.setenv(name, "X")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test")
    monkeypatch.setenv("URL", "sqlite:///legacy.db")  # no longer read
    monkeypatch.setenv("ENV", "production")

    with pytest.raises(EnvironmentVariableNotFoundError, match="DATABASE_URL"):
        Settings(_env_file=None).require(*REQUIRED)

    monkeypatch.setenv("DATABASE_URL", "sqlite:////data/hikarie.db")
    Settings(_env_file=None).require(*REQUIRED)

    for in_memory in ("sqlite:///:memory:", "sqlite://"):
        monkeypatch.setenv("DATABASE_URL", in_memory)
        with pytest.raises(InMemoryDatabaseError, match="persistent volume"):
            Settings(_env_file=None).require("database_url")

    monkeypatch.setenv("ENV", "test")
    monkeypatch.delenv("DATABASE_URL")
    assert Settings(_env_file=None).database_url == "sqlite:///:memory:"


def test_settings_reject_missing_slack_values_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """The first missing required value is reported by its environment variable name."""
    monkeypatch.setenv("ENV", "production")
    for name in REQUIRED_SLACK:
        monkeypatch.delenv(name, raising=False)

    loaded = Settings(_env_file=None)  # reading the settings requires nothing

    with pytest.raises(EnvironmentVariableNotFoundError, match="OUTPUT_CHANNEL"):
        loaded.require(*REQUIRED)


def test_environment_wins_over_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Values come from the env file unless an environment variable is set."""
    env_file = tmp_path / ".env.dev"
    env_file.write_text("ENV=dev\nOUTPUT_CHANNEL=C_FROM_FILE\nLOG_CHANNEL=C_FILE\nSLACK_BOT_TOKEN=xoxb-from-file\n")
    monkeypatch.delenv("ENV")
    monkeypatch.setenv("LOG_CHANNEL", "C_FROM_ENV")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-injected")

    loaded = Settings(_env_file=env_file)

    assert loaded.output_channel == "C_FROM_FILE"
    assert loaded.log_channel == "C_FROM_ENV"
    assert loaded.slack_bot_token == "xoxb-injected"  # noqa: S105


def test_env_file_is_dotenv_path_or_working_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Outside tests the env file is DOTENV_PATH, else ./.env; never a parent directory's."""
    assert env_file() is None  # ENV=test

    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("DOTENV_PATH", ".env.dev")
    assert env_file() == ".env.dev"

    monkeypatch.delenv("DOTENV_PATH")
    (tmp_path / ".env").write_text("OUTPUT_CHANNEL=C_PARENT\n")
    (tmp_path / "child").mkdir()
    monkeypatch.chdir(tmp_path / "child")
    assert env_file() == ".env"
    assert Settings(_env_file=env_file()).output_channel == ""  # the parent's .env is not read
