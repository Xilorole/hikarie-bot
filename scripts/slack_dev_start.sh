#!/bin/sh
# Start hook for `slack run`. The Slack CLI injects SLACK_BOT_TOKEN / SLACK_APP_TOKEN of the
# local dev app, and the rest of the settings come from .env.dev (it must not contain tokens,
# since settings.py loads it with override=True). Extra hook-protocol args are ignored.
set -e
export DOTENV_PATH="${DOTENV_PATH:-.env.dev}"
if [ ! -f "$DOTENV_PATH" ]; then
    echo "$DOTENV_PATH not found; copy .env.dev.template and fill it in" >&2
    exit 1
fi

# BOT_ID / SLACK_WORKSPACE_ID / channels belong to the dev app, so derive them from its token
exports="$(uv run python scripts/slack_dev_bootstrap.py)"
eval "$exports"

exec uv run python -m hikarie_bot start --dev
