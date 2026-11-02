from datetime import datetime
from unittest.mock import patch

from hikarie_bot.engine import JST
from hikarie_bot.utils import get_level, get_level_name, is_level_uped, is_max_level_reached
from tests.helpers import compute_in_order


# only the fastest-arrival and time-window badges
@patch("hikarie_bot.engine.BADGE_TYPES_TO_CHECK", [2, 5])
def test_only_the_first_arrival_of_the_day_scores() -> None:
    """A second arrival on the same day earns nothing."""
    engine = compute_in_order(
        ("test_user", datetime(2024, 1, 1, 6, 0, tzinfo=JST)), ("test_user", datetime(2024, 1, 1, 7, 0, tzinfo=JST))
    )

    assert [(result.user_id, result.previous_score, result.current_score) for result in engine.results] == [
        ("test_user", 0, 7)
    ]


def test_rank_follows_the_time_of_day() -> None:
    """Ranks count the earlier arrivals of the same day, whichever order they were recorded in."""
    engine = compute_in_order(
        ("1st", datetime(2024, 1, 1, 6, 0, tzinfo=JST)),
        ("2nd", datetime(2024, 1, 1, 6, 1, tzinfo=JST)),
        ("1st", datetime(2024, 1, 1, 5, 0, tzinfo=JST)),
        ("1st", datetime(2024, 1, 2, 7, 0, tzinfo=JST)),
    )

    assert [(result.user_id, result.time.day, result.rank) for result in engine.results] == [
        ("1st", 1, 1),
        ("2nd", 1, 2),
        ("1st", 2, 1),
    ]


@patch("hikarie_bot.engine.BADGE_TYPES_TO_CHECK", [2, 5])
def test_second_arrived_user_has_lower_point() -> None:
    """The fastest badge goes only to the first arrival of the day."""
    engine = compute_in_order(
        ("1st", datetime(2024, 1, 1, 6, 0, tzinfo=JST)), ("2nd", datetime(2024, 1, 1, 7, 0, tzinfo=JST))
    )

    assert {user_id: user.score for user_id, user in engine.users.items()} == {"1st": 7, "2nd": 3}


@patch("hikarie_bot.engine.BADGE_TYPES_TO_CHECK", [2, 5])
def test_level_up() -> None:
    """Scores accumulate across days and cross the level threshold."""
    engine = compute_in_order(*(("test_user", datetime(2024, 2, day, 7, 0, tzinfo=JST)) for day in range(1, 5)))

    last = engine.results[-1]
    assert (last.previous_score, last.current_score) == (15, 20)
    assert is_level_uped(last.previous_score, last.current_score)
    assert (get_level(last.current_score), get_level_name(last.current_score)) == (2, "みならいのかいしゃいん")


# only the fastest-arrival badge, worth 701pt, so three arrivals cross the 1400pt upper limit
@patch("hikarie_bot.engine.BADGE_TYPES_TO_CHECK", [2])
@patch.dict("hikarie_bot.engine.BADGE_SCORES", {201: 701})
def test_reach_max_level() -> None:
    """The score beyond the upper limit is kept and the level stays at max."""
    engine = compute_in_order(*(("test_user", datetime(2024, 2, day, 7, 0, tzinfo=JST)) for day in (1, 2, 5)))

    reached, beyond = engine.results[1], engine.results[2]
    assert is_max_level_reached(reached.previous_score, reached.current_score)
    assert beyond.current_score > beyond.previous_score > 1400
    assert get_level(beyond.current_score) == 12
    assert not is_level_uped(beyond.previous_score, beyond.current_score)
