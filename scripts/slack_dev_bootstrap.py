"""Prepare the dev workspace for `slack run` and print the derived settings as shell exports.

Uses the dev app's bot token injected by the Slack CLI to resolve BOT_ID / SLACK_WORKSPACE_ID,
and to find or create the output / log channels, join them and invite ADMIN.
"""

import json
import os
import shlex
import sys
from pathlib import Path

from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

CHANNEL_NAMES = {
    "OUTPUT_CHANNEL": os.environ.get("DEV_OUTPUT_CHANNEL_NAME", "prd"),
    "LOG_CHANNEL": os.environ.get("DEV_LOG_CHANNEL_NAME", "log"),
}


def find_channel(client: WebClient, name: str) -> dict | None:
    """Return the public channel with the given name, if any."""
    for page in client.conversations_list(types="public_channel", exclude_archived=True, limit=1000):
        for channel in page["channels"]:
            if channel["name"] == name:
                return channel
    return None


def ensure_channel(client: WebClient, name: str, admin: str) -> str:
    """Find or create the channel, make sure the bot is in it and invite the admin."""
    channel = find_channel(client, name)
    if channel is None:
        channel = client.conversations_create(name=name)["channel"]
        print(f"created #{name} ({channel['id']})", file=sys.stderr)
    elif not channel.get("is_member"):
        client.conversations_join(channel=channel["id"])

    if admin:
        try:
            client.conversations_invite(channel=channel["id"], users=admin)
        except SlackApiError as e:
            if e.response["error"] != "already_in_channel":
                raise
    return channel["id"]


def dev_app_id(team_id: str) -> str | None:
    """Return the dev app's ID in the workspace from the Slack CLI's .slack/apps.dev.json, if it is there."""
    try:
        apps = json.loads(Path(".slack/apps.dev.json").read_text())
    except OSError, ValueError:
        return None
    return apps.get(team_id, {}).get("app_id")


def main() -> None:
    """Print `export KEY=value` lines for the dev settings."""
    load_dotenv(os.environ.get("DOTENV_PATH", ".env.dev"), override=True)
    client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
    auth = client.auth_test()

    exports = {"BOT_ID": auth["bot_id"], "SLACK_WORKSPACE_ID": auth["team_id"]}
    if app_id := dev_app_id(auth["team_id"]):
        exports["SLACK_APP_ID"] = app_id
    for key, name in CHANNEL_NAMES.items():
        exports[key] = ensure_channel(client, name, os.environ.get("ADMIN", ""))

    print("export " + " ".join(f"{key}={shlex.quote(value)}" for key, value in exports.items()))


if __name__ == "__main__":
    main()
