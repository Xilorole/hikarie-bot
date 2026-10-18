import json
import sqlite3
from pathlib import Path

import pytest
from cryptography.fernet import Fernet, InvalidToken

from hikarie_bot.initial_data import initialize_database


def write_manifest(directory: Path, mode: str = "empty") -> Path:
    """Write a test seed manifest."""
    directory.mkdir(parents=True, exist_ok=True)
    manifest = directory / "manifest.json"
    manifest.write_text(json.dumps({"format_version": 1, "mode": mode}))
    return manifest


def test_empty_seed_and_existing_database(tmp_path: Path) -> None:
    """Create schema and badges with no users, and preserve subsequent changes."""
    manifest = write_manifest(tmp_path / "seed")
    database = tmp_path / "db" / "data.db"
    assert initialize_database(manifest, database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM user").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM guest_arrival_raw").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM badges").fetchone()[0] > 0
        connection.execute("CREATE TABLE sentinel (value TEXT)")
        connection.execute("INSERT INTO sentinel VALUES ('preserved')")
    manifest.unlink()
    assert not initialize_database(manifest, database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM sentinel").fetchone() == ("preserved",)


def test_encrypted_seed(tmp_path: Path) -> None:
    """Load an authenticated SQLite snapshot with the matching key."""
    source = tmp_path / "source.db"
    manifest = write_manifest(tmp_path / "seed")
    initialize_database(manifest, source)
    plaintext = source.read_bytes()
    key = Fernet.generate_key()
    key_file = tmp_path / "key"
    key_file.write_bytes(key)
    manifest = write_manifest(manifest.parent, "fernet-sqlite")
    (manifest.parent / "snapshot.sqlite.fernet").write_bytes(Fernet(key).encrypt(plaintext))
    destination = tmp_path / "destination" / "data.db"
    assert initialize_database(manifest, destination, key_file)
    assert destination.read_bytes() == plaintext


@pytest.mark.parametrize("failure", ["missing-key", "wrong-key", "tampered", "invalid-sqlite"])
def test_failed_decryption_never_publishes_database(tmp_path: Path, failure: str) -> None:
    """Reject invalid inputs without creating a destination or leaving plaintext."""
    manifest = write_manifest(tmp_path / "seed", "fernet-sqlite")
    key = Fernet.generate_key()
    key_file = tmp_path / "key"
    key_file.write_bytes(Fernet.generate_key() if failure == "wrong-key" else key)
    payload = Fernet(key).encrypt(b"not a database")
    if failure == "tampered":
        payload = payload[:-10] + b"corrupted!"
    (manifest.parent / "snapshot.sqlite.fernet").write_bytes(payload)
    destination = tmp_path / "db" / "data.db"
    with pytest.raises((ValueError, InvalidToken, sqlite3.DatabaseError)):
        initialize_database(manifest, destination, None if failure == "missing-key" else key_file)
    assert not destination.exists()
    assert not list(destination.parent.glob(".initial-data-*"))


def test_existing_invalid_database_is_not_overwritten(tmp_path: Path) -> None:
    """Fail explicitly for an invalid existing destination."""
    manifest = write_manifest(tmp_path / "seed")
    destination = tmp_path / "data.db"
    destination.write_bytes(b"existing invalid data")
    with pytest.raises(sqlite3.DatabaseError):
        initialize_database(manifest, destination)
    assert destination.read_bytes() == b"existing invalid data"


def test_unknown_manifest_version(tmp_path: Path) -> None:
    """Reject unsupported seed formats rather than silently creating an empty DB."""
    manifest = write_manifest(tmp_path / "seed")
    manifest.write_text('{"format_version": 2, "mode": "empty"}')
    destination = tmp_path / "db" / "data.db"
    with pytest.raises(ValueError, match="format version"):
        initialize_database(manifest, destination)
    assert not destination.exists()


@pytest.mark.parametrize("content", ["[]", '{"format_version": 1, "mode": "unknown"}', "{"])
def test_invalid_manifest(tmp_path: Path, content: str) -> None:
    """Reject malformed manifests before creating any database file."""
    manifest = write_manifest(tmp_path / "seed")
    manifest.write_text(content)
    destination = tmp_path / "db" / "data.db"
    with pytest.raises((TypeError, ValueError)):
        initialize_database(manifest, destination)
    assert not destination.exists()


def test_incompatible_snapshot(tmp_path: Path) -> None:
    """Reject valid SQLite files that do not contain the application schema."""
    source = tmp_path / "unrelated.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE unrelated (id INTEGER)")
    manifest = write_manifest(tmp_path / "seed", "fernet-sqlite")
    key = Fernet.generate_key()
    key_file = tmp_path / "key"
    key_file.write_bytes(key)
    (manifest.parent / "snapshot.sqlite.fernet").write_bytes(Fernet(key).encrypt(source.read_bytes()))
    destination = tmp_path / "db" / "data.db"
    with pytest.raises(ValueError, match="missing table"):
        initialize_database(manifest, destination, key_file)
    assert not destination.exists()
    assert not list(destination.parent.glob(".initial-data-*"))
