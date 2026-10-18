"""Initialize a persistent database from an empty or encrypted seed image."""

import argparse
import fcntl
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from hikarie_bot.curd import initially_insert_badge_data
from hikarie_bot.database import BaseSchema

MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024


def _validate_database(path: Path) -> None:
    """Check SQLite integrity and compatibility before publishing a seed."""
    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as connection:
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            msg = "Initial database failed its integrity check"
            raise ValueError(msg)
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for table in BaseSchema.metadata.sorted_tables:
            if table.name not in tables:
                msg = f"Initial database is missing table {table.name}"
                raise ValueError(msg)
            columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table.name}")')}
            if not set(table.columns.keys()).issubset(columns):
                msg = f"Initial database has incompatible columns in {table.name}"
                raise ValueError(msg)


def _populate_database(path: Path, manifest_path: Path, mode: str, key_file: Path | None) -> None:
    """Prepare a temporary database without exposing partially loaded data."""
    if mode == "empty":
        engine = create_engine(f"sqlite:///{path}")
        try:
            BaseSchema.metadata.create_all(engine)
            with Session(engine) as session:
                initially_insert_badge_data(session)
        finally:
            engine.dispose()
    else:
        if key_file is None:
            msg = "Encrypted initial data requires a secret key file"
            raise ValueError(msg)
        snapshot_path = manifest_path.parent / "snapshot.sqlite.fernet"
        if snapshot_path.stat().st_size > MAX_SNAPSHOT_BYTES:
            msg = "Encrypted initial data exceeds the size limit"
            raise ValueError(msg)
        plaintext = Fernet(key_file.read_bytes().strip()).decrypt(snapshot_path.read_bytes())
        path.write_bytes(plaintext)


def initialize_database(manifest_path: Path, database_path: Path, key_file: Path | None = None) -> bool:
    """Initialize a missing SQLite database, never replacing an existing file."""
    database_path = database_path.resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with (database_path.parent / ".initial-data.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if database_path.exists():
            _validate_database(database_path)
            logger.info("Existing database preserved; seed import skipped")
            return False

        manifest = json.loads(manifest_path.read_text())
        if not isinstance(manifest, dict):
            msg = "Initial-data manifest must be a JSON object"
            raise TypeError(msg)
        if manifest.get("format_version") != 1:
            msg = "Unsupported initial-data format version"
            raise ValueError(msg)
        mode = manifest.get("mode")
        if mode not in {"empty", "fernet-sqlite"}:
            msg = "Unsupported initial-data mode"
            raise ValueError(msg)

        descriptor, temporary_name = tempfile.mkstemp(prefix=".initial-data-", dir=database_path.parent)
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        try:
            _populate_database(temporary_path, manifest_path, mode, key_file)
            _validate_database(temporary_path)
            with temporary_path.open("rb") as snapshot:
                os.fsync(snapshot.fileno())
            # A hard link publishes the complete file without overwriting an existing destination.
            os.link(temporary_path, database_path)
            directory_descriptor = os.open(database_path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
            logger.info("Initial database installed successfully ({})", mode)
            return True
        finally:
            temporary_path.unlink(missing_ok=True)


def main() -> None:
    """Run the seed-image entry point and report initialization failures."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("/opt/initial-data/manifest.json"))
    parser.add_argument("--database", type=Path, default=Path("/opt/.db/data.db"))
    parser.add_argument("--key-file", type=Path)
    args = parser.parse_args()
    try:
        initialize_database(args.manifest, args.database, args.key_file)
    except (OSError, ValueError, TypeError, sqlite3.DatabaseError, SQLAlchemyError, InvalidToken) as error:
        logger.error("Initial database setup failed: {}", type(error).__name__)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
