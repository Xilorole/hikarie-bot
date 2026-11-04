import re
from collections import Counter
from datetime import datetime

import pytest

from hikarie_bot.constants import JST
from hikarie_bot.engine import BadgeEngine
from hikarie_bot.home import HOME_BLOCK_MAX, HomeActionID, HomeTab, home_view, ranking
from hikarie_bot.preview import build_synthetic_context


@pytest.mark.parametrize("tab", list(HomeTab.LABELS))
def test_every_tab_renders_within_the_block_limit(tab: str) -> None:
    """Each tab is a Home view led by the tab bar, with the selected tab highlighted."""
    context = build_synthetic_context()
    view = home_view(context.engine, context.user_id, context.reference.replace(hour=12), tab)

    assert view["type"] == "home"
    assert len(view["blocks"]) <= HOME_BLOCK_MAX
    selected = [button["action_id"] for button in view["blocks"][0]["elements"] if button.get("style") == "primary"]
    assert selected == [tab]


def test_my_page_offers_the_arrival_and_item_buttons_before_arriving() -> None:
    """A user who has not arrived on a business day gets the buttons to register and to look at the items."""
    view = home_view(BadgeEngine(), "U0NEW", datetime(2025, 5, 7, 9, tzinfo=JST))

    actions = [
        element["action_id"]
        for block in view["blocks"][1:]
        if block["type"] == "actions"
        for element in block["elements"]
    ]
    assert HomeActionID.ARRIVE in actions
    assert HomeActionID.PICK_ITEM in actions  # the day's items can be looked at before arriving


def test_ranking_shares_ranks_on_ties_and_keeps_the_user_below_the_top() -> None:
    """Equal totals share a rank and the next one skips; a user below the top five gets their own entry."""
    totals = Counter({"U1": 5, "U2": 5, "U3": 4, "U4": 3, "U5": 2, "U6": 1, "U7": 1, "U8": 0})
    board = ranking("出社回数", totals, "U8", "回")

    assert [(entry.rank, entry.user_id) for entry in board.top] == [
        (1, "U1"),
        (1, "U2"),
        (3, "U3"),
        (4, "U4"),
        (5, "U5"),
    ]
    assert board.own is not None
    assert (board.own.rank, board.own.value) == (8, 0)


def _mrkdwn_texts(node: object) -> list[str]:
    if isinstance(node, dict):
        own = [node["text"]] if node.get("type") == "mrkdwn" else []
        return own + [text for value in node.values() for text in _mrkdwn_texts(value)]
    if isinstance(node, list):
        return [text for value in node for text in _mrkdwn_texts(value)]
    return []


@pytest.mark.parametrize("tab", list(HomeTab.LABELS))
def test_bold_spans_stand_apart_from_the_text_around_them(tab: str) -> None:
    """Slack makes *text* bold only with a space (or the line's edge) on both sides, even next to Japanese text."""
    context = build_synthetic_context()
    view = home_view(context.engine, context.user_id, context.reference.replace(hour=12), tab)

    for text in _mrkdwn_texts(view):
        for line in text.split("\n"):
            for match in re.finditer(r"\*[^*]+\*", line):
                assert match.start() == 0 or line[match.start() - 1].isspace(), line
                assert match.end() == len(line) or line[match.end()].isspace(), line


def test_ranking_tab_writes_each_ranking_as_a_table() -> None:
    """The three rankings are tables of place, user and value, medals for the top three."""
    context = build_synthetic_context()
    view = home_view(context.engine, context.user_id, context.reference.replace(hour=12), HomeTab.RANKING)

    tables = [block for block in view["blocks"] if block["type"] == "table"]
    assert len(tables) == 3
    first_place = tables[0]["rows"][0][0]["elements"][0]["elements"][0]["text"]
    assert first_place == "\N{FIRST PLACE MEDAL}"
