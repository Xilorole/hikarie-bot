from datetime import datetime, timedelta

from loguru import logger
from sqlalchemy.orm import Session

from .db_data import Badges, BadgeTypes
from .models import GuestArrivalInfo, GuestArrivalRaw, User
from .utils import (
    get_current_level_point,
    get_level,
    get_level_name,
    get_point_range_to_next_level,
    get_point_to_next_level,
    get_time_score,
    is_jp_bizday,
    is_level_uped,
)


def _check_straight_flash(
    session: Session, user_id: str, last_date: datetime, flash_length: int = 5
) -> bool:
    """Check if the user arrived at the office five days in a row.

    Args:
    ----
        session (Session): The session factory to interact with the database.
        user_id (str): The user ID.
        last_date (datetime): The last date to check for a straight flash.
        flash_length (int): The number of days to check for a straight flash.

    Returns:
    -------
        bool: True if the user has a straight flash, False otherwise.

    """
    # Get the user's arrival information
    user_arrivals = (
        session.query(GuestArrivalInfo)
        .filter(GuestArrivalInfo.user_id == user_id)
        .filter(GuestArrivalInfo.arrival_time <= last_date + timedelta(minutes=1))
        .order_by(GuestArrivalInfo.arrival_time.desc())
        .limit(5)
        .all()
    )

    # Check if the user has straight flash within last 5 arrivals
    if any(
        user_arrival.straight_flash_score > 0
        for user_arrival in user_arrivals
        if datetime.date(user_arrival.arrival_time) != last_date.date()
    ):
        logger.info("already has straight flash")
        return False

    # Check if the user has at least 5 arrivals
    if len(user_arrivals) < flash_length:
        logger.info(f"not enough arrivals: {len(user_arrivals)}")
        return False

    # Check if the user has a straight flash
    # list all workdays within the last 5 arrivals

    initial_date: datetime.date = user_arrivals[-1].arrival_time.date()
    valid_bizdays = []
    for i in range(14):
        logger.info(
            f"checking date: {initial_date + timedelta(days=i)}, last_date: {last_date}"
        )
        logger.info(f"- cond 1 {is_jp_bizday(initial_date + timedelta(days=i))}")
        logger.info(f"- cond 2 {initial_date + timedelta(days=i) <= last_date.date()}")

        if (
            is_jp_bizday(initial_date + timedelta(days=i))
            and initial_date + timedelta(days=i) <= last_date.date()
        ):
            valid_bizdays.append(initial_date + timedelta(days=i))
    return len(valid_bizdays) == flash_length


def _calculate_and_update_user_score(
    session: Session, user_id: str, jst_datetime: datetime
) -> None:
    arrival = (
        session.query(GuestArrivalInfo)
        .filter(GuestArrivalInfo.user_id == user_id)
        .filter(GuestArrivalInfo.arrival_time == jst_datetime)
        .one()
    )

    start_of_day = jst_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)
    # Calculate the arrival rank
    # The arrival rank is the number of users arrived on the same day + 1
    same_day_arrivals = (
        session.query(GuestArrivalInfo)
        .filter(GuestArrivalInfo.arrival_time >= start_of_day)
        .filter(GuestArrivalInfo.arrival_time < end_of_day)
        .count()
    )
    arrival_rank = same_day_arrivals

    # Determine the score based on arrival time
    time_score = get_time_score(jst_datetime)

    # add initial arrival bonus
    rank_score = 0

    # if the user arrived first and the time score is not 0
    # (thus the user arrived within the labour time), add 2 points
    if arrival_rank == 1 and time_score != 0:
        rank_score = 2

    straight_flash_score = 0
    logger.info(f"checking straight flash for {user_id}, {jst_datetime}")
    if _check_straight_flash(session, user_id, last_date=jst_datetime):
        straight_flash_score = 3

    logger.info(
        f"arrival rank: {arrival_rank}, "
        f"time score: {time_score}, "
        f"rank score: {rank_score}, "
        f"straight_flash_score: {straight_flash_score}"
    )

    # update
    arrival.arrival_rank = arrival_rank
    arrival.acquired_score_sum = time_score + rank_score + straight_flash_score
    arrival.acquired_time_score = time_score
    arrival.acquired_rank_score = rank_score
    arrival.straight_flash_score = straight_flash_score

    session.commit()


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
    if existing_arrival is not None:
        logger.info(f"existing arrival @ {existing_arrival.arrival_time}")
        return False

    # Insert the new arrival
    new_arrival = GuestArrivalInfo(
        arrival_time=jst_datetime,
        user_id=user_id,
        arrival_rank=-1,
        acquired_score_sum=-1,
        acquired_time_score=-1,
        acquired_rank_score=-1,
        straight_flash_score=-1,
    )
    session.add(new_arrival)
    session.commit()

    _calculate_and_update_user_score(session, user_id, jst_datetime)
    updated_arrival = (
        session.query(GuestArrivalInfo)
        .filter(GuestArrivalInfo.user_id == user_id)
        .filter(GuestArrivalInfo.arrival_time == jst_datetime)
        .one()
    )

    # Update user score
    user_score_entry = session.query(User).filter_by(id=user_id).one_or_none()

    # calculate_attribute
    previous_score = user_score_entry.current_score or 0 if user_score_entry else 0
    current_score = previous_score + updated_arrival.acquired_score_sum

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


def initially_insert_badge_data(session: Session) -> None:
    """Insert the badge data into the database.

    Args:
    ----
        session (Session): The session factory to interact with the database.

    """
    session.add_all(Badges)
    session.add_all(BadgeTypes)
    session.commit()
    logger.info("Badge data inserted successfully")
