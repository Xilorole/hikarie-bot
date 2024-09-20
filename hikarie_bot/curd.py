from datetime import datetime, timedelta

from loguru import logger
from sqlalchemy.orm import Session

from .models import GuestArrivalInfo, GuestArrivalRaw, User
from .utils import (
    get_current_level_point,
    get_level,
    get_level_name,
    get_point_range_to_next_level,
    get_point_to_next_level,
    get_time_score,
    is_level_uped,
)


def insert_arrival_action(
    session: Session, jst_datetime: datetime, user_id: str
) -> bool:
    """Insert the arrival action into the database.

    Args:
    ----
        session (Session): The session factory to interact with the database.
        jst_datetime (datetime): The arrival time in JST.
        user_id (str): The user ID.

    Returns:
    -------
        bool: True if the arrival action is successfully inserted, False otherwise.

    """
    logger.info(f"inserting action; date: {jst_datetime}, user_id: {user_id}")
    session.add(GuestArrivalRaw(arrival_time=jst_datetime, user_id=user_id))
    session.commit()
    start_of_day = jst_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    logger.info(f"start of day: {start_of_day}, end of day: {end_of_day}")

    # Check for existing arrival for the same user on the same day
    existing_arrival = (
        session.query(GuestArrivalInfo)
        .filter(GuestArrivalInfo.user_id == user_id)
        .filter(GuestArrivalInfo.arrival_time >= start_of_day)
        .filter(GuestArrivalInfo.arrival_time < end_of_day)
        .first()
    )
    logger.info(f"existing arrival: {existing_arrival}")
    if existing_arrival:
        return False

    # Calculate the arrival rank
    # The arrival rank is the number of users arrived on the same day + 1
    same_day_arrivals = (
        session.query(GuestArrivalInfo)
        .filter(GuestArrivalInfo.arrival_time >= start_of_day)
        .filter(GuestArrivalInfo.arrival_time < end_of_day)
        .count()
    )
    arrival_rank = same_day_arrivals + 1

    # Determine the score based on arrival time
    time_score = get_time_score(jst_datetime)

    # add initial arrival bonus
    rank_score = 0

    # if the user arrived first and the time score is not 0
    # (thus the user arrived within the labour time), add 2 points
    if arrival_rank == 1 and time_score != 0:
        rank_score = 2

    logger.info(
        f"arrival rank: {arrival_rank}, "
        f"time score: {time_score}, "
        f"rank score: {rank_score}"
    )
    # Insert the new arrival
    new_arrival = GuestArrivalInfo(
        arrival_time=jst_datetime,
        user_id=user_id,
        arrival_rank=arrival_rank,
        acquired_score_sum=time_score + rank_score,
        acquired_time_score=time_score,
        acquired_rank_score=rank_score,
    )
    session.add(new_arrival)

    # Update user score
    user_score_entry = session.query(User).filter_by(id=user_id).one_or_none()

    # calculate_attribute
    if user_score_entry:
        previous_score = user_score_entry.current_score
        current_score = user_score_entry.current_score + time_score + rank_score
    else:
        previous_score = 0
        current_score = time_score + rank_score
    level = get_level(current_score)
    level_name = get_level_name(current_score)
    level_uped = is_level_uped(previous_score, current_score)
    point_to_next_level = get_point_to_next_level(current_score)
    point_range_to_next_level = get_point_range_to_next_level(current_score)
    current_level_point = get_current_level_point(current_score)

    if user_score_entry:
        user_score_entry.previous_score = previous_score
        user_score_entry.current_score = current_score
        user_score_entry.update_datetime = jst_datetime
        user_score_entry.level = level
        user_score_entry.level_name = level_name
        user_score_entry.level_uped = level_uped
        user_score_entry.point_to_next_level = point_to_next_level
        user_score_entry.point_range_to_next_level = point_range_to_next_level
        user_score_entry.current_level_point = current_level_point
    else:
        # Create a new entry if the user doesn't exist in user_score table
        new_user_score = User(
            id=user_id,
            current_score=current_score,
            previous_score=previous_score,
            update_datetime=jst_datetime,
            level=level,
            level_name=level_name,
            level_uped=level_uped,
            point_to_next_level=point_to_next_level,
            point_range_to_next_level=point_range_to_next_level,
            current_level_point=current_level_point,
        )
        session.add(new_user_score)

    session.commit()
    return True
