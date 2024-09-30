from collections.abc import Generator

from hikarie_bot.slack_helper import MessageFilter


def test_filter(monkeypatch: Generator) -> None:
    """Test the message filter."""
    # temporarily override the environment variables
    # to avoid the error of the missing environment variables
    monkeypatch.setenv("BOT_ID", "TST")

    message = {
        "bot_id": "TST",
        "text": "ヒカリエは正義 :hikarie:¥n"
        "本日の最速出社申告ユーザ:<@USRIDTST0123> @ 9:00",
    }
    assert MessageFilter.run(message) is True

    message = {
        "bot_id": "TST",
        "text": "<@USRIDTST0123> clicked *出社してる*",
    }
    assert MessageFilter.run(message) is False

    message = {
        "bot_id": "FAIL",
        "text": "ヒカリエは正義 :hikarie:¥n"
        "本日の最速出社申告ユーザ:<@USRIDTST0123> @ 9:00",
    }
    assert MessageFilter.run(message) is False
