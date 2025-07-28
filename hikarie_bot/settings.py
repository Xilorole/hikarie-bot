import os

from dotenv import load_dotenv

from hikarie_bot.exceptions import EnvironmentVariableNotFoundError

load_dotenv(override=True)

# slack.channel
OUTPUT_CHANNEL = os.environ.get("OUTPUT_CHANNEL", "")
LOG_CHANNEL = os.environ.get("LOG_CHANNEL", "")

# slack.user
BOT_ID = os.environ.get("BOT_ID", "")
V1_BOT_ID = os.environ.get("V1_BOT_ID", "")
V2_BOT_ID = os.environ.get("V2_BOT_ID", "")
ADMIN = os.environ.get("ADMIN", "")

# slack.workspace
SLACK_WORKSPACE_ID = os.environ.get("SLACK_WORKSPACE_ID", "")

# auth
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN", "")

for env, env_str in [
    (OUTPUT_CHANNEL, "OUTPUT_CHANNEL"),
    (LOG_CHANNEL, "LOG_CHANNEL"),
    (BOT_ID, "BOT_ID"),
    (V1_BOT_ID, "V1_BOT_ID"),
    (V2_BOT_ID, "V2_BOT_ID"),
    (ADMIN, "ADMIN"),
    (SLACK_WORKSPACE_ID, "SLACK_WORKSPACE_ID"),
    (SLACK_BOT_TOKEN, "SLACK_BOT_TOKEN"),
    (SLACK_APP_TOKEN, "SLACK_APP_TOKEN"),
]:
    if env == "" and os.environ.get("ENV") not in ["dev", "test"] and env_str != "SLACK_WORKSPACE_ID":
        raise EnvironmentVariableNotFoundError(env_str)


# database
DATABASE_URL = os.environ.get("URL", "sqlite:///:memory:")

# log
LOGURU_LEVEL = os.environ.get("LOGURU_LEVEL", "DEBUG")
