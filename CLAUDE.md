# hikarie-bot

Slack bot that records office arrivals (button presses in one channel) and awards badges and points.
Why the data works the way it does: `docs/design/data-architecture.md` (Japanese). Deploy: `docs/deploy/rancher.md`.

## Data model

- The database holds only `arrival_event`, the source of truth: append-only, deduplicated by Slack message ts; the first event of a user's JST day counts. Startup reads Slack only into an empty database (`sync_channel` always reads the whole channel); live arrivals are stored before they are posted, so Slack never has one the database lacks. After restoring an older backup, run `python -m hikarie_bot sync`.
- Ranks, badges, scores and levels are never stored: `arrivals.compute_arrivals` runs `engine.py` over all events (tens of ms) for each button press and achievement view, and `modals.py` renders the engine's results. Change the rules in `engine.py`.
- A rule change rewrites everyone's past points and badges on the next deploy. To affect only later arrivals, gate the rule on its badge type's `apply_start`.
- Badges are defined only in code (`db_data/badges.py`). A new badge type needs its definitions there, a checker in `BadgeEngine._checkers` and its ID in `constants.BADGE_TYPES_TO_CHECK`.

## Time

- `arrival_event` stores timezone-aware UTC (`UTCDateTime` rejects naive values).
- The engine works on aware datetimes in JST (`BadgeEngine.add` converts aware input and rejects naive), so `.date()` and `.hour` of its results are JST.

## Schema

Alembic, with `0000` as the baseline; databases from before Alembic are refused (rebuild them from Slack). New revision, against a file DB at head (`tests/test_migrations.py` fails if models and migrations diverge):

```bash
export ENV=dev DATABASE_URL=sqlite:////tmp/alembic.db
uv run alembic upgrade head && uv run alembic revision --autogenerate --rev-id <next, e.g. 0001> -m "..."
```

## Running

- Importing the package needs no configuration: settings (`settings.get_settings()`), the engine (`database.get_engine()`) and the Slack app (`__main__.create_app()`) are created on first use. Read settings where they are used instead of copying them into module constants.
- `start` checks `settings.REQUIRED` (skipped under `ENV=dev` / `ENV=test`); a database must be a file outside dev/test. pytest sets `ENV=test`; the `settings` fixture gives each test fresh settings to assign to, and `app_database` a fresh database behind `get_db`.
- Offline commands need no Slack token:
  - `uv run python -m hikarie_bot preview --workspace-id T0000`: message mocks from synthetic data (without `--workspace-id` it calls `auth.test`).
  - `DATABASE_URL=sqlite:///.db/data.db uv run python -m hikarie_bot sync --from-cache <dir>`: rebuild a DB from recorded Slack responses (also needs the production `BOT_ID` and `OUTPUT_CHANNEL`).
- Never run the bot locally with the production app's tokens: Socket Mode would take button presses away from production. Use `slack run` (dev app, `.env.dev`).
- CI runs `uv run pytest -n auto`, `uv run ruff check .` and `uv run ruff format --check .`. pyright is installed but not enforced and has existing errors.
- Regenerate `uv.lock` with the uv version pinned in the `Dockerfile` (`uvx --from uv==<version> uv lock`).

## Personal data

Slack user IDs and arrival times are personal data: never put real ones in the repo, tests, CI, images or the startup reports posted to the log channel. Recorded Slack responses live only in `.cache/slack/` of the main checkout (gitignored; worktrees do not have it).
