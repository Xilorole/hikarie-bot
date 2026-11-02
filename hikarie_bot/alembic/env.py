"""Alembic environment: run migrations on a shared connection or on DATABASE_URL."""

from typing import Any

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

from hikarie_bot.database import BaseSchema
from hikarie_bot.models import UTCDateTime
from hikarie_bot.settings import get_settings


def _render_item(type_: str, obj: Any, _autogen_context: Any) -> str | bool:  # noqa: ANN401
    # Migrations must not import application types; UTCDateTime is stored as text.
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.String()"
    return False


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=BaseSchema.metadata,
        render_as_batch=True,  # SQLite cannot ALTER most constraints in place
        render_item=_render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


if (shared := context.config.attributes.get("connection")) is not None:
    _run(shared)
else:
    with create_engine(get_settings().database_url).connect() as connection:
        _run(connection)
