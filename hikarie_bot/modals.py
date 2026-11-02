from datetime import date, datetime, timedelta
from functools import cached_property
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
    BADGE_TYPES_TO_CHECK,
    CONTEXT_ITEM_MAX,
    NOT_ACHIEVED_BADGE_IMAGE_URL,
)
from hikarie_bot.constants import (
    ACHIEVED_BADGE_IMAGE_URL as ARRIVED_IMAGE_URL,
)
from hikarie_bot.constants import (
    NOT_ACHIEVED_BADGE_IMAGE_URL as NOT_ARRIVED_IMAGE_URL,
)
from hikarie_bot.db_data.badges import KIRIBANS, BadgeData, BadgeTypeData, Kiriban
from hikarie_bot.engine import ArrivalResult, BadgeEngine, UserBadgeTally
from hikarie_bot.utils import (
    get_current_jst_datetime,
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
    return [badge_type for badge_type in db_data.BadgeTypes if badge_type.id in BADGE_TYPES_TO_CHECK]


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


class BaseMessage:
    """Base class for creating Slack messages with blocks."""

    def __init__(self) -> None:
        """Initialize the BaseMessage with an empty list of blocks."""
        self.blocks: list[Block] = []

    def render(self) -> list[dict]:
        """Render the blocks to a list of dictionaries."""
        return [block.to_dict() for block in self.blocks]

    def to_text(self) -> str:
        """Convert the blocks to a text."""
        # block.text is a TextObject, so we need to check if block has a text attribute
        return "\n".join(
            [
                # block.text is clearly a TextObject,
                # but the block.text is later assigned in __init__
                block.text.text  # type: ignore  # noqa: PGH003
                for block in self.blocks
                if hasattr(block, "text")
            ]
        )


class InitialMessage(BaseMessage):
    """Class for creating the initial Slack message with a question and a button."""

    def __init__(self) -> None:
        """Initialize the InitialMessage with a question and a button."""
        super().__init__()
        self.blocks.extend(
            [
                blocks.SectionBlock(text="ヒカリエに出社してる？"),
                blocks.ActionsBlock(
                    elements=[
                        block_elements.ButtonElement(
                            text="最速出社した",
                            action_id=ActionID.FASTEST_ARRIVAL,
                            style="primary",
                        ),
                        block_elements.ButtonElement(
                            text="実績を確認",
                            action_id=ActionID.CHECK_ACHIEVEMENT,
                        ),
                    ],
                    block_id=BlockID.FASTEST_ARRIVAL,
                ),
            ]
        )


class RegistryMessage(BaseMessage):
    """Class for creating the registry Slack message with a question and a button."""

    def __init__(self, arrivals: list[ArrivalResult]) -> None:
        """Initialize the RegistryMessage with a question, a button and the day's arrivals in time order."""
        super().__init__()
        self.blocks.extend(
            [
                blocks.SectionBlock(text="ヒカリエに出社してる？"),
                blocks.ActionsBlock(
                    elements=[
                        block_elements.ButtonElement(
                            text="出社した",
                            action_id=ActionID.ARRIVED_OFFICE,
                        ),
                        block_elements.ButtonElement(
                            text="実績を確認",
                            action_id=ActionID.CHECK_ACHIEVEMENT,
                        ),
                    ],
                    block_id=BlockID.ARRIVED_OFFICE,
                ),
                blocks.DividerBlock(),
                blocks.SectionBlock(
                    text="本日の出社ユーザー :hikarie: :\n"
                    + "\n".join([f"*{arrival.time:%H:%M}* : <@{arrival.user_id}>" for arrival in arrivals]),
                ),
            ]
        )


class PointGetMessage(BaseMessage):
    """Class for creating the point get Slack message."""

    def __init__(self, arrival: ArrivalResult) -> None:
        """Initialize the PointGetMessage with a counted arrival.

        initial_arrival tells whether this was the day's first arrival, by the computed rank.
        """
        super().__init__()

        user_id = arrival.user_id
        arrive_time = arrival.time
        previous_point = arrival.previous_score
        current_point = arrival.current_score
        score_addup = arrival.score_sum

        # get the variables
        level = get_level(current_point)

        # calculate the experience rate
        experience_rate = int(100 * level.progress_points / level.span)
        experience_add_up_rate = int(100 * score_addup / level.span)
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
        if max_level_reached(previous_point, current_point):
            level_up_text = " *上限に到達!* :crown: "
        elif leveled_up(previous_point, current_point):
            level_up_text = " *LvUP!* :star2: "
        else:
            level_up_text = ""

        self.initial_arrival = arrival.rank == 1
        initial_arrival_text = "最速" if self.initial_arrival else ""
        hikarie_text = " :hikarie:" if self.initial_arrival else ""

        badges = [BADGES[badge_id] for badge_id in sorted(arrival.badge_ids)]
        achievements_text = "\n".join([f" - {badge.message}:*+{badge.score}pt*" for badge in badges])

        context = dedent(
            f"""\
            かたがき: *{level.name}* (lv{level.number})
            つぎのレベルまで: {next_level_text}
            しんこうど: {progress_text}
            うちわけ:
            """
        ) + (achievements_text)

        self.blocks.extend(
            [
                blocks.SectionBlock(
                    text=f"*{arrive_time:%H:%M}* "
                    f"{initial_arrival_text}出社登録しました！{hikarie_text}"
                    f"\n<@{user_id}>さんのポイント "
                    f"{previous_point} → *{current_point}* "
                    f"(*+{score_addup}*){level_up_text}"
                ),
                blocks.DividerBlock(),
                blocks.ContextBlock(
                    elements=[
                        basic_components.MarkdownTextObject(
                            text=context,
                        )
                    ]
                ),
                blocks.DividerBlock(),
            ]
        )


class AchievementView(View):
    """Class for creating the achievement Slack view."""

    def __init__(self, engine: BadgeEngine, user_id: str, jst_datetime: datetime | None = None) -> None:
        """Initialize the AchievementView with the computed arrivals and the user ID.

        jst_datetime is the "today" of the attendance history (default: now).
        """
        super().__init__(type="modal", title="Achievements", close="閉じる")

        self.engine = engine
        self.user_id = user_id
        self.jst_datetime = jst_datetime

        # 各セクションのブロックを生成して追加
        self.blocks.extend(self.generate_statistics_blocks())
        self.blocks.extend(self.generate_attendance_history_blocks())
        self.blocks.extend(self.generate_badge_blocks())

    def generate_statistics_blocks(self) -> list[Block]:
        """Generate statistics section blocks."""
        blocks_list: list[Block] = [blocks.HeaderBlock(text="出社統計情報")]

        # 基本統計を取得
        stats = self._get_user_statistics()

        # 出社データがない場合
        if stats["total_arrivals"] == 0:
            basic_info = "まだ出社登録がありません。最初の出社登録をしてみましょう！"
            blocks_list.append(blocks.SectionBlock(text=basic_info))
        else:
            # 統計情報をリスト形式で表示
            stats_info = self._format_statistics_text(stats)
            blocks_list.append(blocks.SectionBlock(text=stats_info))

        blocks_list.append(blocks.DividerBlock())
        return blocks_list

    def generate_attendance_history_blocks(self) -> list[Block]:
        """Generate attendance history section blocks."""
        blocks_list: list[Block] = [blocks.HeaderBlock(text="過去の出社履歴")]

        # 過去10週間の平日の出社データを取得
        attendance_data = self._get_attendance_data_for_past_10_weeks()

        # GitHub風の縦書き表示を作成
        blocks_list.extend(self._create_github_style_display(attendance_data))
        return blocks_list

    def generate_badge_blocks(self) -> list[Block]:
        """Generate badge section blocks."""
        blocks_list: list[Block] = [blocks.HeaderBlock(text="獲得したバッジ")]

        # バッジの全量を表示する
        for badge_type in badge_types_to_show():
            # バッジタイプの説明を追加
            blocks_list.append(blocks.SectionBlock(text=f"*{badge_type.id}系 : {badge_type.description}*"))

            # 全バッジの視覚的表示（獲得済み・未獲得）
            all_badge_elements = self._generate_badge_elements_for_type(badge_type)
            if all_badge_elements:
                blocks_list.extend(self._create_context_blocks_from_elements(all_badge_elements))

            # 6xx番台（キリ番バッジ）の場合は次のキリ番情報を追加
            if badge_type.id == KIRIBAN_BADGE_TYPE_ID:
                kiriban_status = self._generate_kiriban_status_text()
                blocks_list.append(blocks.SectionBlock(text=kiriban_status))

            blocks_list.append(blocks.DividerBlock())

        # 獲得済みバッジの詳細をまとめて表示
        achieved_badges_details = self._create_all_achieved_badges_summary()
        if achieved_badges_details:
            blocks_list.append(blocks.HeaderBlock(text="獲得済みバッジ詳細"))
            blocks_list.extend(achieved_badges_details)

        # 未獲得バッジの一覧を表示
        unachieved_badges_list = self._create_unachieved_badges_list()
        if unachieved_badges_list:
            blocks_list.append(blocks.DividerBlock())
            blocks_list.append(blocks.HeaderBlock(text="未獲得バッジ一覧"))
            blocks_list.extend(unachieved_badges_list)

        return blocks_list

    def _format_statistics_text(self, stats: dict) -> str:
        """Format statistics data into display text."""
        stats_info = f"• *総出社回数*: {stats['total_arrivals']}回\n"
        stats_info += f"• *最速出社*: {stats['fastest_arrivals']}回\n"
        stats_info += f"• *現在レベル*: {stats['current_level']} ({stats['current_score']}pt)\n"
        stats_info += f"• *初回出社*: {stats['first_arrival_date']}\n"

        if stats["earliest_time"]:
            stats_info += f"• *最早出社*: `{stats['earliest_time']}`\n"
        if stats["latest_time"]:
            stats_info += f"• *最遅出社*: `{stats['latest_time']}`\n"

        return stats_info.rstrip()

    def _generate_badge_elements_for_type(self, badge_type: BadgeTypeData) -> list[block_elements.ImageElement]:
        """Generate badge elements for a specific badge type."""
        elements = []
        badges = BADGES_BY_TYPE[badge_type.id]

        # 6xx番台（キリ番バッジ）の場合は取得済みのみ表示
        if badge_type.id == KIRIBAN_BADGE_TYPE_ID:
            for badge in badges:
                user_badge = self._user_badges.get(badge.id)
                if user_badge:
                    element = block_elements.ImageElement(
                        image_url=ACHIEVED_BADGE_IMAGE_URL,
                        alt_text=f"【{badge.message}】{badge.condition} @ {user_badge.first:%Y-%m-%d}",
                    )
                    elements.append(element)
        else:
            # 他のバッジタイプは従来通り全て表示
            for badge in badges:
                element = self._create_badge_element(badge)
                elements.append(element)

        return elements

    def _create_badge_element(self, badge: BadgeData) -> block_elements.ImageElement:
        """Create a single badge element based on user's badge status."""
        user_badge = self._user_badges.get(badge.id)

        if user_badge:
            return block_elements.ImageElement(
                image_url=ACHIEVED_BADGE_IMAGE_URL,
                alt_text=f"【{badge.message}】{badge.condition} @ {user_badge.first:%Y-%m-%d}",
            )
        return block_elements.ImageElement(
            image_url=NOT_ACHIEVED_BADGE_IMAGE_URL,
            alt_text=f"【{badge.message}】???",
        )

    @cached_property
    def _user_badges(self) -> dict[int, UserBadgeTally]:
        """Return the user's badges by badge ID, in the order they were first earned."""
        return {
            badge_id: tally for (user_id, badge_id), tally in self.engine.user_badges.items() if user_id == self.user_id
        }

    @cached_property
    def _arrival_count(self) -> int:
        """Count the arrivals of all users, which kiribans number."""
        return len(self.engine.results)

    @cached_property
    def _next_kiriban(self) -> Kiriban | None:
        """Return the next kiriban to be reached, or None beyond the last one."""
        return next((kiriban for kiriban in KIRIBANS if self._arrival_count < kiriban.number), None)

    def _generate_kiriban_status_text(self) -> str:
        """Generate kiriban status text showing progress to next kiriban."""
        if self._next_kiriban is None:
            return "現在実装されているキリ番は全て達成可能範囲を超えています。今後の実装をお待ちください。"
        remaining = self._next_kiriban.number - self._arrival_count
        return f"次のキリ番まで: あと *{remaining}回* ({self._next_kiriban.number}回目)"

    def _create_context_blocks_from_elements(
        self, elements: list[block_elements.ImageElement]
    ) -> list[blocks.ContextBlock]:
        """Create context blocks from elements, respecting CONTEXT_ITEM_MAX limit."""
        context_blocks = []
        current_elements = []

        for element in elements:
            if len(current_elements) == CONTEXT_ITEM_MAX:
                context_blocks.append(blocks.ContextBlock(elements=current_elements))
                current_elements = []
            current_elements.append(element)

        # 残りの要素があれば最後のブロックに追加
        if current_elements:
            context_blocks.append(blocks.ContextBlock(elements=current_elements))

        return context_blocks

    def _get_user_statistics(self) -> dict:
        """Get comprehensive statistics for the user."""
        # 全出社データを取得
        user = self.engine.users.get(self.user_id)
        all_arrivals = user.results if user else []

        if not all_arrivals:
            return {
                "total_arrivals": 0,
                "fastest_arrivals": 0,
                "current_level": 1,
                "current_score": 0,
                "first_arrival_date": None,
                "earliest_time": None,
                "latest_time": None,
            }

        stats = {
            "total_arrivals": len(all_arrivals),
            "fastest_arrivals": sum(1 for arrival in all_arrivals if arrival.rank == 1),
            "current_level": get_level(user.score).number,
            "current_score": user.score,
            "first_arrival_date": all_arrivals[0].time.strftime("%Y-%m-%d"),
        }

        # 最早・最遅の出社時刻
        earliest = min(all_arrivals, key=lambda x: x.time.hour * 60 + x.time.minute)
        latest = max(all_arrivals, key=lambda x: x.time.hour * 60 + x.time.minute)

        stats["earliest_time"] = earliest.time.strftime("%H:%M")
        stats["latest_time"] = latest.time.strftime("%H:%M")

        return stats

    def _get_attendance_data_for_past_10_weeks(self) -> dict[date, bool]:
        """Get attendance data for the past 10 weeks (weekdays only).

        Returns:
            Dict mapping date objects to attendance status (bool)
        """
        today = (self.jst_datetime or get_current_jst_datetime()).date()
        # 10週間前の月曜日（今週を含む）から今日まで
        start_monday = today - timedelta(days=today.weekday(), weeks=9)
        days = (start_monday + timedelta(days=offset) for offset in range((today - start_monday).days + 1))

        user = self.engine.users.get(self.user_id)
        arrival_dates = {time.date() for time in user.times} if user else set()
        # 平日のみ（月曜日=0 から 金曜日=4）
        return {day: day in arrival_dates for day in days if day.weekday() < 5}  # noqa: PLR2004

    def _create_github_style_display(self, attendance_data: dict[date, bool]) -> list[Block]:
        """Create GitHub-style vertical activity display.

        Args:
            attendance_data: Dict mapping date objects to attendance status
        """
        # 日付を曜日ごとにグループ化
        weekday_data = {i: [] for i in range(5)}  # 0=月曜日, 4=金曜日

        sorted_dates = sorted(attendance_data.keys())
        for date_obj in sorted_dates:
            weekday = date_obj.weekday()
            if weekday < 5:  # 平日のみ  # noqa: PLR2004
                attended = attendance_data[date_obj]
                display_date = date_obj.strftime("%m/%d")

                if attended:
                    element = block_elements.ImageElement(
                        image_url=ARRIVED_IMAGE_URL,
                        alt_text=f"{display_date} 出社",
                    )
                else:
                    element = block_elements.ImageElement(
                        image_url=NOT_ARRIVED_IMAGE_URL,
                        alt_text=f"{display_date} 未出社",
                    )

                weekday_data[weekday].append(element)

        # 各曜日の行を作成（最大10要素制限に対応）
        blocks_list = []
        for weekday in range(5):
            if weekday_data[weekday]:  # データがある場合のみ
                # 10要素制限のため、最大10週分のみ表示
                elements_to_show = weekday_data[weekday][:10]

                blocks_list.append(blocks.ContextBlock(elements=elements_to_show))

        return blocks_list

    def _create_all_achieved_badges_summary(self) -> list[Block]:
        """Create a summary block for all achieved badges."""
        # 獲得済みバッジを全て取得し、獲得日時の早い順でソート
        achieved_user_badges = sorted(
            (
                (user_badge, BADGES[badge_id])
                for badge_id, user_badge in self._user_badges.items()
                if BADGES[badge_id].badge_type_id in BADGE_TYPES_TO_CHECK
            ),
            key=lambda pair: pair[0].first,
        )

        if not achieved_user_badges:
            return []

        # RichTextBlockの要素を構築 - 各バッジとその詳細をペアで作成
        rich_text_elements = []

        for user_badge, badge in achieved_user_badges:
            achievement_count = user_badge.count

            # トップレベル: ID、タイトル、獲得日
            initial_date = user_badge.first.strftime("%Y-%m-%d")
            top_level_text_elements = [
                {"type": "text", "text": f"{badge.message} ", "style": {"bold": True}},
                {"type": "text", "text": f"@ {initial_date} "},
            ]

            # 2ndレベル: 条件と獲得ポイント詳細
            total_points = badge.score * achievement_count
            second_level_text_elements = [
                [{"type": "text", "text": f"{badge.condition}", "style": {"code": True}}],
                [
                    {"type": "text", "text": "計 "},
                    {"type": "text", "text": f"{total_points}", "style": {"bold": True}},
                    {"type": "text", "text": f"pt ({badge.score}pt x {achievement_count})"},
                ],
            ]

            # このバッジのトップレベル項目を追加
            rich_text_elements.append(
                {
                    "type": "rich_text_list",
                    "style": "bullet",
                    "elements": [{"type": "rich_text_section", "elements": top_level_text_elements}],
                }
            )

            # このバッジの詳細をインデントされた項目として追加
            rich_text_elements.extend(
                [
                    {
                        "type": "rich_text_list",
                        "style": "bullet",
                        "indent": 1,
                        "elements": [{"type": "rich_text_section", "elements": second_level_text_element}],
                    }
                    for second_level_text_element in second_level_text_elements
                ]
            )

        # RichTextBlockを返す
        return [blocks.RichTextBlock(elements=rich_text_elements)]

    def _create_unachieved_badges_list(self) -> list[Block]:
        """Create a simple list of unachieved badges for the user."""
        blocks_list: list[Block] = []
        unachieved_badges_text = ""

        next_kiriban_id = self._next_kiriban.id if self._next_kiriban else None
        for badge_type in badge_types_to_show():
            badges = BADGES_BY_TYPE[badge_type.id]
            # キリ番は全体の出社回数で次に来るものだけを表示
            type_unachieved = [
                f"[{badge.id}] {badge.message}"
                for badge in badges
                if badge.id not in self._user_badges
                and (badge_type.id != KIRIBAN_BADGE_TYPE_ID or badge.id == next_kiriban_id)
            ]

            if type_unachieved:
                unachieved_badges_text += f"*{badge_type.id}系*\n"
                unachieved_badges_text += "\n".join([f"• {badge}" for badge in type_unachieved])
                unachieved_badges_text += "\n\n"

        if unachieved_badges_text:
            blocks_list.append(blocks.SectionBlock(text=unachieved_badges_text.strip()))
        else:
            blocks_list.append(blocks.SectionBlock(text="すべてのバッジを獲得済みです！"))

        return blocks_list
