from datetime import datetime, timedelta

from loguru import logger
from sqlalchemy import func, update
from sqlalchemy.orm import Session

from hikarie_bot.constants import BADGE_TYPES_TO_CHECK
from hikarie_bot.db_data.badges import BadgeChecker
from hikarie_bot.exceptions import (
    AchievementAlreadyRegisteredError,
    UserArrivalNotFoundError,
)

from . import db_data
from .models import (
    Achievement,
    Badge,
    BadgeType,
    GuestArrivalInfo,
    GuestArrivalRaw,
    User,
    UserBadge,
)
from .utils import (
    get_current_level_point,
    get_level,
    get_level_name,
    get_point_range_to_next_level,
    get_point_to_next_level,
    is_level_uped,
)


def _update_achievements(session: Session, arrival_id: int) -> None:
    """_summary_.

    Parameters
    ----------
    session : Session
        _description_
    user_id : str
        _description_
    jst_datetime : datetime
        _description_
    arrival_id : int
        _description_
    """
    # initially check whether user has already achieved the badge
    achievements = (
        session.query(Achievement).filter(Achievement.arrival_id == arrival_id).all()
    )
    if achievements:
        logger.error("User has already achieved the badge")
        raise AchievementAlreadyRegisteredError

    user_arrival = (
        session.query(GuestArrivalInfo)
        .filter(GuestArrivalInfo.id == arrival_id)
        .one_or_none()
    )

    if user_arrival is None:
        logger.error(f"User arrival not found for arrival_id: {arrival_id}")
        raise UserArrivalNotFoundError(arrival_id)

    user_id, jst_datetime = user_arrival.user_id, user_arrival.arrival_time

    checker = BadgeChecker(badge_type_to_check=BADGE_TYPES_TO_CHECK)
    achieved_badges = checker.check(session, user_id, jst_datetime)

    for badge in achieved_badges:
        session.add(
            Achievement(
                user_id=user_id,
                arrival_id=arrival_id,
                badge_id=badge.id,
                achieved_time=jst_datetime,
            )
        )
        user_badge = (
            session.query(UserBadge)
            .filter(UserBadge.user_id == user_id, UserBadge.badge_id == badge.id)
            .one_or_none()
        )
        if user_badge is None:
            session.add(
                UserBadge(
                    user_id=user_id,
                    badge_id=badge.id,
                    initially_acquired_datetime=jst_datetime,
                    last_acquired_datetime=jst_datetime,
                    count=1,
                )
            )
        else:
            user_badge.count += 1
            user_badge.last_acquired_datetime = jst_datetime
    session.commit()


def _update_arrival_rank(session: Session, arrival_id: int) -> None:
    """
    Calculate and update the user's rank based on their arrival information.

    Parameters
    ----------
    session : Session
        The session factory to interact with the database.
    arrival_id : int
        The ID of the arrival record.

    Returns
    -------
    None
    """
    user_arrival = (
        session.query(GuestArrivalInfo)
        .filter(GuestArrivalInfo.id == arrival_id)
        .one_or_none()
    )
    if user_arrival is None:
        logger.error(f"User arrival not found for arrival_id: {arrival_id}")
        raise UserArrivalNotFoundError(arrival_id)

    today = user_arrival.arrival_time.date()
    start_of_day = datetime.combine(today, datetime.min.time())

    # calculate the arrivals within the same day
    arrivals_count = (
        session.query(GuestArrivalInfo)
        .filter(
            GuestArrivalInfo.arrival_time >= start_of_day,
            GuestArrivalInfo.arrival_time < user_arrival.arrival_time,
        )
        .count()
    )
    user_arrival.arrival_rank = arrivals_count + 1

    session.commit()


def _update_acquired_score_sum(session: Session, arrival_id: int) -> None:
    """
    Calculate and update the user's score based on their arrival information.

    Parameters
    ----------
    session : Session
        The session factory to interact with the database.
    arrival_id : int
        The ID of the arrival record.

    Returns
    -------
    None
    """
    acquired_score_sum = (
        session.query(func.sum(Badge.score))
        .join(Achievement, Achievement.badge_id == Badge.id)
        .filter(Achievement.arrival_id == arrival_id)
        .scalar()
    ) or 0

    logger.info(f"acquired_score_sum: {acquired_score_sum}")
    session.execute(
        update(GuestArrivalInfo)
        .where(GuestArrivalInfo.id == arrival_id)
        .values(acquired_score_sum=acquired_score_sum)
    )

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
    )
    session.add(new_arrival)
    session.commit()
    logger.info(f"new arrival @ {new_arrival.arrival_time} id: {new_arrival.id}")

    _update_arrival_rank(session, new_arrival.id)
    _update_achievements(session, new_arrival.id)
    _update_acquired_score_sum(session, new_arrival.id)
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
    if session.query(Badge).count() > 0:
        logger.info("Badge data already exists")
    else:
        session.add_all(
            Badge(
                id=badge.id,
                message=badge.message,
                condition=badge.condition,
                level=badge.level,
                score=badge.score,
                badge_type_id=badge.badge_type_id,
            )
            for badge in db_data.Badges
        )
        logger.info("Badge data inserted successfully")

    if session.query(BadgeType).count() > 0:
        logger.info("Badge Type data already exists")
    else:
        session.add_all(
            BadgeType(
                id=badge_type.id,
                name=badge_type.name,
                description=badge_type.description,
                apply_start=badge_type.apply_start,
            )
            for badge_type in db_data.BadgeTypes
        )
        logger.info("Badge Type data inserted successfully")
    session.commit()
    logger.info("inserted successfully")
