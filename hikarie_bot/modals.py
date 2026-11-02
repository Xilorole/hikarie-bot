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
from sqlalchemy.orm import Session

from hikarie_bot.constants import (
    ACHIEVED_BADGE_IMAGE_URL,
    BADGE_TYPES_TO_CHECK,
    CONTEXT_ITEM_MAX,
    NOT_ACHIEVED_BADGE_IMAGE_URL,
    TAKEN_6XXX_BADGE_IMAGE_URL,
)
from hikarie_bot.constants import (
    ACHIEVED_BADGE_IMAGE_URL as ARRIVED_IMAGE_URL,
)
from hikarie_bot.constants import (
    NOT_ACHIEVED_BADGE_IMAGE_URL as NOT_ARRIVED_IMAGE_URL,
)
from hikarie_bot.db_data.badges import KIRIBANS
from hikarie_bot.models import (
    Achievement,
    Badge,
    BadgeType,
    GuestArrivalInfo,
    User,
    UserBadge,
)
from hikarie_bot.utils import (
    get_current_jst_datetime,
    get_current_level_point,
    get_level,
    get_level_name,
    get_point_range_to_next_level,
    get_point_to_next_level,
    is_level_uped,
    is_max_level,
    is_max_level_reached,
)

# Constants
KIRIBAN_BADGE_TYPE_ID = 6


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

    def __init__(self, session: Session, user_id: str, jst_datetime: datetime) -> None:
        """Initialize the PointGetMessage with the user ID and time.

        initial_arrival tells whether this was the day's first arrival, by the computed rank.
        """
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
        # show at least one cell: a bar of spaces only renders as an empty inline code in Slack
        digits = max(1, (experience_rate + 10 - 1) // 10)
        point_rate_text = "█" * digits + " " * (10 - digits)

        # the level does not go beyond the upper limit
        if is_max_level(current_point):
            next_level_text = "*上限に到達*"
            progress_text = f"`{point_rate_text}` | *100%*"
        else:
            next_level_text = f"*{point_to_next_level}pt*"
            progress_text = f"`{point_rate_text}` | *{experience_rate:>3d}%* (*+{experience_add_up_rate}%*)"
        if is_max_level_reached(previous_point, current_point):
            level_up_text = " *上限に到達!* :crown: "
        elif level_up_flag:
            level_up_text = " *LvUP!* :star2: "
        else:
            level_up_text = ""

        self.initial_arrival = arrival.arrival_rank == 1
        initial_arrival_text = "最速" if self.initial_arrival else ""
        hikarie_text = " :hikarie:" if self.initial_arrival else ""

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

    def __init__(self, session: Session, user_id: str, jst_datetime: datetime | None = None) -> None:
        """Initialize the AchievementView with the user ID.

        jst_datetime is the "today" of the attendance history (default: now).
        """
        super().__init__(type="modal", title="Achievements", close="閉じる")

        self.session = session
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

    def _generate_badge_elements_for_type(self, badge_type: BadgeType) -> list[block_elements.ImageElement]:
        """Generate badge elements for a specific badge type."""
        elements = []
        badges = self.session.query(Badge).filter(Badge.badge_type_id == badge_type.id).all()

        # 6xx番台（キリ番バッジ）の場合は取得済みのみ表示
        if badge_type.id == KIRIBAN_BADGE_TYPE_ID:
            for badge in badges:
                user_badge = (
                    self.session.query(UserBadge)
                    .filter(UserBadge.user_id == self.user_id, UserBadge.badge_id == badge.id)
                    .one_or_none()
                )
                if user_badge:
                    element = block_elements.ImageElement(
                        image_url=ACHIEVED_BADGE_IMAGE_URL,
                        alt_text=(
                            f"【{badge.message}】{badge.condition} @ {user_badge.initially_acquired_datetime:%Y-%m-%d}"
                        ),
                    )
                    elements.append(element)
        else:
            # 他のバッジタイプは従来通り全て表示
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
        if self._is_kiriban_badge(badge.id):
            return self._create_kiriban_badge_element(badge)
        return block_elements.ImageElement(
            image_url=NOT_ACHIEVED_BADGE_IMAGE_URL,
            alt_text=f"【{badge.message}】???",
        )

    def _create_kiriban_badge_element(self, badge: Badge) -> block_elements.ImageElement:
        """Create element for kiriban special badges."""
        other_user_badge = self.session.query(UserBadge).filter(UserBadge.badge_id == badge.id).first()

        if other_user_badge is not None:
            return block_elements.ImageElement(
                image_url=TAKEN_6XXX_BADGE_IMAGE_URL,
                alt_text=f"【{badge.message}】他のユーザーが獲得済み",
            )
        return block_elements.ImageElement(
            image_url=NOT_ACHIEVED_BADGE_IMAGE_URL,
            alt_text=f"【{badge.message}】???",
        )

    def _is_kiriban_badge(self, badge_id: int) -> bool:
        """Check if badge is a kiriban badge (6000 series)."""
        return 6000 <= badge_id < 7000  # noqa: PLR2004

    def _get_next_kiriban_badge_id(self) -> int | None:
        """Get the next kiriban badge ID that should be displayed.

        Returns the next unachieved kiriban badge ID if the previous one is achieved,
        or the first kiriban badge ID if none are achieved yet.
        """
        # Check from the first kiriban
        for i, kiriban in enumerate(KIRIBANS):
            user_badge = (
                self.session.query(UserBadge)
                .filter(UserBadge.user_id == self.user_id, UserBadge.badge_id == kiriban.id)
                .first()
            )

            if not user_badge:  # This kiriban is not achieved
                if i == 0:  # First kiriban
                    return kiriban.id

                # Check if previous kiriban is achieved
                prev_kiriban = KIRIBANS[i - 1]
                prev_user_badge = (
                    self.session.query(UserBadge)
                    .filter(UserBadge.user_id == self.user_id, UserBadge.badge_id == prev_kiriban.id)
                    .first()
                )

                if prev_user_badge:  # Previous kiriban is achieved
                    return kiriban.id

                # If previous kiriban is not achieved, don't show this one
                return None

        return None  # All kiribans are achieved

    def _get_badge_achievement_count(self, badge_id: int) -> int:
        """Get the number of times a user has achieved a specific badge."""
        count_query = (
            self.session.query(UserBadge)
            .filter(UserBadge.user_id == self.user_id, UserBadge.badge_id == badge_id)
            .order_by(UserBadge.last_acquired_datetime.desc())
            .one_or_none()
        )
        return count_query.count if count_query else 0

    def _get_current_arrival_count(self) -> int:
        """Get the current total arrival count for all users."""
        return self.session.query(GuestArrivalInfo).count()

    def _get_next_kiriban_info(self, current_count: int) -> tuple[int, int] | None:
        """Get the next kiriban badge info (badge_id, kiriban_count).

        Args:
            current_count: Current total arrival count

        Returns:
            Tuple of (badge_id, kiriban_count) for the next kiriban, or None if no more
        """
        return next(((kiriban.id, kiriban.number) for kiriban in KIRIBANS if current_count < kiriban.number), None)

    def _generate_kiriban_status_text(self) -> str:
        """Generate kiriban status text showing progress to next kiriban."""
        current_count = self._get_current_arrival_count()
        next_kiriban = self._get_next_kiriban_info(current_count)

        if next_kiriban is None:
            return "現在実装されているキリ番は全て達成可能範囲を超えています。今後の実装をお待ちください。"

        _badge_id, kiriban_count = next_kiriban
        remaining = kiriban_count - current_count

        return f"次のキリ番まで: あと *{remaining}回* ({kiriban_count}回目)"

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
        current_date = self.jst_datetime or get_current_jst_datetime()
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

        if not achieved_user_badges:
            return []

        # RichTextBlockの要素を構築 - 各バッジとその詳細をペアで作成
        rich_text_elements = []

        for user_badge, badge in achieved_user_badges:
            # 獲得回数を取得
            achievement_count = self._get_badge_achievement_count(badge.id)

            # トップレベル: ID、タイトル、獲得日
            initial_date = user_badge.initially_acquired_datetime.strftime("%Y-%m-%d")
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
                    # キリ番バッジ（6000番台）の特別処理
                    if self._is_kiriban_badge(badge.id):
                        # 他のユーザーが獲得済みの場合は表示しない
                        other_user_badge = self.session.query(UserBadge).filter(UserBadge.badge_id == badge.id).first()
                        if other_user_badge is not None:
                            continue

                        # 次に獲得すべきキリ番のみ表示
                        next_kiriban_id = self._get_next_kiriban_badge_id()
                        if badge.id != next_kiriban_id:
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
