"""Badge master data in the database, kept in sync with the definitions in code."""

from datetime import datetime

from loguru import logger
from sqlalchemy.orm import Session

from . import db_data
from .models import Badge, BadgeType


def _same_value(stored: object, expected: object) -> bool:
    # SQLite DateTime columns store wall-clock time without the timezone.
    if isinstance(stored, datetime) and isinstance(expected, datetime) and expected.tzinfo is not None:
        return stored.replace(tzinfo=None) == expected.replace(tzinfo=None)
    return stored == expected


def _sync_rows(session: Session, model: type, rows: list, fields: list[str]) -> tuple[int, int]:
    existing = {row.id: row for row in session.query(model).all()}
    inserted = updated = 0
    for row in rows:
        values = {field: getattr(row, field) for field in fields}
        current = existing.get(row.id)
        if current is None:
            session.add(model(id=row.id, **values))
            inserted += 1
        elif not all(_same_value(getattr(current, field), value) for field, value in values.items()):
            for field, value in values.items():
                setattr(current, field, value)
            updated += 1
    return inserted, updated


def sync_badge_master_data(session: Session) -> None:
    """Synchronize the badge master data in the database with the definitions in code.

    New badges are inserted and changed ones updated, so a persistent database picks up
    badges added in later releases. Rows no longer defined in code are kept because
    achievements may still reference them.

    Args:
    ----
        session (Session): The session factory to interact with the database.

    """
    badge_types = _sync_rows(session, BadgeType, db_data.BadgeTypes, ["name", "description", "apply_start"])
    session.flush()
    badges = _sync_rows(session, Badge, db_data.Badges, ["message", "condition", "level", "score", "badge_type_id"])
    session.commit()
    logger.info("Badge types synchronized (inserted, updated): {}; badges: {}", badge_types, badges)


# Kept for existing callers and tests.
initially_insert_badge_data = sync_badge_master_data
