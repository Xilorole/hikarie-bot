from datetime import datetime, timedelta

from slack_sdk.models.blocks import (
    BlockElement,
    basic_components,
    block_elements,
    blocks,
)
from sqlalchemy.orm import Session

from hikarie_bot.models import GuestArrivalInfo, User
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


class BlockID:
    """Class for storing the block IDs used in the Slack app."""

    FASTEST_ARRIVAL = "FASTEST_ARRIVAL"
    FASTEST_ARRIVAL_REPLY = "FASTEST_ARRIVAL_REPLY"
    ARRIVED_OFFICE = "ARRIVED_OFFICE"


class BaseMessage:
    """Base class for creating Slack messages with blocks."""

    def __init__(self) -> None:
        """Initialize the BaseMessage with an empty list of blocks."""
        self.blocks: list[BlockElement] = []

    def render(self) -> list[dict]:
        """Render the blocks to a list of dictionaries."""
        return [block.to_dict() for block in self.blocks]

    def to_text(self) -> str:
        """Convert the blocks to a text."""
        # block.text is a TextObject, so we need to check if block has a text attribute
        return "\n".join(
            [block.text.text for block in self.blocks if hasattr(block, "text")]
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
                        )
                    ],
                    block_id=BlockID.FASTEST_ARRIVAL,
                ),
            ]
        )


class RegistryMessage(BaseMessage):
    """Class for creating the registry Slack message with a question and a button."""

    def __init__(self) -> None:
        """Initialize the RegistryMessage with a question and a button."""
        super().__init__()
        self.blocks.extend(
            [
                blocks.SectionBlock(text="ヒカリエに出社してる？"),  # noqa: RUF001
                blocks.ActionsBlock(
                    elements=[
                        block_elements.ButtonElement(
                            text="出社した",
                            action_id=ActionID.ARRIVED_OFFICE,
                        )
                    ],
                    block_id=BlockID.ARRIVED_OFFICE,
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

    def __init__(self, session: Session, user_id: str, jst_datetime: datetime) -> None:
        """Initialize the PointGetMessage with the user ID and time."""
        super().__init__()

        ## variable
        score = session.query(User).filter(User.id == user_id).first()

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
        time_score = arrival.acquired_time_score
        fastest_score = arrival.acquired_rank_score
        straight_flash_score = arrival.straight_flash_score

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

        time_score_text = {
            3: "9時までの出社:*+3pt*",
            2: "11時までの出社:*+2pt*",
            1: "11時以降の出社:*+1pt*",
            0: "18時を過ぎるとポイント付与はありません！また明日！",  # noqa: RUF001
        }.get(time_score)

        fastest_score_text = {
            2: "最速出社:*+2pt*",
            0: "",
        }.get(fastest_score)

        straight_flash_score_text = {
            3: "ストレートフラッ出社:*+3pt*",
            0: "",
        }.get(straight_flash_score)

        self.blocks.extend(
            [
                blocks.SectionBlock(
                    text=f"*{arrive_time:%H:%M}* 出社登録しました！"  # noqa: RUF001
                    f"\n<@{user_id}>さんのポイント "
                    f"{previous_point} → *{current_point}* "
                    f"(*+{score_addup}{' レベルアップ！' if level_up_flag else ''}*)"  # noqa: RUF001
                ),
                blocks.DividerBlock(),
                blocks.ContextBlock(
                    elements=[
                        basic_components.MarkdownTextObject(
                            text=f"かたがき: *{level_name}* (lv{level})"
                            f"\nつぎのレベルまで: *{point_to_next_level}pt*"
                            f"\nしんこうど: `{point_rate_text}` "
                            f"| *{experience_rate:>3d}%* "
                            f"(*+{experience_add_up_rate}%*)"
                            f"\nうちわけ: {time_score_text} {fastest_score_text} "
                            f"{straight_flash_score_text}"
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
                    text=f"本日の出社登録はすでに完了しています"
                    f"\n<@{user_id}> @ {jst_datetime:%Y-%m-%d %H:%M:%S}",
                    block_id=BlockID.ALREADY_REGISTERED_REPLY,
                )
            ]
        )
