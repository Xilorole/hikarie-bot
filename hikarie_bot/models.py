from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from .database import BaseSchema


# define the GuestArrivalRaw table
class GuestArrivalRaw(BaseSchema):
    """Define the GuestArrivalRaw table.

    The GuestArrivalRaw table stores the raw data of guest arrival information.
    The raw data includes the user ID and the arrival time.
    Refined data is stored in the GuestArrivalInfo table.
    """

    __tablename__ = "guest_arrival_raw"

    id = Column(Integer, primary_key=True)
    user_id = Column(String, ForeignKey("user.id"), nullable=False)
    arrival_time = Column(DateTime, default=func.now())


# Define the GuestArrivalInfo table
class GuestArrivalInfo(BaseSchema):
    """Define the GuestArrivalInfo table.

    The GuestArrivalInfo table stores the refined data of guest arrival information.
    The refined data includes the user ID, the arrival time, the arrival rank,
    the acquired score, the acquired score time, and the acquired score rank.
    """

    __tablename__ = "guest_arrival_info"

    id = Column(Integer, primary_key=True)
    user_id = Column(String, ForeignKey("user.id"), nullable=False)
    arrival_time = Column(DateTime, default=func.now())
    arrival_rank = Column(Integer)
    acquired_score_sum = Column(Integer)
    acquired_time_score = Column(Integer)
    acquired_rank_score = Column(Integer)
    straight_flash_score = Column(Integer)


class Achievement(BaseSchema):
    """Define the Achievement table.

    The Achievement table stores the user ID, arrival data, and the badges
    The badges are related to single arrival data.
    """

    __tablename__ = "achievement"

    id = Column(Integer, primary_key=True)
    user_id = Column(String, ForeignKey("user.id"), nullable=False)
    arrival_id = Column(Integer, ForeignKey("guest_arrival_info.id"), nullable=False)
    badge_id = Column(Integer, ForeignKey("badges.id"), nullable=False)
    achieved_time = Column(DateTime, default=func.now())

    user = relationship("User", backref="achievement")
    arrival = relationship("GuestArrivalInfo", backref="achievement")
    badges = relationship("Badge", backref="achievement")


# Define the UserScore table
class User(BaseSchema):
    """Define the UserScore table.

    The UserScore table stores the user ID, the current score, the previous score,
    and the update datetime.
    """

    __tablename__ = "user"

    id = Column(String, primary_key=True)
    current_score = Column(Integer)
    previous_score = Column(Integer)
    update_datetime = Column(DateTime, default=func.now())
    level = Column(Integer)
    level_name = Column(String)
    level_uped = Column(Boolean)
    point_to_next_level = Column(Integer)
    point_range_to_next_level = Column(Integer)
    current_level_point = Column(Integer)

    guest_arrivals_raw = relationship("GuestArrivalRaw", backref="user")
    guest_arrivals_info = relationship("GuestArrivalInfo", backref="user")
    badges = relationship("UserBadge", back_populates="user")


class BadgeType(BaseSchema):
    "Define the BadgeType table."

    __tablename__ = "badge_types"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String)

    badges = relationship("Badge", back_populates="badge_type")


class Badge(BaseSchema):
    "Define the Badge table."

    __tablename__ = "badges"

    id = Column(Integer, primary_key=True)
    message = Column(String)
    condition = Column(String)
    level = Column(Integer, nullable=False)
    score = Column(Integer, nullable=False)
    badge_type_id = Column(Integer, ForeignKey("badge_types.id"), nullable=False)

    badge_type = relationship("BadgeType", back_populates="badges")
    users = relationship("UserBadge", back_populates="badge")


class UserBadge(BaseSchema):
    """Define the UserBadge table."""

    __tablename__ = "user_badges"

    user_id = Column(Integer, ForeignKey("user.id"), primary_key=True)
    badge_id = Column(Integer, ForeignKey("badges.id"), primary_key=True)
    acquired_date = Column(DateTime, default=func.now())

    user = relationship("User", back_populates="badges")
    badge = relationship("Badge", back_populates="users")
