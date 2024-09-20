import pytest

from hikarie_bot.errors import InvalidPointError
from hikarie_bot.utils import (
    get_current_level_point,
    get_level_name,
    get_point_range_to_next_level,
    get_point_to_next_level,
    is_level_uped,
    unix_timestamp_to_jst,
)


def test_get_level_name() -> None:
    "Test level names."
    assert get_level_name(0) == "かけだしのかいしゃいん"
    assert get_level_name(19) == "かけだしのかいしゃいん"
    assert get_level_name(20) == "みならいのかいしゃいん"
    assert get_level_name(41) == "みならいのかいしゃいん"
    assert get_level_name(42) == "けいけんちゅうのかいしゃいん"
    assert get_level_name(70) == "けいけんちゅうのかいしゃいん"
    assert get_level_name(71) == "はんにんまえのかいしゃいん"
    assert get_level_name(110) == "はんにんまえのかいしゃいん"
    assert get_level_name(111) == "じしんありのかいしゃいん"
    assert get_level_name(166) == "じしんありのかいしゃいん"
    assert get_level_name(167) == "いちにんまえのかいしゃいん"
    assert get_level_name(243) == "いちにんまえのかいしゃいん"
    assert get_level_name(244) == "じゅくれんのかいしゃいん"
    assert get_level_name(345) == "じゅくれんのかいしゃいん"
    assert get_level_name(346) == "せんもんかのかいしゃいん"
    assert get_level_name(477) == "せんもんかのかいしゃいん"
    assert get_level_name(478) == "たつじんのかいしゃいん"
    assert get_level_name(643) == "たつじんのかいしゃいん"
    assert get_level_name(644) == "エリートかいしゃいん"
    assert get_level_name(848) == "エリートかいしゃいん"
    assert get_level_name(849) == "むてきのかいしゃいん"
    assert get_level_name(1097) == "むてきのかいしゃいん"
    assert get_level_name(1098) == "でんせつのかいしゃいん"
    assert get_level_name(1399) == "でんせつのかいしゃいん"
    assert get_level_name(1400) == "でんせつのかいしゃいん"
    assert get_level_name(1401) == "でんせつのかいしゃいん"


def test_is_level_uped() -> None:
    """Test either level is uped or not.

    The level is uped when the previous point is lower than
    the threshold and the current point is equal or greater than
    the next level point.
    """
    assert is_level_uped(0, 20) is True
    assert is_level_uped(19, 20) is True
    assert is_level_uped(19, 21) is True
    assert is_level_uped(20, 21) is False
    assert is_level_uped(20, 22) is False
    assert is_level_uped(21, 22) is False
    # if the point is over the last level point, the level is not uped
    assert is_level_uped(1400, 1405) is False


def test_get_point_to_next_level() -> None:
    """Test the point to the next level."""
    assert get_point_to_next_level(0) == 20
    assert get_point_to_next_level(19) == 1
    assert get_point_to_next_level(20) == 22
    assert get_point_to_next_level(21) == 21
    assert get_point_to_next_level(22) == 20
    assert get_point_to_next_level(41) == 1
    assert get_point_to_next_level(42) == 29
    assert get_point_to_next_level(43) == 28
    assert get_point_to_next_level(70) == 1
    assert get_point_to_next_level(71) == 40
    assert get_point_to_next_level(110) == 1
    assert get_point_to_next_level(111) == 56
    assert get_point_to_next_level(166) == 1
    assert get_point_to_next_level(167) == 77
    assert get_point_to_next_level(243) == 1
    assert get_point_to_next_level(244) == 102
    assert get_point_to_next_level(345) == 1
    assert get_point_to_next_level(346) == 132
    assert get_point_to_next_level(477) == 1
    assert get_point_to_next_level(478) == 166
    assert get_point_to_next_level(643) == 1
    assert get_point_to_next_level(644) == 205
    assert get_point_to_next_level(848) == 1
    assert get_point_to_next_level(849) == 249
    assert get_point_to_next_level(1097) == 1
    assert get_point_to_next_level(1098) == 302
    assert get_point_to_next_level(1399) == 1
    assert get_point_to_next_level(1400) == 0
    assert get_point_to_next_level(1401) == 0


def test_get_point_range_to_next_level() -> None:
    "Assert the total amount of the point range is equal to the point to next level."
    assert get_point_range_to_next_level(0) == 20
    assert get_point_range_to_next_level(19) == 20
    assert get_point_range_to_next_level(20) == 42 - 20
    assert get_point_range_to_next_level(21) == 42 - 20
    assert get_point_range_to_next_level(22) == 42 - 20
    assert get_point_range_to_next_level(41) == 42 - 20
    assert get_point_range_to_next_level(42) == 71 - 42
    assert get_point_range_to_next_level(43) == 71 - 42
    assert get_point_range_to_next_level(70) == 71 - 42
    assert get_point_range_to_next_level(71) == 111 - 71
    assert get_point_range_to_next_level(110) == 111 - 71
    assert get_point_range_to_next_level(111) == 167 - 111
    assert get_point_range_to_next_level(166) == 167 - 111
    assert get_point_range_to_next_level(167) == 244 - 167
    assert get_point_range_to_next_level(243) == 244 - 167
    assert get_point_range_to_next_level(244) == 346 - 244
    assert get_point_range_to_next_level(345) == 346 - 244
    assert get_point_range_to_next_level(346) == 478 - 346
    assert get_point_range_to_next_level(477) == 478 - 346
    assert get_point_range_to_next_level(478) == 644 - 478
    assert get_point_range_to_next_level(643) == 644 - 478
    assert get_point_range_to_next_level(644) == 849 - 644
    assert get_point_range_to_next_level(848) == 849 - 644
    assert get_point_range_to_next_level(849) == 1098 - 849
    assert get_point_range_to_next_level(1097) == 1098 - 849
    assert get_point_range_to_next_level(1098) == 1400 - 1098
    assert get_point_range_to_next_level(1399) == 1400 - 1098
    # when the user reached the last level, the point range function raise ValueError
    with pytest.raises(InvalidPointError):
        get_point_range_to_next_level(1400)


def test_get_current_level_point() -> None:
    "test: Calculate the current level point based on the given total point."
    assert get_current_level_point(0) == 0
    assert get_current_level_point(19) == 19
    assert get_current_level_point(20) == 20 - 20
    assert get_current_level_point(21) == 21 - 20
    assert get_current_level_point(22) == 22 - 20
    assert get_current_level_point(41) == 41 - 20
    assert get_current_level_point(42) == 42 - 42
    assert get_current_level_point(43) == 43 - 42
    assert get_current_level_point(70) == 70 - 42
    assert get_current_level_point(71) == 71 - 71
    assert get_current_level_point(110) == 110 - 71
    assert get_current_level_point(111) == 111 - 111
    assert get_current_level_point(166) == 166 - 111
    assert get_current_level_point(167) == 167 - 167
    assert get_current_level_point(243) == 243 - 167
    assert get_current_level_point(244) == 244 - 244
    assert get_current_level_point(345) == 345 - 244
    assert get_current_level_point(346) == 346 - 346
    assert get_current_level_point(477) == 477 - 346
    assert get_current_level_point(478) == 478 - 478
    assert get_current_level_point(643) == 643 - 478
    assert get_current_level_point(644) == 644 - 644
    assert get_current_level_point(848) == 848 - 644
    assert get_current_level_point(849) == 849 - 849
    assert get_current_level_point(1097) == 1097 - 849
    assert get_current_level_point(1098) == 1098 - 1098
    assert get_current_level_point(1399) == 1399 - 1098
    # when the user reached the last level, the point range function raise ValueError
    with pytest.raises(InvalidPointError):
        get_current_level_point(1400)


def test_unix_timestamp_to_jst() -> None:
    "Test the conversion of Unix timestamp to JST."
    # test: Convert a Unix timestamp to a string representing the date and time in
    # Japan Standard Time (JST).
    # this Returns:
    #     datetime: A datetime object representing the date and time in JST.
    assert (
        unix_timestamp_to_jst(0).strftime("%Y-%m-%d %H:%M:%S") == "1970-01-01 09:00:00"
    )
