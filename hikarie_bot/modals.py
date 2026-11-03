import json
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from itertools import batched
from textwrap import dedent

from slack_sdk.models.blocks import (
    Block,
    basic_components,
    block_elements,
    blocks,
)
from slack_sdk.models.views import View

from hikarie_bot import db_data
from hikarie_bot.constants import (
    ACHIEVED_BADGE_IMAGE_URL,
    CONTEXT_ITEM_MAX,
    JST,
    NOT_ACHIEVED_BADGE_IMAGE_URL,
)
from hikarie_bot.db_data.badges import KIRIBANS, BadgeData, BadgeTypeData, Kiriban
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
    UserBadgeTally,
)
from hikarie_bot.utils import (
    get_level,
    leveled_up,
    max_level_reached,
)

# Constants
KIRIBAN_BADGE_TYPE_ID = 6
WELCOME_BADGE = 101
LONG_TIME_NO_SEE_BADGES = {701, 702, 703, 704}
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
    CHECK_ACHIEVEMENT = "CHECK_ACHIEVEMENT"
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
    """Describe everyone's arrivals this week against the goal."""
    bonus = f"+{BADGES[TEAM_GOAL_BADGE].score}pt"
    if team.reached:
        return f":tada: 今週のみんなの出社: *{team.count}* / {team.goal}回 達成！ 今週これからの出社は {bonus}"
    return f":busts_in_silhouette: 今週のみんなの出社: *{team.count}* / {team.goal}回 (達成したあとの出社は {bonus})"


def _team_context(team: TeamProgress | None) -> list[Block]:
    return (
        []
        if team is None
        else [blocks.ContextBlock(elements=[basic_components.MarkdownTextObject(text=team_text(team))])]
    )


def initial_message(team: TeamProgress | None = None) -> list[Block]:
    """Build the daily question with its buttons, and the week's team progress once the team goal applies."""
    return [
        blocks.SectionBlock(text="高輪に出社してる？"),
        blocks.ActionsBlock(
            elements=[
                block_elements.ButtonElement(text="最速出社した", action_id=ActionID.FASTEST_ARRIVAL, style="primary"),
                block_elements.ButtonElement(text="実績を確認", action_id=ActionID.CHECK_ACHIEVEMENT),
                block_elements.ButtonElement(text="今日のアイテム", action_id=ActionID.PICK_ITEM),
            ],
            block_id=BlockID.FASTEST_ARRIVAL,
        ),
        *_team_context(team),
    ]


def registry_message(arrivals: list[ArrivalResult], team: TeamProgress | None = None) -> list[Block]:
    """Build the question with its buttons, the day's arrivals in time order and the week's team progress."""
    return [
        blocks.SectionBlock(text="高輪に出社してる？"),
        blocks.ActionsBlock(
            elements=[
                block_elements.ButtonElement(text="出社した", action_id=ActionID.ARRIVED_OFFICE),
                block_elements.ButtonElement(text="実績を確認", action_id=ActionID.CHECK_ACHIEVEMENT),
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


def should_broadcast(arrival: ArrivalResult, outlook: Outlook | None = None) -> bool:
    """Whether the announcement also goes to the channel, not only the thread.

    Kept to moments worth the channel's attention: the day's first, a first arrival ever, a comeback, a level
    up and the arrival that reached the week's team goal.
    """
    badges = set(arrival.badge_ids)
    team = outlook.team if outlook else None
    return (
        arrival.rank == 1
        or WELCOME_BADGE in badges
        or bool(badges & LONG_TIME_NO_SEE_BADGES)
        or leveled_up(arrival.previous_score, arrival.current_score)
        or max_level_reached(arrival.previous_score, arrival.current_score)
        or (team is not None and TEAM_GOAL_BADGE in badges and team.count == team.goal)
    )


def outlook_lines(outlook: Outlook) -> list[str]:
    """Describe what the user can aim for next: the streak, the next count badge, the next kiriban."""
    lines = []
    if outlook.streak >= 2:  # noqa: PLR2004
        streak = f"連続出社 *{outlook.streak}日目*"
        if outlook.streak < STRAIGHT_FLASH_LENGTH:
            to_go = STRAIGHT_FLASH_LENGTH - outlook.streak
            streak += f" (あと{to_go}日で{BADGES[STRAIGHT_FLASH].message})"
        lines.append(streak)
    if outlook.next_count_badge:
        badge_id, to_go = outlook.next_count_badge
        lines.append(f"あと *{to_go}回* の出社で「{BADGES[badge_id].message}」")
    if outlook.next_kiriban:
        number, to_go = outlook.next_kiriban
        lines.append(f"みんなの出社 {number}回目のキリ番まで あと *{to_go}回*")
    return lines


def point_get_message(arrival: ArrivalResult, outlook: Outlook | None = None) -> list[Block]:
    """Build the message announcing a counted arrival, its points, its level and what to aim for next."""
    level = get_level(arrival.current_score)

    experience_rate = int(100 * level.progress_points / level.span)
    experience_add_up_rate = int(100 * arrival.score_sum / level.span)
    # show at least one cell: a bar of spaces only renders as an empty inline code in Slack
    digits = max(1, (experience_rate + 10 - 1) // 10)
    point_rate_text = "█" * digits + " " * (10 - digits)

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
            かたがき: *{level.name}* (lv{level.number})
            つぎのレベルまで: {next_level_text}
            しんこうど: {progress_text}
            うちわけ:
            """
        )
        + achievements_text
    )
    if outlook is not None:
        if lines := outlook_lines(outlook):
            context += "\nつぎのもくひょう:\n" + "\n".join(f" - {line}" for line in lines)
        if outlook.team is not None:
            context += f"\n{team_text(outlook.team)}"

    return [
        blocks.SectionBlock(
            text=f"*{arrival.time:%H:%M}* "
            f"{'最速' if is_first else ''}出社登録しました！"
            f"\n<@{arrival.user_id}>さんのポイント "
            f"{arrival.previous_score} → *{arrival.current_score}* "
            f"(*+{arrival.score_sum}*){level_up_text}" + ("" if is_first else f"\n本日 {arrival.rank}人目の出社です")
        ),
        blocks.DividerBlock(),
        blocks.ContextBlock(elements=[basic_components.MarkdownTextObject(text=context)]),
        blocks.DividerBlock(),
    ]


def _item_effect_text(effect: ItemEffect) -> str:
    """Return what gave an item's points: the item, and whose treat it was."""
    item = ITEMS[effect.item_id]
    return f"{item.label} (<@{effect.giver}>さんから)" if effect.giver else item.label


ITEM_PICK_GUIDE = (
    "1つだけ獲得できます。効果は次の出社から。持てるアイテムは1つまでで、"
    "アイテムによる加点は1回の出社につき最大 +3pt です。"
)


def item_pick_view(
    offered: list[ItemData], channel_id: str, thread_ts: str, day: date, image_urls: Mapping[str, str] = ITEM_IMAGE_URLS
) -> dict:
    """Build the modal offering today's items as cards, picked with a radio button and submitted.

    Views are built as dictionaries: slack_sdk has no model of the card block.
    """
    return {
        "type": "modal",
        "callback_id": CallbackID.ITEM_PICK,
        "title": _plain("今日のアイテム"),
        "submit": _plain("獲得"),
        "close": _plain("やめる"),
        "private_metadata": json.dumps({"channel": channel_id, "thread_ts": thread_ts, "day": day.isoformat()}),
        "blocks": [
            {"type": "section", "text": _mrkdwn(ITEM_PICK_GUIDE)},
            *(item_card(item, image_urls.get(item.id)) for item in offered),
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
    """Build the read-only modal of today's items: after the pick, or while another item is held.

    Slack shows a submit button anyway, so it reads "OK" and only closes the modal.
    """
    return {
        "type": "modal",
        "callback_id": CallbackID.ITEM_REVIEW,
        "title": _plain("今日のアイテム"),
        "submit": _plain("OK"),
        "close": _plain("閉じる"),
        "blocks": [
            {"type": "section", "text": _mrkdwn(notice)},
            *(item_card(item, image_urls.get(item.id), picked=item.id == picked_item_id) for item in offered),
            {"type": "context", "elements": [_mrkdwn("アイテムは1日1つまで。出社した日に選べます。")]},
        ],
    }


def item_card(item: ItemData, image_url: str | None, *, picked: bool = False) -> dict:
    """Return an item's card: its image and name, its story as the subtitle and exactly what it does as the body."""
    card = {
        "type": "card",
        "title": _mrkdwn(f"*{item.name}*" + ("  :white_check_mark: 獲得済み" if picked else "")),
        "subtitle": _mrkdwn(item.flavor),
        "body": _mrkdwn(f"効果: {item.effect}"),
    }
    if image_url:  # an item whose image is not hosted yet has no icon
        card["icon"] = {"type": "image", "image_url": image_url, "alt_text": item.name}
    return card


def _plain(text: str) -> dict:
    return {"type": "plain_text", "text": text}


def _mrkdwn(text: str) -> dict:
    return {"type": "mrkdwn", "text": text}


def notice_view(text: str) -> dict:
    """Build a modal that only shows a message (the reply to the arrival shortcut)."""
    return {
        "type": "modal",
        "title": _plain("出社登録"),
        "close": _plain("閉じる"),
        "blocks": [{"type": "section", "text": _mrkdwn(text)}],
    }


def item_picked_text(user_id: str, item: ItemData) -> str:
    """Return the announcement of a pick, kept small: one line in the thread."""
    return f"<@{user_id}>さんが {item.label} を獲得しました（{item.effect}）"


def item_picked_message(user_id: str, item: ItemData) -> list[Block]:
    """Build the thread post announcing a pick as one line of small text."""
    return [blocks.ContextBlock(elements=[basic_components.MarkdownTextObject(text=item_picked_text(user_id, item))])]


def achievement_view(engine: BadgeEngine, user_id: str, jst_datetime: datetime | None = None) -> View:
    """Build the modal with the user's statistics, attendance history and badges.

    jst_datetime is the "today" of the attendance history (default: now).
    """
    today = (jst_datetime or datetime.now(JST)).date()
    user_badges = {badge_id: tally for (owner, badge_id), tally in engine.user_badges.items() if owner == user_id}
    # kiribans number the arrivals of all users
    arrival_count = len(engine.results)
    next_kiriban = next((kiriban for kiriban in KIRIBANS if arrival_count < kiriban.number), None)
    return View(
        type="modal",
        title="Achievements",
        close="閉じる",
        blocks=[
            *statistics_blocks(engine, user_id, today),
            *attendance_history_blocks(attendance_by_day(engine, user_id, today)),
            *badge_blocks(user_badges, arrival_count, next_kiriban),
        ],
    )


def statistics_blocks(engine: BadgeEngine, user_id: str, today: date | None = None) -> list[Block]:
    """Build the statistics section: counts, level, the earliest and latest arrival times and the held item."""
    user = engine.users.get(user_id)
    arrivals = user.results if user else []
    if not arrivals:
        text = "まだ出社登録がありません。最初の出社登録をしてみましょう！"
    else:
        # "HH:MM" strings sort like the times of day
        times = [f"{arrival.time:%H:%M}" for arrival in arrivals]
        text = "\n".join(
            [
                f"• *総出社回数*: {len(arrivals)}回",
                f"• *最速出社*: {sum(arrival.rank == 1 for arrival in arrivals)}回",
                f"• *現在レベル*: {get_level(user.score).number} ({user.score}pt)",
                f"• *初回出社*: {arrivals[0].time:%Y-%m-%d}",
                f"• *最早出社*: `{min(times)}`",
                f"• *最遅出社*: `{max(times)}`",
            ]
        )
        held = engine.held_item(user_id, today) if today else None
        if held is not None:
            until = f" ({held.last_day:%m/%d}まで)" if held.last_day else " (次の出社で使います)"
            text += f"\n• *所持アイテム*: {ITEMS[held.pick.item_id].label}{until}"
    return [blocks.HeaderBlock(text="出社統計情報"), blocks.SectionBlock(text=text), blocks.DividerBlock()]


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


def badge_blocks(
    user_badges: dict[int, UserBadgeTally], arrival_count: int, next_kiriban: Kiriban | None
) -> list[Block]:
    """Build the badge sections: every badge as an icon, the achieved ones in detail and the unachieved ones listed."""
    result: list[Block] = [blocks.HeaderBlock(text="獲得したバッジ")]
    badge_types = badge_types_to_show()

    for badge_type in badge_types:
        result.append(blocks.SectionBlock(text=f"*{badge_type.id}系 : {badge_type.description}*"))
        badges = BADGES_BY_TYPE[badge_type.id]
        if badge_type.id == KIRIBAN_BADGE_TYPE_ID:
            # only the kiribans that were taken, and how far the next one is
            badges = [badge for badge in badges if badge.id in user_badges]
        icons = [_badge_icon(badge, user_badges.get(badge.id)) for badge in badges]
        result.extend(
            blocks.ContextBlock(elements=list(chunk)) for chunk in batched(icons, CONTEXT_ITEM_MAX, strict=False)
        )
        if badge_type.id == KIRIBAN_BADGE_TYPE_ID:
            result.append(blocks.SectionBlock(text=_kiriban_status_text(arrival_count, next_kiriban)))
        result.append(blocks.DividerBlock())

    shown_type_ids = {badge_type.id for badge_type in badge_types}
    achieved = sorted(
        (
            (BADGES[badge_id], tally)
            for badge_id, tally in user_badges.items()
            if BADGES[badge_id].badge_type_id in shown_type_ids
        ),
        key=lambda pair: pair[1].first,
    )
    if achieved:
        result.append(blocks.HeaderBlock(text="獲得済みバッジ詳細"))
        result.append(blocks.RichTextBlock(elements=_achieved_rich_text(achieved)))

    result.extend(
        [
            blocks.DividerBlock(),
            blocks.HeaderBlock(text="未獲得バッジ一覧"),
            blocks.SectionBlock(text=_unachieved_text(badge_types, user_badges, next_kiriban)),
        ]
    )
    return result


def _icon(alt_text: str, *, achieved: bool) -> block_elements.ImageElement:
    """Return the image of an achieved (or attended) or an unachieved (or missed) item."""
    url = ACHIEVED_BADGE_IMAGE_URL if achieved else NOT_ACHIEVED_BADGE_IMAGE_URL
    return block_elements.ImageElement(image_url=url, alt_text=alt_text)


def _badge_icon(badge: BadgeData, tally: UserBadgeTally | None) -> block_elements.ImageElement:
    """Return the badge's image: with its condition and first date if the user has it, hidden if not."""
    if tally is None:
        return _icon(f"【{badge.message}】???", achieved=False)
    return _icon(f"【{badge.message}】{badge.condition} @ {tally.first:%Y-%m-%d}", achieved=True)


def _kiriban_status_text(arrival_count: int, next_kiriban: Kiriban | None) -> str:
    """Return how far the next kiriban is."""
    if next_kiriban is None:
        return "現在実装されているキリ番は全て達成可能範囲を超えています。今後の実装をお待ちください。"
    return f"次のキリ番まで: あと *{next_kiriban.number - arrival_count}回* ({next_kiriban.number}回目)"


def _achieved_rich_text(achieved: list[tuple[BadgeData, UserBadgeTally]]) -> list[dict]:
    """Return the rich text of the achieved badges, the earliest first: a bullet each with its details indented."""
    elements = []
    for badge, tally in achieved:
        title = [
            {"type": "text", "text": f"{badge.message} ", "style": {"bold": True}},
            {"type": "text", "text": f"@ {tally.first:%Y-%m-%d} "},
        ]
        details = [
            [{"type": "text", "text": f"{badge.condition}", "style": {"code": True}}],
            [
                {"type": "text", "text": "計 "},
                {"type": "text", "text": f"{badge.score * tally.count}", "style": {"bold": True}},
                {"type": "text", "text": f"pt ({badge.score}pt x {tally.count})"},
            ],
        ]
        elements.append(
            {
                "type": "rich_text_list",
                "style": "bullet",
                "elements": [{"type": "rich_text_section", "elements": title}],
            }
        )
        elements.extend(
            {
                "type": "rich_text_list",
                "style": "bullet",
                "indent": 1,
                "elements": [{"type": "rich_text_section", "elements": detail}],
            }
            for detail in details
        )
    return elements


def _unachieved_text(
    badge_types: list[BadgeTypeData], user_badges: dict[int, UserBadgeTally], next_kiriban: Kiriban | None
) -> str:
    """Return the list of the badges the user has not earned, by badge type."""
    next_kiriban_id = next_kiriban.id if next_kiriban else None
    sections = []
    for badge_type in badge_types:
        # only the kiriban the arrivals of all users reach next
        unachieved = [
            f"• [{badge.id}] {badge.message}"
            for badge in BADGES_BY_TYPE[badge_type.id]
            if badge.id not in user_badges and (badge_type.id != KIRIBAN_BADGE_TYPE_ID or badge.id == next_kiriban_id)
        ]
        if unachieved:
            sections.append(f"*{badge_type.id}系*\n" + "\n".join(unachieved))
    return "\n\n".join(sections) or "すべてのバッジを獲得済みです！"
