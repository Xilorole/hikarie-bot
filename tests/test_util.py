import pytest

from hikarie_bot.utils import (
    LEVELS,
    Level,
    get_level,
    leveled_up,
    max_level_reached,
)

# (name, points that complete the level) written out here, independent of hikarie_bot.utils.LEVELS
EXPECTED_LEVELS = [
    ("かけだしのかいしゃいん", 20),
    ("みならいのかいしゃいん", 42),
    ("けいけんちゅうのかいしゃいん", 71),
    ("はんにんまえのかいしゃいん", 111),
    ("じしんありのかいしゃいん", 167),
    ("いちにんまえのかいしゃいん", 244),
    ("じゅくれんのかいしゃいん", 346),
    ("せんもんかのかいしゃいん", 478),
    ("たつじんのかいしゃいん", 644),
    ("エリートかいしゃいん", 849),
    ("むてきのかいしゃいん", 1098),
    ("でんせつのかいしゃいん", 1400),
]
MAX_POINT = 1400


def test_levels_table() -> None:
    """The level table is the one written out above."""
    assert list(LEVELS) == EXPECTED_LEVELS


def test_get_level_at_zero() -> None:
    """0 points is the first level, 0 of its 20 points."""
    assert get_level(0) == Level(number=1, name="かけだしのかいしゃいん", start=0, end=20, point=0)


@pytest.mark.parametrize("index", range(len(EXPECTED_LEVELS)))
def test_get_level_around_each_threshold(index: int) -> None:
    """Each level starts at the previous threshold and the last level stays at max."""
    name, threshold = EXPECTED_LEVELS[index]
    start = EXPECTED_LEVELS[index - 1][1] if index else 0
    is_last = index == len(EXPECTED_LEVELS) - 1

    # the level is completed at its threshold, which is the next level's start
    assert get_level(threshold - 1) == Level(
        number=index + 1, name=name, start=start, end=threshold, point=threshold - 1
    )
    assert get_level(start) == Level(number=index + 1, name=name, start=start, end=threshold, point=start)
    if is_last:
        assert get_level(threshold) == Level(number=12, name=name, start=start, end=threshold, point=threshold)
        assert get_level(threshold + 1).number == 12
    else:
        next_name, next_threshold = EXPECTED_LEVELS[index + 1]
        assert get_level(threshold) == Level(
            number=index + 2, name=next_name, start=threshold, end=next_threshold, point=threshold
        )
        assert get_level(threshold + 1).number == index + 2


def test_level_beyond_max() -> None:
    """Far beyond the upper limit the level is still the last one."""
    assert get_level(5000).number == 12
    assert get_level(5000).name == "でんせつのかいしゃいん"


@pytest.mark.parametrize("index", range(len(EXPECTED_LEVELS)))
def test_level_progress_around_each_threshold(index: int) -> None:
    """Points to the next level, the span and the progress within the level."""
    _, threshold = EXPECTED_LEVELS[index]
    start = EXPECTED_LEVELS[index - 1][1] if index else 0
    span = threshold - start

    first = get_level(start)
    assert (first.span, first.points_to_next, first.progress_points, first.is_max) == (span, span, 0, False)
    last = get_level(threshold - 1)
    assert (last.span, last.points_to_next, last.progress_points, last.is_max) == (span, 1, span - 1, False)

    reached = get_level(threshold)
    if index == len(EXPECTED_LEVELS) - 1:
        # at the upper limit nothing is left, the progress is the whole span of the last level (100%)
        assert (reached.span, reached.points_to_next, reached.progress_points, reached.is_max) == (span, 0, span, True)
        beyond = get_level(threshold + 100)
        assert (beyond.span, beyond.points_to_next, beyond.progress_points, beyond.is_max) == (span, 0, span, True)
    else:
        # reaching the threshold starts the next level
        assert (reached.progress_points, reached.is_max) == (0, False)
        assert reached.span == EXPECTED_LEVELS[index + 1][1] - threshold


def test_level_progress_inside_a_level() -> None:
    """Spot checks inside a level."""
    level = get_level(21)
    assert (level.points_to_next, level.span, level.progress_points) == (21, 22, 1)
    level = get_level(1399)
    assert (level.points_to_next, level.span, level.progress_points) == (1, 302, 301)


def test_leveled_up() -> None:
    """A level up is a move to a higher level; a point gain may even skip levels."""
    assert leveled_up(0, 20) is True
    assert leveled_up(19, 20) is True
    assert leveled_up(19, 21) is True
    assert leveled_up(20, 21) is False
    assert leveled_up(20, 22) is False
    assert leveled_up(21, 22) is False
    assert leveled_up(1097, 1098) is True
    assert leveled_up(0, 100) is True  # skips a level
    assert leveled_up(1000, 1500) is True  # reaches the last level and goes beyond the upper limit
    assert leveled_up(30, 20) is False  # going down is not a level up
    # reaching the upper limit is not a level up (see max_level_reached)
    assert leveled_up(1399, 1400) is False
    assert leveled_up(1390, 1405) is False
    assert leveled_up(1400, 1405) is False


@pytest.mark.parametrize("threshold", [threshold for _, threshold in EXPECTED_LEVELS[:-1]])
def test_leveled_up_at_each_threshold(threshold: int) -> None:
    """Every threshold below the upper limit is a level up when crossed."""
    assert leveled_up(threshold - 1, threshold) is True
    assert leveled_up(threshold, threshold + 1) is False
    assert leveled_up(threshold - 2, threshold - 1) is False


def test_max_level_reached() -> None:
    """The upper limit is reached once, by the gain that makes the total 1400 or more."""
    assert max_level_reached(1399, MAX_POINT) is True
    assert max_level_reached(1390, 1405) is True
    assert max_level_reached(0, 2000) is True
    assert max_level_reached(1400, 1405) is False
    assert max_level_reached(1401, 1405) is False
    assert max_level_reached(1300, 1399) is False
    assert max_level_reached(1398, 1399) is False
    assert max_level_reached(0, 0) is False
