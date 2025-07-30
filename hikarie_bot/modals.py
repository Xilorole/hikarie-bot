import zoneinfo  # Added for timezone conversion
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from textwrap import dedent

from loguru import logger
from slack_sdk.models.blocks import (
    Block,
    basic_components,
    block_elements,
    blocks,
)
from slack_sdk.models.views import View
from sqlalchemy import func
from sqlalchemy.orm import Session

from hikarie_bot.constants import (
    ACHIEVED_BADGE_IMAGE_URL,
    BADGE_TYPES_TO_CHECK,
    CONTEXT_ITEM_MAX,
    NOT_ACHIEVED_BADGE_IMAGE_URL,
    TAKEN_6XX_BADGE_IMAGE_URL,
)
from hikarie_bot.constants import (
    ACHIEVED_BADGE_IMAGE_URL as ARRIVED_IMAGE_URL,
)
from hikarie_bot.constants import (
    NOT_ACHIEVED_BADGE_IMAGE_URL as NOT_ARRIVED_IMAGE_URL,
)
from hikarie_bot.models import (
    Achievement,
    Badge,
    BadgeType,
    GuestArrivalInfo,
    User,
    UserBadge,
    UserInfoRaw,
)
from hikarie_bot.utils import (
    get_current_level_point,
    get_level,
    get_level_name,
    get_point_range_to_next_level,
    get_point_to_next_level,
    is_level_uped,
)


class ActionID:
    """Class for storing the action IDs used in the Slack app."""

    ARRIVED_OFFICE = "ARRIVED_OFFICE"
    FASTEST_ARRIVAL = "FASTEST_ARRIVAL"
    POINT_GET = "POINT_GET"
    CHECK_ACHIEVEMENT = "CHECK_ACHIEVEMENT"


class BlockID:
    """Class for storing the block IDs used in the Slack app."""

    FASTEST_ARRIVAL = "FASTEST_ARRIVAL"
    FASTEST_ARRIVAL_REPLY = "FASTEST_ARRIVAL_REPLY"
    ARRIVED_OFFICE = "ARRIVED_OFFICE"
    ALREADY_REGISTERED_REPLY = "ALREADY_REGISTERED_REPLY"
    CHECK_ACHIEVEMENT = "CHECK_ACHIEVEMENT"


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

    def __init__(self, session: Session, jst_datetime: datetime) -> None:
        """Initialize the RegistryMessage with a question and a button."""
        super().__init__()

        start_of_day = jst_datetime.replace(hour=6, minute=0, second=0, microsecond=0)

        arrived_users = (
            session.query(GuestArrivalInfo)
            .filter(GuestArrivalInfo.arrival_time >= start_of_day)
            .filter(GuestArrivalInfo.arrival_time <= jst_datetime)
            .all()
        )
        arrived_user_text = "本日の出社ユーザー :hikarie: :\n"
        arrived_user_text += "\n".join(
            [
                f"*{user.arrival_time:%H:%M}* : <@{user.user_id}>{':crown:' if idx == 0 else ''}"
                for idx, user in enumerate(arrived_users)
            ]
        )
        logger.info(arrived_users)

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
                    + "\n".join([f"*{user.arrival_time:%H:%M}* : <@{user.user_id}>" for user in arrived_users]),
                ),
            ]
        )


class FastestArrivalMessage(BaseMessage):
    """Class for creating the fastest arrival Slack message."""

    def __init__(self, user_id: str, jst_datetime: datetime) -> None:
        """Initialize the FastestArrivalMessage with the fastest arrival user ID and time."""
        super().__init__()
        self.blocks.extend(
            [
                blocks.SectionBlock(
                    text=f"ヒカリエは正義 :hikarie:\n本日の最速出社: <@{user_id}> @ {jst_datetime:%Y-%m-%d %H:%M:%S}",
                    block_id=BlockID.FASTEST_ARRIVAL_REPLY,
                )
            ]
        )


class PointGetMessage(BaseMessage):
    """Class for creating the point get Slack message."""

    def __init__(
        self,
        session: Session,
        user_id: str,
        jst_datetime: datetime,
        *,
        initial_arrival: bool,
    ) -> None:
        """Initialize the PointGetMessage with the user ID and time."""
        super().__init__()

        ## variable
        score = session.query(User).filter(User.id == user_id).one()

        # retrieve guest arrival data
        start_of_day = jst_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        # Check for existing arrival for the same user on the same day
        arrival = (
            session.query(GuestArrivalInfo)
            .filter(GuestArrivalInfo.user_id == user_id)
            .filter(GuestArrivalInfo.arrival_time >= start_of_day)
            .filter(GuestArrivalInfo.arrival_time < end_of_day)
            .one()
        )

        arrive_time = score.update_datetime
        previous_point = score.previous_score
        current_point = score.current_score
        score_addup = arrival.acquired_score_sum

        # get the variables
        level = get_level(current_point)
        level_name = get_level_name(current_point)
        point_to_next_level = get_point_to_next_level(current_point)
        level_up_flag = is_level_uped(previous_point, current_point)
        current_level_point = get_current_level_point(current_point)
        point_range = get_point_range_to_next_level(current_point)

        # calculate the experience rate
        experience_rate = int(100 * current_level_point / point_range)
        experience_add_up_rate = int(100 * score_addup / point_range)
        digits = (experience_rate + 10 - 1) // 10
        point_rate_text = "█" * digits + " " * (10 - digits)

        initial_arrival_text = "最速" if initial_arrival else ""
        hikarie_text = " :hikarie:" if initial_arrival else ""

        # get the Achievements
        badges = (
            session.query(Badge)
            .join(Achievement, Achievement.badge_id == Badge.id)
            .filter(Achievement.arrival_id == arrival.id)
            .order_by(Achievement.badge_id)
            .all()
        )
        achievements_text = "\n".join([f" - {badge.message}:*+{badge.score}pt*" for badge in badges])

        context = dedent(
            f"""\
            かたがき: *{level_name}* (lv{level})
            つぎのレベルまで: *{point_to_next_level}pt*
            しんこうど: `{point_rate_text}` | *{experience_rate:>3d}%* (*+{experience_add_up_rate}%*)
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
                    f"(*+{score_addup}*){' *LvUP!* :star2: ' if level_up_flag else ''}"
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


class AlreadyRegisteredMessage(BaseMessage):
    """Class for creating the already registered Slack message."""

    def __init__(self, user_id: str, jst_datetime: datetime) -> None:
        """Initialize the AlreadyRegisteredMessage with the user ID and time."""
        super().__init__()
        self.blocks.extend(
            [
                blocks.SectionBlock(
                    text=f"本日の出社登録はすでに完了しています\n<@{user_id}> @ {jst_datetime:%Y-%m-%d %H:%M:%S}",
                    block_id=BlockID.ALREADY_REGISTERED_REPLY,
                )
            ]
        )


class AchievementView(View):
    """Class for creating the achievement Slack view."""

    def __init__(self, session: Session, user_id: str) -> None:
        """Initialize the AchievementView with the user ID."""
        super().__init__(type="modal", title="Achievements", close="閉じる")

        self.session = session
        self.user_id = user_id

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
        all_badge_types = (
            self.session.query(BadgeType).filter(BadgeType.id.in_(BADGE_TYPES_TO_CHECK)).order_by(BadgeType.id).all()
        )

        for badge_type in all_badge_types:
            # バッジタイプの説明を追加
            blocks_list.append(blocks.SectionBlock(text=f"*{badge_type.id}系 : {badge_type.description}*"))

            # 全バッジの視覚的表示（獲得済み・未獲得）
            all_badge_elements = self._generate_badge_elements_for_type(badge_type)
            if all_badge_elements:
                blocks_list.extend(self._create_context_blocks_from_elements(all_badge_elements))

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

    def _generate_badge_elements_for_type(self, badge_type: BadgeType) -> list[block_elements.ImageElement]:
        """Generate badge elements for a specific badge type."""
        elements = []
        badges = self.session.query(Badge).filter(Badge.badge_type_id == badge_type.id).all()

        for badge in badges:
            element = self._create_badge_element(badge)
            elements.append(element)

        return elements

    def _create_badge_element(self, badge: Badge) -> block_elements.ImageElement:
        """Create a single badge element based on user's badge status."""
        user_badge = (
            self.session.query(UserBadge)
            .filter(UserBadge.user_id == self.user_id, UserBadge.badge_id == badge.id)
            .one_or_none()
        )

        if user_badge:
            return block_elements.ImageElement(
                image_url=ACHIEVED_BADGE_IMAGE_URL,
                alt_text=f"【{badge.message}】{badge.condition} @ {user_badge.initially_acquired_datetime:%Y-%m-%d}",
            )
        if self._is_6xx_badge(badge.id):
            return self._create_6xx_badge_element(badge)
        return block_elements.ImageElement(
            image_url=NOT_ACHIEVED_BADGE_IMAGE_URL,
            alt_text=f"【{badge.message}】???",
        )

    def _create_6xx_badge_element(self, badge: Badge) -> block_elements.ImageElement:
        """Create element for 6XX special badges."""
        other_user_badge = self.session.query(UserBadge).filter(UserBadge.badge_id == badge.id).first()

        if other_user_badge is not None:
            return block_elements.ImageElement(
                image_url=TAKEN_6XX_BADGE_IMAGE_URL,
                alt_text=f"【{badge.message}】他のユーザーが獲得済み",
            )
        return block_elements.ImageElement(
            image_url=NOT_ACHIEVED_BADGE_IMAGE_URL,
            alt_text=f"【{badge.message}】???",
        )

    def _is_6xx_badge(self, badge_id: int) -> bool:
        """Check if badge is a 6XX special badge."""
        return 600 <= badge_id < 700  # noqa: PLR2004

    def _get_badge_achievement_count(self, badge_id: int) -> int:
        """Get the number of times a user has achieved a specific badge."""
        return (
            self.session.query(UserBadge)
            .filter(UserBadge.user_id == self.user_id, UserBadge.badge_id == badge_id)
            .count()
        )

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
        all_arrivals = (
            self.session.query(GuestArrivalInfo)
            .filter(GuestArrivalInfo.user_id == self.user_id)
            .order_by(GuestArrivalInfo.arrival_time)
            .all()
        )

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

        # ユーザー情報を取得
        user = self.session.query(User).filter(User.id == self.user_id).first()

        stats = {
            "total_arrivals": len(all_arrivals),
            "fastest_arrivals": sum(1 for arrival in all_arrivals if arrival.arrival_rank == 1),
            "current_level": user.level if user else 1,
            "current_score": user.current_score if user else 0,
            "first_arrival_date": all_arrivals[0].arrival_time.strftime("%Y-%m-%d"),
        }

        # 最早・最遅の出社時刻
        earliest = min(all_arrivals, key=lambda x: x.arrival_time.hour * 60 + x.arrival_time.minute)
        latest = max(all_arrivals, key=lambda x: x.arrival_time.hour * 60 + x.arrival_time.minute)

        stats["earliest_time"] = earliest.arrival_time.strftime("%H:%M")
        stats["latest_time"] = latest.arrival_time.strftime("%H:%M")

        return stats

    def _get_attendance_data_for_past_10_weeks(self) -> dict[date, bool]:
        """Get attendance data for the past 10 weeks (weekdays only).

        Returns:
            Dict mapping date objects to attendance status (bool)
        """
        from hikarie_bot.utils import get_current_jst_datetime

        current_date = get_current_jst_datetime()
        # 時刻を除いて日付のみにする
        current_date = current_date.replace(hour=23, minute=59, second=59, microsecond=999999)

        # 今週の月曜日を計算
        days_since_monday = current_date.weekday()  # 今週の月曜日からの日数
        this_week_monday = current_date - timedelta(days=days_since_monday)

        # 10週間前の月曜日を計算（今週を含む）
        start_monday = this_week_monday - timedelta(weeks=9)  # 9週前 + 今週 = 10週間

        # その期間の出社データを取得
        arrivals = (
            self.session.query(GuestArrivalInfo)
            .filter(
                GuestArrivalInfo.user_id == self.user_id,
                GuestArrivalInfo.arrival_time >= start_monday,
                GuestArrivalInfo.arrival_time <= current_date,
            )
            .all()
        )

        # 出社した日付のセットを作成
        arrival_dates = set()
        for arrival in arrivals:
            arrival_date = arrival.arrival_time.date()
            arrival_dates.add(arrival_date)

        # 10週間前の月曜日から今日までの平日について出社状況を記録
        attendance_data = {}
        current_check_date = start_monday

        while current_check_date <= current_date:
            # 平日のみ（月曜日=0 から 金曜日=4）
            if current_check_date.weekday() < 5:  # noqa: PLR2004
                check_date = current_check_date.date()
                attendance_data[check_date] = check_date in arrival_dates

            current_check_date += timedelta(days=1)

        return attendance_data

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
        blocks_list: list[Block] = []

        # 獲得済みバッジを全て取得し、獲得日時の早い順でソート
        achieved_user_badges = (
            self.session.query(UserBadge, Badge)
            .join(Badge, UserBadge.badge_id == Badge.id)
            .join(BadgeType, Badge.badge_type_id == BadgeType.id)
            .filter(UserBadge.user_id == self.user_id)
            .filter(BadgeType.id.in_(BADGE_TYPES_TO_CHECK))
            .order_by(UserBadge.initially_acquired_datetime)
            .all()
        )

        for user_badge, badge in achieved_user_badges:
            # 獲得回数を取得
            achievement_count = self._get_badge_achievement_count(badge.id)

            # SectionBlock - バッジ名の前にIDを追加
            initial_date = user_badge.initially_acquired_datetime.strftime("%Y-%m-%d")
            markdown_text = f"[{badge.id}] *{badge.message}* @ {initial_date}"
            blocks_list.append(blocks.SectionBlock(text=markdown_text))

            # Contextブロックを作成
            total_points = badge.score * achievement_count
            context_text = f"- {badge.condition} | {total_points}pt ({badge.score}pt x {achievement_count})"
            blocks_list.append(blocks.ContextBlock(elements=[basic_components.MarkdownTextObject(text=context_text)]))

        return blocks_list

    def _create_unachieved_badges_list(self) -> list[Block]:
        """Create a simple list of unachieved badges for the user."""
        blocks_list: list[Block] = []
        unachieved_badges_text = ""

        # バッジの全タイプを取得
        all_badge_types = (
            self.session.query(BadgeType).filter(BadgeType.id.in_(BADGE_TYPES_TO_CHECK)).order_by(BadgeType.id).all()
        )

        for badge_type in all_badge_types:
            badges = self.session.query(Badge).filter(Badge.badge_type_id == badge_type.id).all()
            type_unachieved = []

            for badge in badges:
                user_badge = (
                    self.session.query(UserBadge)
                    .filter(UserBadge.user_id == self.user_id, UserBadge.badge_id == badge.id)
                    .first()
                )

                if not user_badge:
                    # 6xxバッジの特別処理 - 他のユーザーが獲得済みの場合は表示しない
                    if self._is_6xx_badge(badge.id):
                        other_user_badge = self.session.query(UserBadge).filter(UserBadge.badge_id == badge.id).first()
                        if other_user_badge is not None:
                            continue

                    type_unachieved.append(f"[{badge.id}] {badge.message}")

            if type_unachieved:
                unachieved_badges_text += f"*{badge_type.id}系*\n"
                unachieved_badges_text += "\n".join([f"• {badge}" for badge in type_unachieved])
                unachieved_badges_text += "\n\n"

        if unachieved_badges_text:
            blocks_list.append(blocks.SectionBlock(text=unachieved_badges_text.strip()))
        else:
            blocks_list.append(blocks.SectionBlock(text="すべてのバッジを獲得済みです！"))

        return blocks_list


# Define dataclasses for each type of data structure returned by methods
@dataclass
class LevelUpUser:
    """User who leveled up during a specific time period."""

    user_id: str
    level: int
    level_name: str
    update_datetime: datetime


@dataclass
class ScoreGainer:
    """User who gained score during a specific time period."""

    user_id: str
    score_gained: int


@dataclass
class UserAchievement:
    """Achievement unlocked by a user."""

    user_id: str
    badge_id: int
    message: str
    achieved_time: datetime


@dataclass
class BadgeInfo:
    """Information about a badge."""

    badge_id: int | None
    message: str


@dataclass
class EarlyBird:
    """User who checked in earliest during a day."""

    user_id: str
    arrival_time: datetime


@dataclass
class AlmostLevelUpUser:
    """User who is close to leveling up."""

    user_id: str
    current_score: int
    points_needed: int
    next_level: int
    next_level_name: str


class WeeklyMessage(BaseMessage):
    """Class for creating weekly report Slack message."""

    def __init__(self, session: Session, report_date: datetime) -> None:
        """Initialize the WeeklyMessage with session and date.

        Args:
            session: The database session
            report_date: The date of the report (typically the end of the week)
        """
        super().__init__()

        # Calculate the start and end of the week
        # Assuming the week ends on Sunday and we want the last 7 days
        self.end_of_week = report_date.replace(hour=0, minute=0, second=0, microsecond=0)
        self.start_of_week = self.end_of_week - timedelta(days=7)

        # Get total check-ins for the week and compare with last week
        current_week_checkins = self._get_weekly_checkins(session, self.start_of_week, self.end_of_week)
        last_week_start = self.start_of_week - timedelta(days=7)
        last_week_end = self.end_of_week - timedelta(days=7)
        last_week_checkins = self._get_weekly_checkins(session, last_week_start, last_week_end)

        # Calculate week-over-week change
        checkin_change = 0
        if last_week_checkins > 0:
            checkin_change = int(((current_week_checkins - last_week_checkins) / last_week_checkins) * 100)

        # Find the most active day of the week
        most_active_day, day_count = self._get_most_active_day(session, self.start_of_week, self.end_of_week)

        # Get level-up users for the week
        level_up_users = self._get_level_up_users(session, self.start_of_week, self.end_of_week)

        # Get top score gainers
        top_score_gainers = self._get_top_score_gainers(session, self.start_of_week, self.end_of_week, limit=3)

        # Get newly achieved badges
        new_achievements = self._get_new_achievements(session, self.start_of_week, self.end_of_week)

        # Get most acquired badge
        most_acquired_badge, badge_count = self._get_most_acquired_badge(session, self.start_of_week, self.end_of_week)

        # Get unique records (early birds, consecutive days)
        early_birds = self._get_early_birds(session, self.start_of_week, self.end_of_week, limit=1)
        perfect_attendance = self._get_perfect_attendance(session, self.start_of_week, self.end_of_week)

        # Build the blocks
        self._build_header_block(self.start_of_week, self.end_of_week)
        self._build_summary_block(current_week_checkins, checkin_change, most_active_day, day_count)
        self._build_growth_highlights_block(session, level_up_users, top_score_gainers)
        self._build_achievements_block(new_achievements, most_acquired_badge, badge_count)
        self._build_records_block(early_birds, perfect_attendance)

    def _get_weekly_checkins(self, session: Session, start_date: datetime, end_date: datetime) -> int:
        """Get the number of check-ins for the given date range."""
        return (
            session.query(GuestArrivalInfo)
            .filter(
                GuestArrivalInfo.arrival_time >= start_date,
                GuestArrivalInfo.arrival_time < end_date,
            )
            .count()
        )

    def _get_most_active_day(self, session: Session, start_date: datetime, end_date: datetime) -> tuple[str, int]:
        """Get the most active day of the week in the given date range."""
        # This is a simplified implementation - in real SQL you might want to use date functions
        # to extract the day of week and group by it
        day_counts = {}
        arrivals = (
            session.query(GuestArrivalInfo)
            .filter(
                GuestArrivalInfo.arrival_time >= start_date,
                GuestArrivalInfo.arrival_time < end_date,
            )
            .all()
        )

        for arrival in arrivals:
            day_name = arrival.arrival_time.strftime("%a")  # Get day of week name
            day_counts[day_name] = day_counts.get(day_name, 0) + 1

        if not day_counts:
            return "N/A", 0

        def get_count(key: str) -> int:
            return day_counts[key]

        most_active_day = max(day_counts, key=get_count)
        return most_active_day, day_counts[most_active_day]

    def _get_level_up_users(self, session: Session, start_date: datetime, end_date: datetime) -> list[LevelUpUser]:
        """Get users who leveled up during the given date range using UserInfoRaw for historical data."""
        # Use UserInfoRaw to find level-up events within the date range
        # We need to find distinct user_ids where level_uped is True
        from hikarie_bot.models import UserInfoRaw

        level_up_users_raw = (
            session.query(UserInfoRaw)
            .filter(
                UserInfoRaw.update_datetime >= start_date,
                UserInfoRaw.update_datetime < end_date,
                UserInfoRaw.level_uped,
            )
            .order_by(UserInfoRaw.update_datetime.desc())
            .all()
        )

        # Track unique users since we want only the most recent level-up per user
        unique_users = {}
        for user_raw in level_up_users_raw:
            if user_raw.user_id not in unique_users:
                unique_users[user_raw.user_id] = LevelUpUser(
                    user_id=user_raw.user_id,
                    level=user_raw.level,
                    level_name=user_raw.level_name,
                    update_datetime=user_raw.update_datetime,
                )

        # Convert to list and sort by update_datetime
        result = list(unique_users.values())
        result.sort(key=lambda x: x.update_datetime, reverse=True)

        return result

    def _get_top_score_gainers(
        self, session: Session, start_date: datetime, end_date: datetime, limit: int
    ) -> list[ScoreGainer]:
        """Get top users by score gain during the given date range using UserInfoRaw."""
        # Using UserInfoRaw to track score changes over time
        # We need to find the score difference for each user within the date range

        # Get the latest UserInfoRaw record for each user within the date range
        subquery_latest = (
            session.query(
                UserInfoRaw.user_id,
                func.max(UserInfoRaw.update_datetime).label("max_datetime"),
            )
            .filter(UserInfoRaw.update_datetime < end_date)
            .group_by(UserInfoRaw.user_id)
            .subquery()
        )

        latest_records = (
            session.query(UserInfoRaw)
            .join(
                subquery_latest,
                (UserInfoRaw.user_id == subquery_latest.c.user_id)
                & (UserInfoRaw.update_datetime == subquery_latest.c.max_datetime),
            )
            .subquery()
        )

        # Get the earliest UserInfoRaw record for each user within or before the date range
        subquery_earliest = (
            session.query(
                UserInfoRaw.user_id,
                func.max(UserInfoRaw.update_datetime).label("max_datetime"),
            )
            .filter(UserInfoRaw.update_datetime < start_date)
            .group_by(UserInfoRaw.user_id)
            .subquery()
        )

        earliest_records = (
            session.query(UserInfoRaw)
            .join(
                subquery_earliest,
                (UserInfoRaw.user_id == subquery_earliest.c.user_id)
                & (UserInfoRaw.update_datetime == subquery_earliest.c.max_datetime),
            )
            .subquery()
        )

        # Calculate score difference between latest and earliest records
        # SQLite compatible version (using column name instead of func.desc())
        score_diff_query = (
            session.query(
                latest_records.c.user_id,
                (latest_records.c.current_score - func.coalesce(earliest_records.c.current_score, 0)).label(
                    "score_diff"
                ),
            )
            .outerjoin(earliest_records, latest_records.c.user_id == earliest_records.c.user_id)
            .filter((latest_records.c.update_datetime >= start_date) & (latest_records.c.update_datetime < end_date))
            .order_by(
                # SQLite compatible ordering
                (latest_records.c.current_score - func.coalesce(earliest_records.c.current_score, 0)).desc()
            )
            .limit(limit)
        )

        score_diff = score_diff_query.all()

        result = [ScoreGainer(user_id=record.user_id, score_gained=record.score_diff) for record in score_diff]

        # If we don't have enough records from score diff (perhaps due to lack of historical data),
        # fall back to using GuestArrivalInfo
        if len(result) < limit:
            fallback_limit = limit - len(result)
            already_added = {item.user_id for item in result}

            arrivals = (
                session.query(
                    GuestArrivalInfo.user_id,
                    func.sum(GuestArrivalInfo.acquired_score_sum).label("total_score"),
                )
                .filter(
                    GuestArrivalInfo.arrival_time >= start_date,
                    GuestArrivalInfo.arrival_time <= end_date,
                    ~GuestArrivalInfo.user_id.in_(already_added),
                )
                .group_by(GuestArrivalInfo.user_id)
                .order_by(func.sum(GuestArrivalInfo.acquired_score_sum).desc())
                .limit(fallback_limit)
                .all()
            )

            result.extend(
                [ScoreGainer(user_id=arrival.user_id, score_gained=arrival.total_score) for arrival in arrivals]
            )

        return result

    def _get_new_achievements(
        self, session: Session, start_date: datetime, end_date: datetime
    ) -> list[UserAchievement]:
        """Get new achievements during the given date range."""
        # Convert start_date and end_date to naive UTC if they are timezone-aware
        # This is because SQLAlchemy stores aware datetimes as naive UTC in SQLite by default
        utc_zone = zoneinfo.ZoneInfo("UTC")

        # Ensure start_date and end_date are aware before converting, then make naive UTC
        # If they are already naive, assume they are compatible with DB (less likely for this method's inputs)
        # For this method, start_date/end_date are expected to be aware (from WeeklyMessage constructor)

        naive_utc_start_date = start_date.astimezone(utc_zone).replace(tzinfo=None)
        naive_utc_end_date = end_date.astimezone(utc_zone).replace(tzinfo=None)

        user_badges = (
            session.query(
                UserBadge.user_id,
                UserBadge.badge_id,
                Badge.message,
                UserBadge.initially_acquired_datetime,  # This is stored as naive UTC in DB
            )
            .join(Badge, UserBadge.badge_id == Badge.id)
            .filter(
                UserBadge.initially_acquired_datetime >= naive_utc_start_date,
                UserBadge.initially_acquired_datetime <= naive_utc_end_date,
            )
            .order_by(UserBadge.initially_acquired_datetime.desc())
            .limit(5)
            .all()
        )

        return [
            UserAchievement(
                user_id=user_badge.user_id,
                badge_id=user_badge.badge_id,
                message=user_badge.message,
                achieved_time=user_badge.initially_acquired_datetime,  # This will be naive UTC
            )
            for user_badge in user_badges
        ]

    def _get_most_acquired_badge(
        self, session: Session, start_date: datetime, end_date: datetime
    ) -> tuple[BadgeInfo, int]:
        """Get the most acquired badge during the given date range."""
        # Count achievements by badge
        badge_counts = (
            session.query(
                Achievement.badge_id,
                Badge.message,
                func.count(Achievement.id).label("badge_count"),
            )
            .join(Badge, Achievement.badge_id == Badge.id)
            .filter(
                Achievement.achieved_time >= start_date,
                Achievement.achieved_time <= end_date,
            )
            .group_by(Achievement.badge_id, Badge.message)
            .order_by(func.count(Achievement.id).desc())
            .first()
        )

        if not badge_counts:
            return BadgeInfo(badge_id=None, message="N/A"), 0

        return BadgeInfo(
            badge_id=badge_counts.badge_id,
            message=badge_counts.message,
        ), badge_counts.badge_count

    def _get_early_birds(
        self, session: Session, start_date: datetime, end_date: datetime, limit: int
    ) -> list[EarlyBird]:
        """Get users who checked in earliest during the given date range."""
        # For each day, find the earliest check-in
        all_days = []
        current_date = start_date
        while current_date <= end_date:
            next_day = current_date + timedelta(days=1)
            earliest = (
                session.query(GuestArrivalInfo)
                .filter(
                    GuestArrivalInfo.arrival_time >= current_date,
                    GuestArrivalInfo.arrival_time < next_day,
                )
                .order_by(GuestArrivalInfo.arrival_time)
                .first()
            )

            if earliest:
                all_days.append(EarlyBird(user_id=earliest.user_id, arrival_time=earliest.arrival_time))

            current_date = next_day

        # Sort by arrival time and get the earliest ones
        all_days.sort(key=lambda x: x.arrival_time.time())
        return all_days[:limit]

    def _get_perfect_attendance(self, session: Session, start_date: datetime, end_date: datetime) -> list[str]:
        """Get users who checked in every day during the given date range."""
        # Get all unique days in the date range
        all_days = set()
        current_date = start_date
        while current_date <= end_date:
            all_days.add(current_date.date())
            current_date += timedelta(days=1)

        # Get all users who checked in during the date range
        user_days = {}
        arrivals = (
            session.query(GuestArrivalInfo)
            .filter(
                GuestArrivalInfo.arrival_time >= start_date,
                GuestArrivalInfo.arrival_time <= end_date,
            )
            .all()
        )

        for arrival in arrivals:
            if arrival.user_id not in user_days:
                user_days[arrival.user_id] = set()
            user_days[arrival.user_id].add(arrival.arrival_time.date())

        # Filter users who checked in every day
        perfect_users = []
        for user_id, days in user_days.items():
            if len(days) == len(all_days):
                perfect_users.append(user_id)

        return perfect_users

    def _build_header_block(self, start_date: datetime, end_date: datetime) -> None:
        """Build the header block of the report."""
        self.blocks.append(blocks.HeaderBlock(text=f"出社BOT 週次レポート({start_date:%m/%d}~{end_date:%m/%d})"))
        self.blocks.append(blocks.DividerBlock())

    def _build_summary_block(
        self,
        total_checkins: int,
        checkin_change: int,
        most_active_day: str,
        day_count: int,
    ) -> None:
        """Build the summary block of the report."""
        change_emoji = "📈" if checkin_change >= 0 else "📉"
        change_sign = "+" if checkin_change >= 0 else ""

        self.blocks.append(
            blocks.SectionBlock(
                text=f"*今週の出社総数*: {total_checkins}人 {change_emoji} *前週比*: {change_sign}{checkin_change}%\n"
                f"*最も賑わった日*: {most_active_day} ({day_count}人)"
            )
        )
        self.blocks.append(blocks.DividerBlock())

    def _build_growth_highlights_block(
        self,
        session: Session,
        level_up_users: list[LevelUpUser],
        top_score_gainers: list[ScoreGainer],
    ) -> None:
        """Build the growth highlights block of the report."""
        self.blocks.append(blocks.SectionBlock(text="✨ *成長ハイライト* ✨"))

        # Format level up users text
        level_up_text = "*レベルアップ達成者* 🎉\n"
        if level_up_users:
            level_up_text += "\n".join(
                [
                    f"• <@{user.user_id}> → {user.level_name}"
                    for user in level_up_users[:3]  # Limit to top 3
                ]
            )
        else:
            level_up_text += "今週はレベルアップした人はいませんでした"

        # Format top score gainers text
        score_gainers_text = "*スコア伸び率TOP3* 📈\n"
        if top_score_gainers:
            score_gainers_text += "\n".join(
                [f"• <@{user.user_id}> +{user.score_gained}pt" for user in top_score_gainers]
            )
        else:
            score_gainers_text += "今週はスコア獲得がありませんでした"

        self.blocks.append(
            blocks.SectionBlock(
                fields=[
                    basic_components.MarkdownTextObject(text=level_up_text),
                    basic_components.MarkdownTextObject(text=score_gainers_text),
                ]
            )
        )

        # Add "almost level up" notification if available
        # Find users who are close to leveling up
        almost_level_up_users = self._get_almost_level_up_users(session)
        if almost_level_up_users:
            user = almost_level_up_users[0]  # Take the first user who is closest
            self.blocks.append(
                blocks.ContextBlock(
                    elements=[
                        basic_components.MarkdownTextObject(
                            text=(
                                f"もうすぐレベルアップ!👀 <@{user.user_id}>さんは"
                                f"あと{user.points_needed}ptで「{user.next_level_name}」に!"
                            )
                        )
                    ]
                )
            )

        self.blocks.append(blocks.DividerBlock())

    def _build_achievements_block(
        self,
        new_achievements: list[UserAchievement],
        most_acquired_badge: BadgeInfo,
        badge_count: int,
    ) -> None:
        """Build the achievements block of the report."""
        self.blocks.append(blocks.SectionBlock(text="🏆 *新規解禁実績* 🏆"))

        # Format new achievements text
        new_achievements_text = "*新たに解除された実績*\n"
        if new_achievements:
            # Group by user to show one achievement per user
            user_achievements = {}
            for achievement in new_achievements:
                if achievement.user_id not in user_achievements:
                    user_achievements[achievement.user_id] = achievement

            new_achievements_text += "\n".join(
                [
                    f"• 「{achievement.message}」- <@{achievement.user_id}>さん"
                    for user_id, achievement in list(user_achievements.items())[:2]  # Limit to 2
                ]
            )
        else:
            new_achievements_text += "今週は新たに解除された実績はありませんでした"

        # Format most acquired badge text
        most_acquired_text = "*最も獲得された実績*\n"
        if most_acquired_badge.badge_id is not None:
            most_acquired_text += f"「{most_acquired_badge.message}」- {badge_count}人獲得!"
        else:
            most_acquired_text += "今週は実績獲得がありませんでした"

        self.blocks.append(
            blocks.SectionBlock(
                fields=[
                    basic_components.MarkdownTextObject(text=new_achievements_text),
                    basic_components.MarkdownTextObject(text=most_acquired_text),
                ]
            )
        )

    def _build_records_block(self, early_birds: list[EarlyBird], perfect_attendance: list[str]) -> None:
        """Build the records block of the report."""
        self.blocks.append(blocks.SectionBlock(text="🌟 *特別な記録* 🌟"))

        # Format perfect attendance text
        attendance_text = "*皆勤賞* 👑\n"
        if perfect_attendance:
            attendance_text += "毎日出社した勇者たち\n"
            attendance_text += ", ".join([f"<@{user_id}>" for user_id in perfect_attendance[:5]])  # Limit to 5
        else:
            attendance_text += "今週は毎日出社した人はいませんでした"

        # Format early birds text
        early_bird_text = "*アーリーバード* 🐦\n"
        if early_birds:
            earliest = early_birds[0]
            early_bird_text += f"最も早い出社 {earliest.arrival_time:%H:%M}am <@{earliest.user_id}>さん"
        else:
            early_bird_text += "今週はだれも出社していませんでした"

        self.blocks.append(
            blocks.SectionBlock(
                fields=[
                    basic_components.MarkdownTextObject(text=attendance_text),
                    basic_components.MarkdownTextObject(text=early_bird_text),
                ]
            )
        )

        self.blocks.append(blocks.DividerBlock())

        # Add actions buttons
        self.blocks.append(
            blocks.ActionsBlock(
                elements=[
                    # block_elements.ButtonElement(
                    #     text="詳細ランキングを見る", action_id="view_weekly_details"
                    # ),
                    block_elements.ButtonElement(
                        text="自分の実績をみる",
                        action_id=ActionID.CHECK_ACHIEVEMENT,
                        style="primary",
                    ),
                ]
            )
        )

    def _get_almost_level_up_users(self, session: Session) -> list[AlmostLevelUpUser]:
        """Find users who are close to leveling up, using most recent UserInfoRaw data."""
        # Get the most recent UserInfoRaw record for each user
        # Get user_ids of users who had an arrival in the last week
        recent_arrival_user_ids = (
            session.query(GuestArrivalInfo.user_id)
            .filter(
                GuestArrivalInfo.arrival_time >= self.start_of_week,
                GuestArrivalInfo.arrival_time < self.end_of_week,
            )
            .distinct()
            .all()
        )
        recent_arrival_user_ids = [user_id for (user_id,) in recent_arrival_user_ids]

        if not recent_arrival_user_ids:
            return []

        # Get the most recent UserInfoRaw record for these users
        subquery = (
            session.query(
                UserInfoRaw.user_id,
                func.max(UserInfoRaw.update_datetime).label("max_datetime"),
            )
            .filter(
                UserInfoRaw.update_datetime <= self.end_of_week,
                UserInfoRaw.user_id.in_(recent_arrival_user_ids),
            )
            .group_by(UserInfoRaw.user_id)
            .subquery()
        )

        user_records = (
            session.query(UserInfoRaw)
            .join(
                subquery,
                (UserInfoRaw.user_id == subquery.c.user_id) & (UserInfoRaw.update_datetime == subquery.c.max_datetime),
            )
            .all()
        )

        # Find users who are close to leveling up (less than 20% of points to next level)
        almost_level_up = []
        for user in user_records:
            if (
                user.point_to_next_level > 0
                and user.point_range_to_next_level > 0
                and (user.point_to_next_level <= user.point_range_to_next_level * 0.2)
            ):  # Within 20% of next level
                # We need to determine next level name
                next_level = user.level + 1
                next_level_name = get_level_name(user.current_score + user.point_to_next_level)

                almost_level_up.append(
                    AlmostLevelUpUser(
                        user_id=user.user_id,
                        current_score=user.current_score,
                        points_needed=user.point_to_next_level,
                        next_level=next_level,
                        next_level_name=next_level_name,
                    )
                )

        # Sort by points needed (ascending)
        almost_level_up.sort(key=lambda x: x.points_needed)
        return almost_level_up
