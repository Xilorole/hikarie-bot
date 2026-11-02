# hikarie-bot

Slack bot that records office arrivals (button presses in one channel) and awards badges and points.
Why the data works the way it does: `docs/design/data-architecture.md` (Japanese). Deploy: `docs/deploy/rancher.md`.

## Data model

- `arrival_event` is the only source of truth: append-only, deduplicated by Slack message ts; the first event of a user's JST day counts.
- `GuestArrivalInfo`, `Achievement`, `User`, `UserInfoRaw` and `UserBadge` are derived. `sync.rebuild_derived_tables` deletes and recomputes them from all events on every startup and every button press, so never write to them; change the rules in `engine.py`.
- A rule change rewrites everyone's past points and badges on the next deploy. To affect only later arrivals, gate the rule on its badge type's `apply_start`.
- Badges are defined in code (`db_data/badges.py`) and synced into the DB at startup. A new badge type needs its definitions there, a checker in `BadgeEngine._checkers` and its ID in `constants.BADGE_TYPES_TO_CHECK`.

## Time

- `arrival_event` stores timezone-aware UTC (`UTCDateTime` rejects naive values).
- The engine and the derived tables use naive JST wall-clock times. SQLite drops tzinfo when comparing, so filtering derived tables with a UTC datetime is silently 9 hours off: use JST (`engine.to_jst_wall_clock`).

## Schema

Alembic, with `0000` as the baseline; databases from before Alembic are refused (rebuild them from Slack). New revision, against a file DB at head (`tests/test_migrations.py` fails if models and migrations diverge):

```bash
export ENV=dev DATABASE_URL=sqlite:////tmp/alembic.db
uv run alembic upgrade head && uv run alembic revision --autogenerate --rev-id 0001 -m "..."
```

## Running

- Settings are read at import. Outside `ENV=dev` / `ENV=test` every name in `settings.REQUIRED` must be set and the DB must be a file; pytest sets `ENV=test` itself.
- `python -m hikarie_bot` also needs `SLACK_BOT_TOKEN` at import; any `xoxb-` string works for offline commands:
  - `ENV=dev SLACK_BOT_TOKEN=xoxb-dummy uv run python -m hikarie_bot preview`: message mocks from synthetic data.
  - `... sync --from-cache <dir>`: rebuild a DB from recorded Slack responses (also needs the production `BOT_ID` and a file `DATABASE_URL`).
- Never run the bot locally with the production app's tokens: Socket Mode would take button presses away from production. Use `slack run` (dev app, `.env.dev`).
- CI runs `uv run pytest -n auto`, `uv run ruff check .` and `uv run ruff format --check .`. pyright is installed but not enforced and has existing errors.
- Regenerate `uv.lock` with the uv version pinned in the `Dockerfile` (`uvx --from uv==<version> uv lock`).

## Personal data

Slack user IDs and arrival times are personal data: never put real ones in the repo, tests, CI, images or the startup reports posted to the log channel. Recorded Slack responses live only in `.cache/slack/` of the main checkout (gitignored; worktrees do not have it).
