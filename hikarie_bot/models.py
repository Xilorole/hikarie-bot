from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, event, func
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Mapper, Session, mapped_column, relationship

from .database import BaseSchema, SessionLocal, engine


# define the GuestArrivalRaw table
class GuestArrivalRaw(BaseSchema):
    """Define the GuestArrivalRaw table.

    The GuestArrivalRaw table stores the raw data of guest arrival information.
    The raw data includes the user ID and the arrival time.
    Refined data is stored in the GuestArrivalInfo table.
    """

    __tablename__ = "guest_arrival_raw"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, unique=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("user.id"), nullable=False)
    user_info_raw_id: Mapped[str] = mapped_column(
        String, ForeignKey("user_raw.user_id"), nullable=False
    )
    arrival_time: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    def __repr__(self) -> str:
        """Return the string representation of the GuestArrivalRaw class."""
        return (
            f"<GuestArrivalRaw(user_id={self.user_id}, "
            f"arrival_time={self.arrival_time})>"
        )


# Add event listener to automatically set user_info_raw_id from user_id
@event.listens_for(GuestArrivalRaw, "before_insert")
def set_user_info_raw_id(
    mapper: Mapper[GuestArrivalRaw],  # noqa: ARG001
    connection: Connection,  # noqa: ARG001
    target: GuestArrivalRaw,
) -> None:
    """Set user_info_raw_id to the same value as user_id before insert."""
    if target.user_id and not target.user_info_raw_id:
        target.user_info_raw_id = target.user_id


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
    user_info_raw_id: Mapped[str] = mapped_column(
        String, ForeignKey("user_raw.user_id"), nullable=False
    )
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
    user_info_raw_id: Mapped[str] = mapped_column(
        String, ForeignKey("user_raw.user_id"), nullable=False
    )
    arrival_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("guest_arrival_info.id"), nullable=False
    )
    badge_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("badges.id"), nullable=False
    )
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

    guest_arrivals_raw = relationship("GuestArrivalRaw", backref="user")
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
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, unique=True, autoincrement=True
    )

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

    guest_arrivals_raw = relationship("GuestArrivalRaw", backref="user_raw")
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
    badge_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("badge_types.id"), nullable=False
    )

    badge_type = relationship("BadgeType", back_populates="badges")
    users = relationship("UserBadge", back_populates="badge")

    def __repr__(self) -> str:
        """Return the string representation of the Badge class."""
        return (
            f"<Badge(message={self.message}, condition={self.condition}, "
            f"level={self.level}, score={self.score})>"
        )


class UserBadge(BaseSchema):
    """Define the UserBadge table."""

    __tablename__ = "user_badges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, unique=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"))
    user_info_raw_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_raw.user_id")
    )
    badge_id: Mapped[int] = mapped_column(Integer, ForeignKey("badges.id"))
    initially_acquired_datetime: Mapped[datetime] = mapped_column(
        DateTime, default=func.now()
    )
    last_acquired_datetime: Mapped[datetime] = mapped_column(
        DateTime, default=func.now()
    )
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


# Dependency


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Get the database session."""
    # create tables
    BaseSchema.metadata.create_all(engine)
    db = SessionLocal()  # sessionを生成
    try:
        yield db
    finally:
        db.close()
