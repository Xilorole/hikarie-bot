# hikarie-bot

Slack bot that records office arrivals (button presses in one channel) and awards badges and points.
Why the data works the way it does: `docs/design/data-architecture.md` (Japanese). Deploy: `docs/deploy/rancher.md`; production Slack app settings (by hand, unlike the dev app's `manifest.json`): `docs/deploy/slack-app.md`.

## Data model

- `arrival_event` is the source of truth for arrivals: append-only, deduplicated by Slack message ts; the first event of a user's JST day counts. Startup reads Slack only into an empty database (`sync_channel` always reads the whole channel); live arrivals are stored before they are posted, so Slack never has one the database lacks. After restoring an older backup, run `python -m hikarie_bot sync`.
- Item picks (`item_pick_event`, items defined in `db_data/items.py`) are the one other stored input: a user's choice cannot be derived from arrivals. Like arrivals they are stored before they are announced (in the daily post's thread, with metadata that `sync_channel` reads back). The offers and dice rolls are derived from the user and the day, so they are not stored. A pick acts only on the user's arrivals after its day.
- Ranks, badges, scores and levels are never stored: `arrivals.compute_arrivals` runs `engine.py` over all events (tens of ms) for each button press and Home view, and `modals.py` / `home.py` render the engine's results. Change the rules in `engine.py`.
- A rule change rewrites everyone's past points and badges on the next deploy. To affect only later arrivals, gate the rule on its badge type's `apply_start`.
- Badges are defined only in code (`db_data/badges.py`). A new badge type needs its definitions there and a checker in `BadgeEngine.CHECKERS`, which is the list of awarded types and their evaluation order.

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
- `start` checks `settings.REQUIRED` (skipped under `ENV=dev` / `ENV=test`); a database must be a file outside dev/test. It then reads `BOT_ID`, `SLACK_WORKSPACE_ID` and `SLACK_APP_ID` from Slack (`startup.resolve_slack_ids`: `auth.test`, `bots.info`); a value set in the environment wins. pytest sets `ENV=test`; the `settings` fixture gives each test fresh settings to assign to, and `app_database` a fresh database behind `get_db`.
- Offline commands need no Slack token:
  - `uv run python -m hikarie_bot preview`: message mocks from synthetic data, as Block Kit Builder URLs (without `--workspace-id` they open in the signed-in workspace; a wrong ID makes them fail).
  - `DATABASE_URL=sqlite:///.db/data.db uv run python -m hikarie_bot sync --from-cache <dir>`: rebuild a DB from recorded Slack responses (also needs the production `BOT_ID` and `OUTPUT_CHANNEL` as env vars: offline, nothing reads them from Slack).
  - `DATABASE_URL=sqlite:///.db/data.db uv run python -m hikarie_bot stats`: the weekly usage (counts only) that the bot posts to the log channel on Mondays.
- Never run the bot locally with the production app's tokens: Socket Mode would take button presses away from production. Use `slack run` (dev app, `.env.dev`).
- CI runs `uv run pytest -n auto`, `uv run ruff check .` and `uv run ruff format --check .`. pyright is installed but not enforced and has existing errors.
- Regenerate `uv.lock` with the uv version pinned in the `Dockerfile` (`uvx --from uv==<version> uv lock`).

## Item images

Item cards show `assets/items/<item id>.png` (128x128, white with rounded corners), served from `main` by raw.githubusercontent.com. To draw or redraw an item:

1. Generate a whole 4x4 sheet (1024x1024) with Azure OpenAI's `gpt-image-2` (image edit with a reference image), using `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_API_KEY` from the environment (never commit their values).
2. Pass `assets/items/sources/sheet-2.png` as the only reference image, every time; never replace it with a generated sheet (generating from generated images degrades them).
3. Pass the prompt in `assets/items/sources/prompt.md`, rebuilt from the first sheet's prompt, with only the redrawn cells changed. Describe a new design in words instead of adding a second reference image.
4. Save the result as the next `assets/items/sources/sheet-<n>.png`, cut only the redrawn items with `uv run scripts/cut_item_icons.py assets/items/sources/sheet-<n>.png assets/items <item id>...` (its dependencies are inline, PEP 723; it centres each item and keeps at least 7.5% white around it), compare the icons with the others, and record the sheet and its items in `assets/items/sources/README.md`.

## Personal data

Slack user IDs and arrival times are personal data: never put real ones in the repo, tests, CI, images or the startup reports posted to the log channel. Recorded Slack responses live only in `.cache/slack/` of the main checkout (gitignored; worktrees do not have it).
