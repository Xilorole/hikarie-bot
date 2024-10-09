from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

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
    user_id = Column(String, ForeignKey("user.id"))
    arrival_time = Column(DateTime, default=datetime.now(UTC))


# Define the GuestArrivalInfo table
class GuestArrivalInfo(BaseSchema):
    """Define the GuestArrivalInfo table.

    The GuestArrivalInfo table stores the refined data of guest arrival information.
    The refined data includes the user ID, the arrival time, the arrival rank,
    the acquired score, the acquired score time, and the acquired score rank.
    """

    __tablename__ = "guest_arrival_info"

    id = Column(Integer, primary_key=True)
    arrival_time = Column(DateTime, default=datetime.now(UTC))
    user_id = Column(String, ForeignKey("user.id"))
    arrival_rank = Column(Integer)
    acquired_score_sum = Column(Integer)
    acquired_time_score = Column(Integer)
    acquired_rank_score = Column(Integer)
    straight_flash_score = Column(Integer)


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
    update_datetime = Column(DateTime, default=datetime.now(UTC))
    level = Column(Integer)
    level_name = Column(String)
    level_uped = Column(Boolean)
    point_to_next_level = Column(Integer)
    point_range_to_next_level = Column(Integer)
    current_level_point = Column(Integer)
