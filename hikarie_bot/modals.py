from datetime import datetime, timedelta
from textwrap import dedent

from loguru import logger
from slack_sdk.models.blocks import (
    Block,
    MarkdownTextObject,
    basic_components,
    block_elements,
    blocks,
)
from sqlalchemy.orm import Session

from hikarie_bot.models import Achievement, Badge, GuestArrivalInfo, User, UserBadge
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
                blocks.SectionBlock(text="ヒカリエに出社してる？"),  # noqa: RUF001
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
                f"*{user.arrival_time:%H:%M}* : <@{user.user_id}>"
                f"{':crown:' if idx == 0 else ''}"
                for idx, user in enumerate(arrived_users)
            ]
        )
        logger.info(arrived_users)

        self.blocks.extend(
            [
                blocks.SectionBlock(text="ヒカリエに出社してる？"),  # noqa: RUF001
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
                    + "\n".join(
                        [
                            f"*{user.arrival_time:%H:%M}* : <@{user.user_id}>"
                            for user in arrived_users
                        ]
                    ),
                ),
            ]
        )


class FastestArrivalMessage(BaseMessage):
    """Class for creating the fastest arrival Slack message."""

    def __init__(self, user_id: str, jst_datetime: datetime) -> None:
        """Initialize the FastestArrivalMessage with the fastest arrival user ID and time."""  # noqa: E501
        super().__init__()
        self.blocks.extend(
            [
                blocks.SectionBlock(
                    text="ヒカリエは正義 :hikarie:\n"
                    f"本日の最速出社: <@{user_id}> @ {jst_datetime:%Y-%m-%d %H:%M:%S}",
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
        point_rate_text = (
            "█" + "█" * (experience_rate // 10) + " " * (10 - experience_rate // 10)
        )

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
        achievements_text = "\n".join(
            [f" - {badge.message}:*+{badge.score}pt*" for badge in badges]
        )

        context = dedent(
            f"""\
            かたがき: *{level_name}* (lv{level})
            つぎのレベルまで: *{point_to_next_level}pt*
            しんこうど: `{point_rate_text}` | *{experience_rate:>3d}%* (*+{experience_add_up_rate}%*)
            うちわけ:
            """  # noqa: E501
        ) + (achievements_text)

        self.blocks.extend(
            [
                blocks.SectionBlock(
                    text=f"*{arrive_time:%H:%M}* "
                    f"{initial_arrival_text}出社登録しました！{hikarie_text}"  # noqa: RUF001
                    f"\n<@{user_id}>さんのポイント "
                    f"{previous_point} → *{current_point}* "
                    f"(*+{score_addup}{' レベルアップ！' if level_up_flag else ''}*)"  # noqa: RUF001
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
                    text=f"本日の出社登録はすでに完了しています\n"
                    f"<@{user_id}> @ {jst_datetime:%Y-%m-%d %H:%M:%S}",
                    block_id=BlockID.ALREADY_REGISTERED_REPLY,
                )
            ]
        )


class AchievementMessage(BaseMessage):
    """Class for creating the achievement Slack message."""

    def __init__(
        self,
        session: Session,
        user_id: str,
    ) -> None:
        """Initialize the AchievementMessage with the user ID."""
        super().__init__()

        user_badges = (
            session.query(UserBadge).filter(UserBadge.user_id == user_id).all()
        )
        self.blocks.extend(
            [
                blocks.SectionBlock(text=f"<@{user_id}>が獲得したバッジ:\n"),
                blocks.DividerBlock(),
            ]
        )
        for user_badge in sorted(user_badges, key=lambda x: x.badge_id):
            self.blocks.extend(
                [
                    blocks.SectionBlock(
                        text=f"`{user_badge.badge_id}`  : *{user_badge.badge.message}* [{user_badge.badge.score}pt x{user_badge.count}]",  # noqa: E501
                        fields=[
                            MarkdownTextObject(
                                text="*取得条件*",
                            ),
                            MarkdownTextObject(
                                text="*初めて取得した日*",
                            ),
                            MarkdownTextObject(
                                text=f"{user_badge.badge.condition}",
                            ),
                            MarkdownTextObject(
                                text=f"{user_badge.initially_acquired_datetime:%Y-%m-%d}",
                            ),
                        ],
                    ),
                    blocks.DividerBlock(),
                ]
            )
