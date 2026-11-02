# Hikarie BOT

A Slack bot for office arrivals: every business day at 06:00 JST it posts a button to the channel, records who
pressed it and when, and awards badges, points and levels.

## Development

```bash
uv sync
uv tool install pre-commit --with pre-commit-uv
pre-commit install
```

The `Lint Dockerfiles` hook runs the system `hadolint` (macOS: `brew install hadolint`).

### Running against the dev workspace

Never run the bot locally with the production app's tokens: Socket Mode would take the button presses away from
production. Use the dev app instead:

1. Install the [Slack CLI](https://api.slack.com/automation/cli/install) and `slack login` to the dev workspace.
2. Copy `.env.dev.template` to `.env.dev` and set `ADMIN` to your user ID.
3. `slack run`

The CLI installs the dev app from `manifest.json` and injects its tokens. `scripts/slack_dev_start.sh` derives
`BOT_ID` and the workspace from them, creates the `#prd` / `#log` channels if needed, and starts the bot with
`--dev`, which posts the daily message right away.

### Message previews

```bash
uv run python -m hikarie_bot preview --workspace-id <team ID>
```

renders every user-facing message from synthetic data and prints Block Kit Builder URLs for that workspace, without
touching Slack (`--database-url` renders from an existing database, read-only).

## Running in production

Create `.env` from `.env.template`, then `docker compose up -d`. Compose keeps the SQLite database in the `bot-db`
volume; add `--build` to run the checkout instead of `ghcr.io/xilorole/hikarie-bot:latest`.

On Rancher, see [docs/deploy/rancher.md](docs/deploy/rancher.md) (Japanese).

## Data

`arrival_event` (one row per arrival) is the only stored data; scores, ranks and badges are recomputed from it on
every start and every button press. Badge definitions live in code and are synced into the database on start.
The design and its reasons: [docs/design/data-architecture.md](docs/design/data-architecture.md) (Japanese).

On start the bot reads the whole channel (about 10 minutes) only when the database is empty; arrivals it posts are
stored first, so later starts need no Slack read. The same full read is available as a read-only command (idempotent;
needed after restoring an older backup):

```bash
# read from Slack and keep the raw responses for offline use
uv run python -m hikarie_bot sync --record .cache/slack
# rebuild a local database from those responses without network access
DATABASE_URL=sqlite:///.db/data.db uv run python -m hikarie_bot sync --from-cache .cache/slack
```

The raw responses contain real user data: never commit or upload them.

### Schema changes

The schema is migrated with Alembic on start. Revision `0000` is the baseline; older databases are refused and
must be rebuilt from Slack. After changing the models, autogenerate against a database at the latest revision:

```bash
export ENV=dev DATABASE_URL=sqlite:///.db/alembic.db
uv run alembic upgrade head
uv run alembic revision --autogenerate --rev-id <next number, e.g. 0001> -m "describe the change"
```

## License

MIT. See [LICENSE](LICENSE).
