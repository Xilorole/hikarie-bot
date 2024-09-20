from datetime import datetime

from pydantic import BaseModel


class User(BaseModel):
    """Define the UserScore table."""

    id: str
    current_score: int
    previous_score: int
    update_datetime: datetime
    level: int
    level_name: str


class GuestArrivalRaw(BaseModel):
    """Define the GuestArrivalRaw table."""

    id: int
    user_id: str
    arrival_time: datetime


class GuestArrivalInfo(BaseModel):
    """Define the GuestArrivalInfo table."""

    id: int
    arrival_time: datetime
    user_id: str
    arrival_rank: int
    acquired_score: int
