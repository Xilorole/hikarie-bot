"""The stored data: arrival events."""

from datetime import UTC, datetime

from sqlalchemy import Dialect, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from .database import BaseSchema


class UTCDateTime(TypeDecorator[datetime]):
    """Store timezone-aware datetimes as sortable UTC ISO 8601 text.

    SQLite has no timezone support, so naive values are rejected instead of guessed.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> str | None:  # noqa: ARG002
        """Convert an aware datetime to UTC text."""
        if value is None:
            return None
        if value.tzinfo is None:
            msg = "UTCDateTime requires a timezone-aware datetime"
            raise ValueError(msg)
        return value.astimezone(UTC).isoformat(timespec="microseconds")

    def process_result_value(self, value: str | None, dialect: Dialect) -> datetime | None:  # noqa: ARG002
        """Parse stored UTC text back to an aware datetime."""
        return None if value is None else datetime.fromisoformat(value)


class ArrivalEvent(BaseSchema):
    """Define the ArrivalEvent table.

    The source of truth for arrivals; append-only. Scores, ranks and badges are computed
    from these events (arrivals.compute_arrivals) and never stored. Several events for the
    same user and day are allowed; the first one counts. slack_ts identifies the Slack
    message the event was read from or posted as.
    """

    __tablename__ = "arrival_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    slack_ts: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=lambda: datetime.now(UTC))

    def __repr__(self) -> str:
        """Return the string representation of the ArrivalEvent class."""
        return f"<ArrivalEvent(user_id={self.user_id}, occurred_at={self.occurred_at}, source={self.source})>"
