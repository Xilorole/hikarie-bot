"""Modal build command for development and testing purposes."""

import json
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

import asyncclick as click
from sqlalchemy.orm import Session

from hikarie_bot.constants import MAX_URL_DISPLAY_LENGTH
from hikarie_bot.curd import initially_insert_badge_data, insert_arrival_action
from hikarie_bot.modals import AchievementView
from hikarie_bot.models import User, get_db
from hikarie_bot.settings import SLACK_WORKSPACE_ID
from hikarie_bot.utils import get_current_jst_datetime


def create_block_kit_url(blocks: list[dict[str, Any]], workspace_id: str) -> str:
    """Create a Block Kit Builder URL for the given blocks.

    Args:
        blocks: List of Slack block dictionaries
        workspace_id: Slack workspace ID

    Returns:
        Block Kit Builder URL
    """
    block_kit_json = {"blocks": blocks}
    encoded_json = urllib.parse.quote(json.dumps(block_kit_json))
    return f"https://app.slack.com/block-kit-builder/{workspace_id}#{encoded_json}"


def create_clickable_link(url: str, display_text: str) -> str:
    """Create a clickable terminal link using ANSI escape sequences.

    Args:
        url: The URL to link to
        display_text: The text to display for the link

    Returns:
        ANSI-formatted clickable link string
    """
    # OSC 8 escape sequence for clickable links
    # the format: \033]8;;URL\033\\DISPLAY_TEXT\033]8;;\033\\
    return f"\033]8;;{url}\033\\{display_text}\033]8;;\033\\"


def ensure_test_modals_directory() -> Path:
    """Ensure the test_modals directory exists and return its path."""
    test_modals_dir = Path("test_modals")
    test_modals_dir.mkdir(exist_ok=True)
    return test_modals_dir


def setup_test_data(session: Session) -> str:
    """Set up test data in the database and return a test user ID."""
    # Initialize badge data
    initially_insert_badge_data(session)

    # Create a test user with some data
    test_user_id = "U12345TEST"

    # Add a test user to the User table
    test_user = User(
        id=test_user_id,
        current_score=150,
        previous_score=100,
        update_datetime=get_current_jst_datetime(),
        level=3,
        level_name="せんぱいのかいしゃいん",
        level_uped=False,
        point_to_next_level=50,
        point_range_to_next_level=200,
        current_level_point=150,
    )
    session.add(test_user)

    # Add some arrival data to trigger badge acquisition
    import zoneinfo

    jst = zoneinfo.ZoneInfo("Asia/Tokyo")
    arrival_times = [
        datetime(2025, 1, 1, 7, 0, 0, tzinfo=jst),  # Morning arrival
        datetime(2025, 1, 2, 8, 30, 0, tzinfo=jst),  # Regular arrival
        datetime(2025, 1, 3, 6, 15, 0, tzinfo=jst),  # Early arrival
        datetime(2025, 7, 25, 6, 15, 0, tzinfo=jst),  # Early arrival
        datetime(2025, 7, 26, 6, 15, 0, tzinfo=jst),  # Early arrival
        datetime(2025, 7, 27, 6, 15, 0, tzinfo=jst),  # Early arrival
    ]

    for arrival_time in arrival_times:
        insert_arrival_action(session, arrival_time, test_user_id)

    session.commit()
    return test_user_id


@click.command()
@click.option("--user-id", default=None, help="Specific user ID to use for modal generation")
def build_modals(user_id: str | None = None) -> None:
    """Build modal JSON files and generate Block Kit Builder URLs.

    This command creates JSON files for Slack modals with actual database content
    and generates corresponding Block Kit Builder URLs for visual testing.
    """
    if not SLACK_WORKSPACE_ID:
        click.echo("❌ SLACK_WORKSPACE_ID is not set in environment variables")
        click.echo("Please set SLACK_WORKSPACE_ID in your .env file")
        return

    # Ensure test_modals directory exists
    test_modals_dir = ensure_test_modals_directory()

    with get_db() as session:
        # Setup test data if no specific user ID is provided
        if user_id is None:
            user_id = setup_test_data(session)
            click.echo(f"📊 Created test data for user: {user_id}")

        # Generate Achievement Modal
        achievement_view = AchievementView(session=session, user_id=user_id)
        achievement_blocks = [block.to_dict() for block in achievement_view.blocks]

        # Create modal view JSON
        modal_json = {
            "type": "modal",
            "title": {"type": "plain_text", "text": "Achievements"},
            "close": {"type": "plain_text", "text": "閉じる"},
            "blocks": achievement_blocks,
        }

        # Write JSON file
        json_file = test_modals_dir / "achievement_modal.json"
        with json_file.open("w", encoding="utf-8") as f:
            json.dump(modal_json, f, ensure_ascii=False, indent=2)

        # Generate Block Kit Builder URL
        block_kit_url = create_block_kit_url(achievement_blocks, SLACK_WORKSPACE_ID)
        clickable_url = create_clickable_link(block_kit_url, "🔗 Block Kit Builder (Click to open)")

        click.echo("✅ Achievement Modal generated:")
        click.echo(f"   📁 JSON file: {json_file}")
        click.echo(f"   {clickable_url}")
        click.echo(
            f"   📋 Raw URL: {block_kit_url[:MAX_URL_DISPLAY_LENGTH]}..."
            if len(block_kit_url) > MAX_URL_DISPLAY_LENGTH
            else f"   📋 Raw URL: {block_kit_url}"
        )
        click.echo()

    click.echo("🎉 Modal generation completed!")
    click.echo(f"📂 All files saved in: {test_modals_dir.absolute()}")


if __name__ == "__main__":
    build_modals()
