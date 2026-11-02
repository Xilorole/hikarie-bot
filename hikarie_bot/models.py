from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Dialect, ForeignKey, Integer, String, event, func
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Mapper, Session, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from .database import BaseSchema, SessionLocal, engine

if TYPE_CHECKING:
    from hikarie_bot.migrations import InitResult


# Define the GuestArrivalInfo table
class GuestArrivalInfo(BaseSchema):
    """Define the GuestArrivalInfo table.

    The GuestArrivalInfo table stores the refined data of guest arrival information.
    The refined data includes the user ID, the arrival time, the arrival rank,
    the acquired score, the acquired score time, and the acquired score rank.
    """

    __tablename__ = "guest_arrival_info"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, unique=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("user.id"), nullable=False)
    user_info_raw_id: Mapped[str] = mapped_column(String, ForeignKey("user_raw.user_id"), nullable=False)
    arrival_time: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    arrival_rank: Mapped[int] = mapped_column(Integer)
    acquired_score_sum: Mapped[int] = mapped_column(Integer)

    def __repr__(self) -> str:
        """Return the string representation of the GuestArrivalInfo class."""
        return (
            f"<GuestArrivalInfo(user_id={self.user_id}, "
            f"arrival_time={self.arrival_time}, "
            f"arrival_rank={self.arrival_rank}, "
            f"acquired_score_sum={self.acquired_score_sum})>"
        )


@event.listens_for(GuestArrivalInfo, "before_insert")
def set_user_info_raw_id_for_info(
    mapper: Mapper[GuestArrivalInfo],  # noqa: ARG001
    connection: Connection,  # noqa: ARG001
    target: GuestArrivalInfo,
) -> None:
    """Set user_info_raw_id to the same value as user_id before insert."""
    if target.user_id and not target.user_info_raw_id:
        target.user_info_raw_id = target.user_id


class Achievement(BaseSchema):
    """Define the Achievement table.

    The Achievement table stores the user ID, arrival data, and the badges
    The badges are related to single arrival data.
    """

    __tablename__ = "achievement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, unique=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("user.id"), nullable=False)
    user_info_raw_id: Mapped[str] = mapped_column(String, ForeignKey("user_raw.user_id"), nullable=False)
    arrival_id: Mapped[int] = mapped_column(Integer, ForeignKey("guest_arrival_info.id"), nullable=False)
    badge_id: Mapped[int] = mapped_column(Integer, ForeignKey("badges.id"), nullable=False)
    achieved_time: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    user = relationship("User", backref="achievement")
    arrival = relationship("GuestArrivalInfo", backref="achievement")
    badge = relationship("Badge", backref="achievement")

    def __repr__(self) -> str:
        """Return the string representation of the Achievement class."""
        return (
            f"<Achievement(user_id={self.user_id}, "
            f"arrival_id={self.arrival_id}, "
            f"badge_id={self.badge_id}, "
            f"achieved_time={self.achieved_time})>"
        )


@event.listens_for(Achievement, "before_insert")
def set_user_info_raw_id_for_achievement(
    mapper: Mapper[Achievement],  # noqa: ARG001
    connection: Connection,  # noqa: ARG001
    target: Achievement,
) -> None:
    """Set user_info_raw_id to the same value as user_id before insert."""
    if target.user_id and not target.user_info_raw_id:
        target.user_info_raw_id = target.user_id


# Define the UserScore table
class User(BaseSchema):
    """Define the UserScore table.

    The UserScore table stores the user ID, the current score, the previous score,
    and the update datetime. This table only stores the latest data.
    """

    __tablename__ = "user"

    id: Mapped[str] = mapped_column(String, primary_key=True, unique=True)
    current_score: Mapped[int] = mapped_column(Integer)
    previous_score: Mapped[int] = mapped_column(Integer)
    update_datetime: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    level: Mapped[int] = mapped_column(Integer)
    level_name: Mapped[str] = mapped_column(String)
    level_uped: Mapped[bool] = mapped_column(Boolean)
    point_to_next_level: Mapped[int] = mapped_column(Integer)
    point_range_to_next_level: Mapped[int] = mapped_column(Integer)
    current_level_point: Mapped[int] = mapped_column(Integer)

    guest_arrivals_info = relationship("GuestArrivalInfo", backref="user")
    badges = relationship("UserBadge", back_populates="user")

    def __repr__(self) -> str:
        """Return the string representation of the User class."""
        return (
            f"<User(id={self.id}, "
            f"current_score={self.current_score}, "
            f"previous_score={self.previous_score}, "
            f"update_datetime={self.update_datetime})>"
        )


# Define the UserInfo table
class UserInfoRaw(BaseSchema):
    """Define the UserInfoRaw table.

    The UserInfoRaw table stores user info in stream.
    This is the snapshot of the `User` table at the time of the `User.update_datetime`.
    """

    __tablename__ = "user_raw"

    # the UserInfoRaw.id is just the auto incremented id
    id: Mapped[int] = mapped_column(Integer, primary_key=True, unique=True, autoincrement=True)

    # the user_id is the same as the user.id
    user_id: Mapped[str] = mapped_column(String, ForeignKey("user.id"), nullable=False)
    current_score: Mapped[int] = mapped_column(Integer)
    previous_score: Mapped[int] = mapped_column(Integer)
    update_datetime: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    level: Mapped[int] = mapped_column(Integer)
    level_name: Mapped[str] = mapped_column(String)
    level_uped: Mapped[bool] = mapped_column(Boolean)
    point_to_next_level: Mapped[int] = mapped_column(Integer)
    point_range_to_next_level: Mapped[int] = mapped_column(Integer)
    current_level_point: Mapped[int] = mapped_column(Integer)

    guest_arrivals_info = relationship("GuestArrivalInfo", backref="user_raw")
    user_badges = relationship("UserBadge", back_populates="user_raw")

    def __repr__(self) -> str:
        """Return the string representation of the UserInfoRaw class."""
        return (
            f"<UserInfoRaw(id={self.id}, "
            f"user_id={self.user_id}, "
            f"current_score={self.current_score}, "
            f"previous_score={self.previous_score}, "
            f"update_datetime={self.update_datetime})>"
        )


class BadgeType(BaseSchema):
    "Define the BadgeType table."

    __tablename__ = "badge_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String)
    apply_start: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    badges = relationship("Badge", back_populates="badge_type")

    def __repr__(self) -> str:
        """Return the string representation of the BadgeType class."""
        return f"<BadgeType(name={self.name}, description={self.description})>"


class Badge(BaseSchema):
    "Define the Badge table."

    __tablename__ = "badges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, unique=True)
    message: Mapped[str] = mapped_column(String)
    condition: Mapped[str] = mapped_column(String)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    badge_type_id: Mapped[int] = mapped_column(Integer, ForeignKey("badge_types.id"), nullable=False)

    badge_type = relationship("BadgeType", back_populates="badges")
    users = relationship("UserBadge", back_populates="badge")

    def __repr__(self) -> str:
        """Return the string representation of the Badge class."""
        return f"<Badge(message={self.message}, condition={self.condition}, level={self.level}, score={self.score})>"


class UserBadge(BaseSchema):
    """Define the UserBadge table."""

    __tablename__ = "user_badges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, unique=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"))
    user_info_raw_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_raw.user_id"))
    badge_id: Mapped[int] = mapped_column(Integer, ForeignKey("badges.id"))
    initially_acquired_datetime: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    last_acquired_datetime: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    count: Mapped[int] = mapped_column(Integer)

    user = relationship("User", back_populates="badges")
    user_raw = relationship("UserInfoRaw", back_populates="user_badges")
    badge = relationship("Badge", back_populates="users")

    def __repr__(self) -> str:
        """Return the string representation of the UserBadge class."""
        return (
            f"<UserBadge(user_id={self.user_id}, "
            f"badge_id={self.badge_id}, "
            f"initially_acquired_datetime={self.initially_acquired_datetime}, "
            f"last_acquired_datetime={self.last_acquired_datetime}, "
            f"count={self.count})>"
        )


@event.listens_for(UserBadge, "before_insert")
def set_user_info_raw_id_for_user_badge(
    mapper: Mapper[UserBadge],  # noqa: ARG001
    connection: Connection,  # noqa: ARG001
    target: UserBadge,
) -> None:
    """Set user_info_raw_id to the same value as user_id before insert."""
    if target.user_id and not target.user_info_raw_id:
        target.user_info_raw_id = target.user_id


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

    The source of truth for arrivals; append-only. Scores, ranks and badges are derived
    from these events. Several events for the same user and day are allowed; the first
    one counts. slack_ts identifies the Slack message the event was read from or posted as.
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


class SyncState(BaseSchema):
    """Define the SyncState table.

    How far a Slack channel has been read: the newest message ts seen, thread replies included.
    """

    __tablename__ = "sync_state"

    channel_id: Mapped[str] = mapped_column(String, primary_key=True)
    synced_until: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=lambda: datetime.now(UTC))

    def __repr__(self) -> str:
        """Return the string representation of the SyncState class."""
        return f"<SyncState(channel_id={self.channel_id}, synced_until={self.synced_until})>"


# Dependency

_initialized_engines: dict[int, "InitResult"] = {}


def ensure_database() -> "InitResult":
    """Migrate the schema and sync master data once per process; return what that first run did."""
    if id(engine) not in _initialized_engines:
        from hikarie_bot.migrations import init_database  # migrations imports this module

        _initialized_engines[id(engine)] = init_database(engine)
    return _initialized_engines[id(engine)]


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Get the database session, preparing the schema and master data on first use."""
    ensure_database()
    db = SessionLocal()  # sessionを生成
    try:
        yield db
    finally:
        db.close()
