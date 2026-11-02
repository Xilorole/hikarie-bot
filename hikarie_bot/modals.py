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
from hikarie_bot.engine import ArrivalResult, BadgeEngine, UserBadgeTally
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
    CHECK_ACHIEVEMENT = "CHECK_ACHIEVEMENT"


class BlockID:
    """Class for storing the block IDs used in the Slack app."""

    FASTEST_ARRIVAL = "FASTEST_ARRIVAL"
    ARRIVED_OFFICE = "ARRIVED_OFFICE"


class ShortcutID:
    """Class for storing the shortcut IDs used in the Slack app."""

    REBOOT = "reboot"  # only small letters are allowed


def render(message: list[Block]) -> list[dict]:
    """Render the blocks of a message to the dictionaries Slack takes."""
    return [block.to_dict() for block in message]


def to_text(message: list[Block]) -> str:
    """Return the text of the message's sections, as the fallback text of the post."""
    return "\n".join(block.text.text for block in message if isinstance(block, blocks.SectionBlock))


def initial_message() -> list[Block]:
    """Build the daily question with its buttons."""
    return [
        blocks.SectionBlock(text="ヒカリエに出社してる？"),
        blocks.ActionsBlock(
            elements=[
                block_elements.ButtonElement(text="最速出社した", action_id=ActionID.FASTEST_ARRIVAL, style="primary"),
                block_elements.ButtonElement(text="実績を確認", action_id=ActionID.CHECK_ACHIEVEMENT),
            ],
            block_id=BlockID.FASTEST_ARRIVAL,
        ),
    ]


def registry_message(arrivals: list[ArrivalResult]) -> list[Block]:
    """Build the question with its buttons and the day's arrivals in time order."""
    return [
        blocks.SectionBlock(text="ヒカリエに出社してる？"),
        blocks.ActionsBlock(
            elements=[
                block_elements.ButtonElement(text="出社した", action_id=ActionID.ARRIVED_OFFICE),
                block_elements.ButtonElement(text="実績を確認", action_id=ActionID.CHECK_ACHIEVEMENT),
            ],
            block_id=BlockID.ARRIVED_OFFICE,
        ),
        blocks.DividerBlock(),
        blocks.SectionBlock(
            text="本日の出社ユーザー :hikarie: :\n"
            + "\n".join(f"*{arrival.time:%H:%M}* : <@{arrival.user_id}>" for arrival in arrivals),
        ),
    ]


def point_get_message(arrival: ArrivalResult) -> list[Block]:
    """Build the message announcing a counted arrival, its points and its level."""
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
    achievements_text = "\n".join(f" - {badge.message}:*+{badge.score}pt*" for badge in badges)
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

    return [
        blocks.SectionBlock(
            text=f"*{arrival.time:%H:%M}* "
            f"{'最速' if is_first else ''}出社登録しました！{' :hikarie:' if is_first else ''}"
            f"\n<@{arrival.user_id}>さんのポイント "
            f"{arrival.previous_score} → *{arrival.current_score}* "
            f"(*+{arrival.score_sum}*){level_up_text}"
        ),
        blocks.DividerBlock(),
        blocks.ContextBlock(elements=[basic_components.MarkdownTextObject(text=context)]),
        blocks.DividerBlock(),
    ]


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
            *statistics_blocks(engine, user_id),
            *attendance_history_blocks(attendance_by_day(engine, user_id, today)),
            *badge_blocks(user_badges, arrival_count, next_kiriban),
        ],
    )


def statistics_blocks(engine: BadgeEngine, user_id: str) -> list[Block]:
    """Build the statistics section: counts, level and the earliest and latest arrival times."""
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
