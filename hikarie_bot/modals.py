import json
import re
from collections.abc import Mapping
from datetime import date, timedelta
from textwrap import dedent

from slack_sdk.models.blocks import (
    Block,
    basic_components,
    block_elements,
    blocks,
)

from hikarie_bot import db_data
from hikarie_bot.constants import (
    ACHIEVED_BADGE_IMAGE_URL,
    NOT_ACHIEVED_BADGE_IMAGE_URL,
)
from hikarie_bot.db_data.badges import BadgeTypeData
from hikarie_bot.db_data.items import ID_CARD, ITEM_IMAGE_URLS, ITEMS, ItemData
from hikarie_bot.engine import (
    STRAIGHT_FLASH,
    STRAIGHT_FLASH_LENGTH,
    TEAM_GOAL_BADGE,
    ArrivalResult,
    BadgeEngine,
    ItemEffect,
    Outlook,
    TeamProgress,
)
from hikarie_bot.utils import (
    get_level,
    leveled_up,
    max_level_reached,
)

# Constants
KIRIBAN_BADGE_TYPE_ID = 6
BADGES = {badge.id: badge for badge in db_data.Badges}
BADGES_BY_TYPE = {
    badge_type.id: [badge for badge in db_data.Badges if badge.badge_type_id == badge_type.id]
    for badge_type in db_data.BadgeTypes
}


def badge_types_to_show() -> list[BadgeTypeData]:
    """Return the badge types the bot awards, in ID order."""
    return [badge_type for badge_type in db_data.BadgeTypes if badge_type.id in BadgeEngine.CHECKERS]


class ActionID:
    """Class for storing the action IDs used in the Slack app."""

    ARRIVED_OFFICE = "ARRIVED_OFFICE"
    FASTEST_ARRIVAL = "FASTEST_ARRIVAL"
    CHECK_ACHIEVEMENT = "CHECK_ACHIEVEMENT"  # the status button of daily posts from before the Home
    OPEN_MY_PAGE = "OPEN_MY_PAGE"
    PICK_ITEM = "PICK_ITEM"
    ITEM_CHOICE = "ITEM_CHOICE"


class BlockID:
    """Class for storing the block IDs used in the Slack app."""

    FASTEST_ARRIVAL = "FASTEST_ARRIVAL"
    ARRIVED_OFFICE = "ARRIVED_OFFICE"
    ITEM_CHOICE = "ITEM_CHOICE"


class CallbackID:
    """Class for storing the callback IDs of the modals that are submitted."""

    ITEM_PICK = "ITEM_PICK"
    ITEM_REVIEW = "ITEM_REVIEW"


class ShortcutID:
    """Class for storing the shortcut IDs used in the Slack app."""

    REBOOT = "reboot"  # only small letters are allowed
    ARRIVE = "arrive"  # the global shortcut that records an arrival from anywhere in Slack


def render(message: list[Block]) -> list[dict]:
    """Render the blocks of a message to the dictionaries Slack takes."""
    return [block.to_dict() for block in message]


def to_text(message: list[Block]) -> str:
    """Return the text of the message's sections, as the fallback text of the post."""
    return "\n".join(block.text.text for block in message if isinstance(block, blocks.SectionBlock))


def team_text(team: TeamProgress) -> str:
    """Describe everyone's arrivals this week against the goal, and what reaching it gives."""
    bonus = f"+{BADGES[TEAM_GOAL_BADGE].score}pt"
    if team.reached:
        return f"今週のみんなの出社 *{team.count}* / {team.goal}回。達成したので、今週これからの出社は {bonus}"
    return f"今週のみんなの出社 *{team.count}* / {team.goal}回。届いたら、そのあとの出社は {bonus}"


def _team_context(team: TeamProgress | None) -> list[Block]:
    return (
        []
        if team is None
        else [blocks.ContextBlock(elements=[basic_components.MarkdownTextObject(text=team_text(team))])]
    )


def home_url(team_id: str, app_id: str) -> str | None:
    """Return the deep link that opens the app's Home tab, or None without both IDs."""
    return f"slack://app?team={team_id}&id={app_id}&tab=home" if team_id and app_id else None


def _my_page_button(url: str | None) -> list[block_elements.ButtonElement]:
    """Return the button that opens my page on the Home, or none without a link to the Home."""
    return (
        []
        if url is None
        else [block_elements.ButtonElement(text="マイページを開く", action_id=ActionID.OPEN_MY_PAGE, url=url)]
    )


def initial_message(team: TeamProgress | None = None, my_page_url: str | None = None) -> list[Block]:
    """Build the daily question with its buttons, and the week's team progress once the team goal applies."""
    return [
        blocks.SectionBlock(text="高輪に出社してる？"),
        blocks.ActionsBlock(
            elements=[
                block_elements.ButtonElement(text="最速出社した", action_id=ActionID.FASTEST_ARRIVAL, style="primary"),
                *_my_page_button(my_page_url),
                block_elements.ButtonElement(text="今日のアイテム", action_id=ActionID.PICK_ITEM),
            ],
            block_id=BlockID.FASTEST_ARRIVAL,
        ),
        *_team_context(team),
    ]


def registry_message(
    arrivals: list[ArrivalResult], team: TeamProgress | None = None, my_page_url: str | None = None
) -> list[Block]:
    """Build the question with its buttons, the day's arrivals in time order and the week's team progress."""
    return [
        blocks.SectionBlock(text="高輪に出社してる？"),
        blocks.ActionsBlock(
            elements=[
                block_elements.ButtonElement(text="出社した", action_id=ActionID.ARRIVED_OFFICE),
                *_my_page_button(my_page_url),
                block_elements.ButtonElement(text="今日のアイテム", action_id=ActionID.PICK_ITEM),
            ],
            block_id=BlockID.ARRIVED_OFFICE,
        ),
        blocks.DividerBlock(),
        blocks.SectionBlock(
            text="本日の出社ユーザー:\n"
            + "\n".join(f"*{arrival.time:%H:%M}* : <@{arrival.user_id}>{_id_card(arrival)}" for arrival in arrivals),
        ),
        *_team_context(team),
    ]


def _id_card(arrival: ArrivalResult) -> str:
    """Return the ID card shown after the user while their ID card item acts."""
    return f" {ITEMS[ID_CARD].emoji}" if any(effect.item_id == ID_CARD for effect in arrival.item_effects) else ""


def outlook_lines(outlook: Outlook) -> list[str]:
    """Describe what the user can reach next, each as "<target>まで あと N".

    Only what the user's own arrivals move: the straight flash and the next count badge (a kiriban is
    luck, and the badge list shows it).
    """
    lines = []
    # from two days in a row, or one before today's arrival (arriving today makes two)
    started = outlook.streak >= 2 or (outlook.streak == 1 and outlook.streak_pending)  # noqa: PLR2004
    if started and outlook.streak < STRAIGHT_FLASH_LENGTH:
        to_go = STRAIGHT_FLASH_LENGTH - outlook.streak
        lines.append(f"{BADGES[STRAIGHT_FLASH].message}まで あと{to_go}日（{outlook.streak}日連続）")
    if outlook.next_count_badge:
        badge_id, to_go = outlook.next_count_badge
        lines.append(f"「{BADGES[badge_id].message}」まで あと{to_go}回")
    return lines


def goals_text(outlook: Outlook) -> str:
    """Describe what to aim for next and the week's team progress, one per line (empty if nothing)."""
    lines = outlook_lines(outlook)
    if outlook.team is not None:
        lines.append(team_text(outlook.team))
    return "\n".join(lines)


def goals_message(outlook: Outlook) -> list[Block]:
    """Build the ephemeral message that tells the user, right after their arrival, what to aim for next."""
    text = goals_text(outlook)
    return [blocks.SectionBlock(text=f"*つぎのもくひょう*\n{text}")] if text else []


def arrival_summary(arrival: ArrivalResult, outlook: Outlook | None, channel_id: str) -> str:
    """Describe a registered arrival: its time and points, where it is recorded, and what to aim for next."""
    text = (
        f"*{arrival.time:%H:%M}* に出社登録しました（+{arrival.score_sum}pt）。"
        f"<#{channel_id}> の今日の投稿のスレッドに記録しています"
    )
    if outlook is not None and (goals := goals_text(outlook)):
        text += f"\n\n*つぎのもくひょう*\n{goals}"
    return text


def point_get_message(arrival: ArrivalResult) -> list[Block]:
    """Build the message announcing a counted arrival, its points and its level."""
    level = get_level(arrival.current_score)

    experience_rate = int(100 * level.progress_points / level.span)
    experience_add_up_rate = int(100 * arrival.score_sum / level.span)
    point_rate_text = _progress_bar(experience_rate)

    # the level does not go beyond the upper limit
    if level.is_max:
        next_level_text = "*上限に到達*"
        progress_text = f"`{point_rate_text}` | *100%*"
    else:
        next_level_text = f"*{level.points_to_next}pt*"
        progress_text = f"`{point_rate_text}` | *{experience_rate:>3d}%* (*+{experience_add_up_rate}%*)"
    if max_level_reached(arrival.previous_score, arrival.current_score):
        level_up_text = " *上限に到達!* :crown: "
    elif leveled_up(arrival.previous_score, arrival.current_score):
        level_up_text = " *LvUP!* :star2: "
    else:
        level_up_text = ""

    is_first = arrival.rank == 1
    badges = [BADGES[badge_id] for badge_id in sorted(arrival.badge_ids)]
    achievements_text = "\n".join(
        [f" - {badge.message}:*+{badge.score}pt*" for badge in badges]
        + [f" - {_item_effect_text(effect)}:*+{effect.points}pt*" for effect in arrival.item_effects if effect.points]
    )
    context = (
        dedent(
            f"""\
            かたがき: *{level.name}* (Lv{level.number})
            つぎのレベルまで: {next_level_text}
            しんこうど: {progress_text}
            うちわけ:
            """
        )
        + achievements_text
    )

    return [
        blocks.SectionBlock(
            text=f"*{arrival.time:%H:%M}* "
            f"{'最速' if is_first else ''}出社登録しました！"
            f"\n<@{arrival.user_id}>さんのポイント "
            f"{arrival.previous_score} → *{arrival.current_score}* "
            f"(*+{arrival.score_sum}*){level_up_text}"
        ),
        blocks.DividerBlock(),
        blocks.ContextBlock(elements=[basic_components.MarkdownTextObject(text=context)]),
        blocks.DividerBlock(),
    ]


def _item_effect_text(effect: ItemEffect) -> str:
    """Return what gave an item's points: the item, and whose treat it was."""
    item = ITEMS[effect.item_id]
    return f"{item.name} (<@{effect.giver}>さんから)" if effect.giver else item.name


ITEM_PICK_GUIDE = (
    "1つだけ獲得できます。効果は次の出社から。持てるアイテムは1つまでで、"
    "アイテムによる加点は1回の出社につき最大 +3pt です。"
)


ITEM_TITLE = "今日のアイテム"


def item_pick_view(
    offered: list[ItemData], channel_id: str, thread_ts: str, day: date, image_urls: Mapping[str, str] = ITEM_IMAGE_URLS
) -> dict:
    """Build the modal offering today's items as the collection shows them, picked with a radio button and submitted.

    Submitting closes the modal (a button inside a modal cannot). The pick goes under the daily post (channel and
    thread in the private metadata) on the day the modal opened.
    """
    return {
        "type": "modal",
        "callback_id": CallbackID.ITEM_PICK,
        "title": _plain(ITEM_TITLE),
        "submit": _plain("獲得"),
        "close": _plain("やめる"),
        "private_metadata": json.dumps({"channel": channel_id, "thread_ts": thread_ts, "day": day.isoformat()}),
        "blocks": [
            {"type": "section", "text": _mrkdwn(ITEM_PICK_GUIDE)},
            {"type": "divider"},
            *divided([[offered_item(item, image_urls.get(item.id))] for item in offered]),
            {"type": "divider"},
            {
                "type": "input",
                "block_id": BlockID.ITEM_CHOICE,
                "label": _plain("獲得するアイテム"),
                "element": {
                    "type": "radio_buttons",
                    "action_id": ActionID.ITEM_CHOICE,
                    "options": [{"text": _mrkdwn(f"*{item.name}*"), "value": item.id} for item in offered],
                },
            },
        ],
    }


def item_review_view(
    offered: list[ItemData],
    notice: str,
    picked_item_id: str | None = None,
    image_urls: Mapping[str, str] = ITEM_IMAGE_URLS,
) -> dict:
    """Build the read-only modal of today's items: before the arrival, after the pick, or while an item is held.

    After a pick, the picked item comes first as usual and the others follow in small grey text, so it stands out
    without a label. It has no inputs, so it needs no submit button: "閉じる" is its only button. (Block Kit Builder's
    "Send to Slack" adds a submit button to every modal; views.open does not.)
    """
    return {
        "type": "modal",
        "callback_id": CallbackID.ITEM_REVIEW,
        "title": _plain(ITEM_TITLE),
        "close": _plain("閉じる"),
        "blocks": [
            {"type": "section", "text": _mrkdwn(notice)},
            {"type": "divider"},
            *divided(
                [
                    offered_item_blocks(item, image_urls.get(item.id), dimmed=picked_item_id not in {None, item.id})
                    # the picked one first; sorted keeps the offers' order otherwise
                    for item in sorted(offered, key=lambda item: item.id != picked_item_id)
                ]
            ),
            {"type": "divider"},
            {"type": "context", "elements": [_mrkdwn("アイテムは1日1つまで。出社した日に選べます。")]},
        ],
    }


def item_section(name: str, effect: str, story: str | None, image_url: str | None, alt_text: str) -> dict:
    """Return an item as the collection and the item modals show it: name and effect beside a large image.

    The collection adds the story below as an italic block quote; the modals leave it out. Cards were dropped: they
    render narrow on a desktop Home and stack up in a modal.
    """
    text = f"{name}\n効果: {effect}" + (f"\n>_{story}_" if story is not None else "")
    block = {"type": "section", "text": _mrkdwn(text)}
    if image_url:  # an item whose image is not hosted yet has no image
        block["accessory"] = {"type": "image", "image_url": image_url, "alt_text": alt_text}
    return block


def offered_item(item: ItemData, image_url: str | None) -> dict:
    """Return an offered item without its story: its name and effect beside its image."""
    return item_section(f"*{item.name}*", item.effect, None, image_url, item.name)


def offered_item_blocks(item: ItemData, image_url: str | None, *, dimmed: bool = False) -> list[dict]:
    """Return an offered item's blocks: as usual, or dimmed (an offer not picked) into small grey text.

    Dimmed, it is two context blocks, the small image with the name and then the effect: one context block
    with both would wrap the effect beside the image.
    """
    if not dimmed:
        return [offered_item(item, image_url)]
    image = [{"type": "image", "image_url": image_url, "alt_text": item.name}] if image_url else []
    return [
        {"type": "context", "elements": [*image, _mrkdwn(f"*{item.name}*")]},
        {"type": "context", "elements": [_mrkdwn(f"効果: {item.effect}")]},
    ]


def divided(items: list[list[dict]]) -> list[dict]:
    """Put a divider between items, each given as its blocks."""
    return [block for index, item in enumerate(items) for block in ([{"type": "divider"}] if index else []) + item]


def _plain(text: str) -> dict:
    return {"type": "plain_text", "text": text}


def _mrkdwn(text: str) -> dict:
    return {"type": "mrkdwn", "text": text}


def notice_view(text: str, title: str = "出社登録") -> dict:
    """Build a modal that only shows a message (the reply to the arrival shortcut, or a refusal from the Home)."""
    return {
        "type": "modal",
        "title": _plain(title),
        "close": _plain("閉じる"),
        "blocks": [{"type": "section", "text": _mrkdwn(text)}],
    }


def item_picked_text(user_id: str, item: ItemData) -> str:
    """Return the announcement of a pick, kept small: one line in the thread, without the effect.

    What an item does is for the picker's modals and the collection, not for the channel.
    """
    return f"<@{user_id}>さんが {item.name} を獲得しました"


def item_picked_message(user_id: str, item: ItemData) -> list[Block]:
    """Build the thread post announcing a pick as one line of small text."""
    return [blocks.ContextBlock(elements=[basic_components.MarkdownTextObject(text=item_picked_text(user_id, item))])]


def _progress_bar(rate: int) -> str:
    """Return a 10-cell bar for a percentage, with at least one cell (a bar of spaces renders as empty code)."""
    digits = max(1, (rate + 10 - 1) // 10)
    return "█" * digits + " " * (10 - digits)


_INLINE = re.compile(r"\*([^*]+)\*|`([^`]+)`")


def _rich_text(text: str) -> list[dict]:
    """Turn a line with *bold* and `code` spans into rich text elements."""
    elements: list[dict] = []
    position = 0
    for match in _INLINE.finditer(text):
        if match.start() > position:
            elements.append({"type": "text", "text": text[position : match.start()]})
        bold, code = match.groups()
        style = {"bold": True} if bold is not None else {"code": True}
        elements.append({"type": "text", "text": bold if bold is not None else code, "style": style})
        position = match.end()
    if position < len(text):
        elements.append({"type": "text", "text": text[position:]})
    return elements


def bullet_list(items: list[tuple[str, int]]) -> dict:
    """Return a rich text block listing (line, indent) items as bullets; a line may hold *bold* and `code`."""
    return {
        "type": "rich_text",
        "elements": [
            {
                "type": "rich_text_list",
                "style": "bullet",
                "indent": indent,
                "elements": [{"type": "rich_text_section", "elements": _rich_text(line)}],
            }
            for line, indent in items
        ],
    }


def attendance_by_day(engine: BadgeEngine, user_id: str, today: date) -> dict[date, bool]:
    """Return whether the user arrived, for each weekday of the past 10 weeks up to today."""
    # from the Monday 9 weeks back (this week included) to today
    start_monday = today - timedelta(days=today.weekday(), weeks=9)
    days = (start_monday + timedelta(days=offset) for offset in range((today - start_monday).days + 1))
    user = engine.users.get(user_id)
    arrival_dates = {time.date() for time in user.times} if user else set()
    return {day: day in arrival_dates for day in days if day.weekday() < 5}  # noqa: PLR2004


def attendance_history_blocks(attendance: dict[date, bool]) -> list[Block]:
    """Build the attendance history: one row of up to 10 weeks per weekday, like a GitHub activity graph."""
    rows = [
        [
            _icon(f"{day:%m/%d} {'出社' if attended else '未出社'}", achieved=attended)
            for day, attended in attendance.items()
            if day.weekday() == weekday
        ]
        for weekday in range(5)
    ]
    return [blocks.HeaderBlock(text="過去の出社履歴"), *(blocks.ContextBlock(elements=row) for row in rows)]


def _icon(alt_text: str, *, achieved: bool) -> block_elements.ImageElement:
    """Return the image of an achieved (or attended) or an unachieved (or missed) item."""
    url = ACHIEVED_BADGE_IMAGE_URL if achieved else NOT_ACHIEVED_BADGE_IMAGE_URL
    return block_elements.ImageElement(image_url=url, alt_text=alt_text)
