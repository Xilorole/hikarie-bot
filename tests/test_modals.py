import zoneinfo
from datetime import datetime
from textwrap import dedent

from sqlalchemy.orm import Session, sessionmaker

from hikarie_bot.curd import initially_insert_badge_data, insert_arrival_action
from hikarie_bot.modals import (
    AchievementMessage,
    AlreadyRegisteredMessage,
    FastestArrivalMessage,
    InitialMessage,
    PointGetMessage,
    RegistryMessage,
)


def test_initial_message() -> None:
    """Test the initial message."""
    message = InitialMessage()
    assert message.to_text() == "ヒカリエに出社してる？"  # noqa: RUF001
    assert message.render() == [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "ヒカリエに出社してる？"},  # noqa: RUF001
        },
        {
            "type": "actions",
            "block_id": "FASTEST_ARRIVAL",
            "elements": [
                {
                    "type": "button",
                    "style": "primary",
                    "text": {
                        "type": "plain_text",
                        "text": "最速出社した",
                        "emoji": True,
                    },
                    "action_id": "FASTEST_ARRIVAL",
                },
                {
                    "action_id": "CHECK_ACHIEVEMENT",
                    "text": {
                        "emoji": True,
                        "text": "実績を確認",
                        "type": "plain_text",
                    },
                    "type": "button",
                },
            ],
        },
    ]


def test_registry_message(temp_db: sessionmaker[Session]) -> None:
    """Test the second arrived user has lower point."""
    session = temp_db()
    initially_insert_badge_data(session=session)

    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 1, 1, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user_1st",
    )
    message = RegistryMessage(
        session=session,
        jst_datetime=datetime(
            2024, 1, 1, 7, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
    )
    assert message.render() == [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "ヒカリエに出社してる？"},  # noqa: RUF001
        },
        {
            "type": "actions",
            "block_id": "ARRIVED_OFFICE",
            "elements": [
                {
                    "type": "button",
                    "action_id": "ARRIVED_OFFICE",
                    "text": {
                        "type": "plain_text",
                        "text": "出社した",
                        "emoji": True,
                    },
                },
                {
                    "action_id": "CHECK_ACHIEVEMENT",
                    "text": {
                        "emoji": True,
                        "text": "実績を確認",
                        "type": "plain_text",
                    },
                    "type": "button",
                },
            ],
        },
        {
            "type": "divider",
        },
        {
            "text": {
                "text": "本日の出社ユーザー :hikarie: :\n*06:00* : <@test_user_1st>",
                "type": "mrkdwn",
            },
            "type": "section",
        },
    ]


def test_registry_message_2(temp_db: sessionmaker[Session]) -> None:
    """Test the second arrived user has lower point."""
    session = temp_db()
    initially_insert_badge_data(session=session)

    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 1, 1, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user_1st",
    )
    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 1, 1, 6, 1, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user_2nd",
    )
    message = RegistryMessage(
        session=session,
        jst_datetime=datetime(
            2024, 1, 1, 7, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
    )
    assert message.render() == [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "ヒカリエに出社してる？"},  # noqa: RUF001
        },
        {
            "type": "actions",
            "block_id": "ARRIVED_OFFICE",
            "elements": [
                {
                    "type": "button",
                    "action_id": "ARRIVED_OFFICE",
                    "text": {
                        "type": "plain_text",
                        "text": "出社した",
                        "emoji": True,
                    },
                },
                {
                    "action_id": "CHECK_ACHIEVEMENT",
                    "text": {
                        "emoji": True,
                        "text": "実績を確認",
                        "type": "plain_text",
                    },
                    "type": "button",
                },
            ],
        },
        {
            "type": "divider",
        },
        {
            "text": {
                "text": dedent("""\
                        本日の出社ユーザー :hikarie: :
                        *06:00* : <@test_user_1st>
                        *06:01* : <@test_user_2nd>"""),
                "type": "mrkdwn",
            },
            "type": "section",
        },
    ]


def test_fastest_arrival_message(temp_db: sessionmaker[Session]) -> None:
    """Test the fastest arrival message."""
    session = temp_db()
    initially_insert_badge_data(session=session)

    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 1, 1, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user",
    )
    message = FastestArrivalMessage(
        user_id="test_user",
        jst_datetime=datetime(
            2024, 1, 1, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
    )

    assert message.render() == [
        {
            "type": "section",
            "block_id": "FASTEST_ARRIVAL_REPLY",
            "text": {
                "type": "mrkdwn",
                "text": "ヒカリエは正義 :hikarie:\n"
                "本日の最速出社: <@test_user> @ 2024-01-01 06:00:00",
            },
        }
    ]


def test_point_get_message(temp_db: sessionmaker[Session]) -> None:
    """Test the point get message."""
    session = temp_db()
    initially_insert_badge_data(session=session)

    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 1, 1, 7, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user",
    )

    message = PointGetMessage(
        session,
        user_id="test_user",
        jst_datetime=datetime(
            2024, 1, 1, 7, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        initial_arrival=True,
    )

    assert message.render() == [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*07:00* 最速出社登録しました！ :hikarie:\n"  # noqa: RUF001
                "<@test_user>さんのポイント 0 → *7* (*+7*)",
            },
        },
        {
            "type": "divider",
        },
        {
            "elements": [
                {
                    "text": "かたがき: *かけだしのかいしゃいん* (lv1)\n"
                    "つぎのレベルまで: *13pt*\n"
                    "しんこうど: `████      ` | * 35%* (*+35%*)\n"
                    "うちわけ:\n"
                    " - はじめての出社登録:*+2pt*\n"
                    " - 最速出社:*+2pt*\n"
                    " - 朝型出社:*+3pt*",
                    "type": "mrkdwn",
                },
            ],
            "type": "context",
        },
        {
            "type": "divider",
        },
    ]


def test_already_registered_message(temp_db: sessionmaker[Session]) -> None:
    """Test the already registered message."""
    session = temp_db()
    initially_insert_badge_data(session=session)

    message = AlreadyRegisteredMessage(
        user_id="test_user",
        jst_datetime=datetime(
            2024, 1, 1, 6, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
    )

    assert message.render() == [
        {
            "type": "section",
            "block_id": "ALREADY_REGISTERED_REPLY",
            "text": {
                "type": "mrkdwn",
                "text": "本日の出社登録はすでに完了しています\n"
                "<@test_user> @ 2024-01-01 06:00:00",
            },
        }
    ]


def test_achievement_message(temp_db: sessionmaker[Session]) -> None:
    """Test the achievement message."""
    session = temp_db()
    initially_insert_badge_data(session=session)

    insert_arrival_action(
        session=session,
        jst_datetime=datetime(
            2024, 1, 1, 7, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Tokyo")
        ),
        user_id="test_user",
    )

    message = AchievementMessage(
        session=session,
        user_id="test_user",
    )

    assert message.render() == [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "<@test_user>が獲得したバッジ:\n",
            },
        },
        {
            "type": "divider",
        },
        {
            "fields": [
                {
                    "text": "*取得条件*",
                    "type": "mrkdwn",
                },
                {
                    "text": "*初めて取得した日*",
                    "type": "mrkdwn",
                },
                {
                    "text": "出社登録BOTを初めて利用した",
                    "type": "mrkdwn",
                },
                {
                    "text": "2024-01-01",
                    "type": "mrkdwn",
                },
            ],
            "text": {
                "text": "`101`  : *はじめての出社登録* [2pt x1]",
                "type": "mrkdwn",
            },
            "type": "section",
        },
        {
            "type": "divider",
        },
        {
            "fields": [
                {
                    "text": "*取得条件*",
                    "type": "mrkdwn",
                },
                {
                    "text": "*初めて取得した日*",
                    "type": "mrkdwn",
                },
                {
                    "text": "最速で出社登録を行った",
                    "type": "mrkdwn",
                },
                {
                    "text": "2024-01-01",
                    "type": "mrkdwn",
                },
            ],
            "text": {
                "text": "`201`  : *最速出社* [2pt x1]",
                "type": "mrkdwn",
            },
            "type": "section",
        },
        {
            "type": "divider",
        },
        {
            "fields": [
                {
                    "text": "*取得条件*",
                    "type": "mrkdwn",
                },
                {
                    "text": "*初めて取得した日*",
                    "type": "mrkdwn",
                },
                {
                    "text": "7-9時の間に出社登録をした",
                    "type": "mrkdwn",
                },
                {
                    "text": "2024-01-01",
                    "type": "mrkdwn",
                },
            ],
            "text": {
                "text": "`501`  : *朝型出社* [3pt x1]",
                "type": "mrkdwn",
            },
            "type": "section",
        },
        {
            "type": "divider",
        },
    ]
