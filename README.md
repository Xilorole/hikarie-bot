# Hikarie BOT

<div align="center">

[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

[![Ruff](https://github.com/Xilorole/hikarie-bot/actions/workflows/ruff.yml/badge.svg)](https://github.com/Xilorole/hikarie-bot/actions/workflows/ruff.yml)
[![Test](https://github.com/Xilorole/hikarie-bot/actions/workflows/test.yml/badge.svg)](https://github.com/Xilorole/hikarie-bot/actions/workflows/test.yml)
[![Docker](https://github.com/Xilorole/hikarie-bot/actions/workflows/docker.yml/badge.svg)](https://github.com/Xilorole/hikarie-bot/actions/workflows/docker.yml)

</div>

## Getting Started
## Features
## Project Structure

The repository is organized as follows:
### Setting Up the Development Environment

Development runs directly on the host (no Dev Container). Install
[uv](https://docs.astral.sh/uv/), then install the project dependencies:

```bash
uv sync --dev
```

This will create a virtual environment and install all necessary dependencies for the project.

Install the pre-commit hooks with pre-commit as a uv tool:

```bash
uv tool install pre-commit --with pre-commit-uv
pre-commit install
```

The `Lint Dockerfiles` hook runs the system `hadolint`, so install it too
(macOS: `brew install hadolint`).

```
├── .github             # GitHub configuration and workflows
│   ├── workflows       # GitHub Actions workflows
├── hikarie_bot         # Source code for the application
│   ├── __init__.py     # Package initialization
│   ├── models.py       # Database models
│   ├── slack_helper.py # Slack integration utilities
│   ├── modals.py       # Slack modal utilities
│   ├── settings.py     # Application settings
│   └── ...             # Other modules
├── tests               # Test cases for the application
│   ├── test_app.py     # Tests for the main application
│   ├── test_badges.py  # Tests for badge-related functionality
│   └── ...             # Other test modules
├── scripts             # Utility scripts
├── Dockerfile          # Docker configuration
├── pyproject.toml      # Project configuration
├── README.md           # Project documentation
└── LICENSE             # License file
```

## Roadmap

- [x] Integrate Ruff for linting and formatting
- [x] Add GitHub Actions for CI/CD
- [ ] Add more test cases
- [ ] Improve documentation

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [uv](https://github.com/astral-sh/uv) for development utilities
- [Ruff](https://github.com/astral-sh/ruff) for linting and formatting

- **Code Quality Tools**: Integrated with `uv` and `Ruff` for formatting and linting.
- **Automated Workflows**: Pre-configured GitHub Actions for Docker builds, testing, and linting.

## Prerequisites

Before you begin, ensure you have the following installed:

- [uv](https://docs.astral.sh/uv/)
- [Docker](https://www.docker.com/) (for building and running the production image)

## Usage

### Running Locally

1. **Start the Development Environment**:
   ```bash
   docker-compose up --build
   ```

2. **Access the Application**:
   Open your browser and navigate to [http://localhost:53138](http://localhost:53138) or [http://localhost:58456](http://localhost:58456).

### Running Tests

To run tests locally, use the following command:
```bash
docker-compose run app pytest
```

## Troubleshooting

### Common Issues

- **Ruff Formatting Not Working**:
  If the Ruff format does not work, try reloading the VS Code window by following these steps:
  ```plaintext
  1. Type `⌘+⇧+P` to open the command palette
  2. Type `Developer: Reload Window` in the command palette to reload the window
  ```

- **Docker Build Fails**:
  Ensure Docker is running and you have sufficient permissions to execute Docker commands.

To get started with the Hikarie BOT, follow these steps:

1. Clone the repository:
   ```bash
   git clone https://github.com/Xilorole/hikarie-bot.git
   ```

2. Navigate to the project directory:
   ```bash
   cd hikarie-bot
   ```

3. Build and run the development environment using Docker:
   ```bash
   docker-compose up --build
   ```

4. Access the application at [http://localhost:53138](http://localhost:53138) or [http://localhost:58456](http://localhost:58456).

## Contributing

Contributions are welcome! Please follow these steps to contribute:

1. Fork the repository.
2. Create a new branch for your feature or bugfix.
3. Commit your changes with clear and descriptive messages.
4. Push your branch and create a pull request.
## Overview
This repository uses uv for dependency management and Ruff for linting and formatting.

If the Ruff format does not work, try reloading the VS Code window.
Specifically, you can solve this problem by following the steps below.

```plaintext
1. Type `⌘+⇧+P` to open the command palette
2. Type `Developer: Reload Window` in the command palette to reload the window
```

## GitHub Actions
- [`docker.yml`](.github/workflows/docker.yml)
  - Workflow to check if you can build with Docker
- [`test.yml`](.github/workflows/test.yml)
  - Workflow to check if all the described tests can be passed with pytest
- [`ruff.yml`](.github/workflows/ruff.yml)
  - Workflow to check if you can go through Formatter and Linter with Ruff

## Running the Bot with Docker

To run the Hikarie Bot using Docker, follow these steps:

1. Build the Docker image:

   ```bash
   docker build -t hikarie-bot .
   ```

2. Run the Docker container:

   ```bash
   docker run -d --name hikarie-bot-container --env-file .env hikarie-bot
   ```

3. Verify that the bot is running:

   ```bash
   docker logs hikarie-bot-container
   ```

Replace `hikarie-bot` and `hikarie-bot-container` with your preferred image and container names if needed.

The production image installs the locked `core` dependencies at build time and
runs the installed package directly as a non-root user (UID/GID 10001). It does
not install or update dependencies when starting. Python and uv images are
pinned by digest; Dependabot checks Docker image updates weekly.

Create `.env` from `.env.template` and fill in the Slack configuration before
starting the bot. `DATABASE_URL` is required outside `ENV=dev`/`ENV=test`; with
`DATABASE_URL=sqlite:////opt/.db/data.db`, persist `/opt/.db` with a Docker volume
when recreating containers. Settings come from environment variables, then
`DOTENV_PATH` or `./.env` (a parent directory's `.env` is never read):

```bash
docker run -d --name hikarie-bot-container --env-file .env \
  --mount type=volume,source=hikarie-bot-db,target=/opt/.db hikarie-bot
```

Existing bind-mounted database directories must be writable by UID/GID 10001.
Back up an existing database before changing its mount configuration. The
Compose configuration uses a named volume for persistent database storage.

Docker CI lints the Dockerfile and verifies that the production image can
import its dependencies, display CLI help, and write to SQLite without network
access. Development/test dependencies are deliberately excluded from that image;
run the test suite on the host with `uv run pytest`.

The dependency layer is separate from the application layer. BuildKit cache
mounts reuse uv downloads on the same builder, while GitHub Actions caches the
production image layers in its own cache scope. Cache mount contents
are not automatically exported to the GitHub Actions cache.

These choices follow the [Docker build best practices](https://docs.docker.com/build/building/best-practices/)
and [uv Docker integration guide](https://docs.astral.sh/uv/guides/integration/docker/).
## Running the Bot with Docker Compose

To run the Hikarie Bot using Docker Compose, follow these steps:

1. Ensure you have Docker and Docker Compose installed on your system.

2. Start the bot using Docker Compose:

   ```bash
   docker-compose up -d
   ```

3. Verify that the bot is running:

   ```bash
   docker logs hikarie-bot-container
   ```

This will build and run the bot in a container named `hikarie-bot-container`.

### Database

The bot creates and migrates its SQLite schema on startup with Alembic
(`hikarie_bot/alembic/`). Revision `0000` is the baseline: databases created
before it are not upgraded and must be removed, since the data is rebuilt from
Slack. Badge definitions are synchronized from code on every start.

To add a migration after changing the models, point `DATABASE_URL` at a database
at the latest revision and autogenerate:

```bash
ENV=dev DATABASE_URL=sqlite:///.db/data.db uv run alembic revision --autogenerate -m "describe the change"
```

### Syncing from Slack

On startup the bot reads arrival events from the output channel into the
`arrival_event` table: the whole channel the first time, then only what was
posted since the last run (one day of overlap, and only threads with new
replies). Scores and badges are then recomputed from those events.

The same sync is available as a command. It only reads from Slack:

```bash
# read from Slack and keep the raw responses (gitignored) for offline use
uv run python -m hikarie_bot sync --record .cache/slack
# rebuild a local database from those responses without network access
ENV=dev DATABASE_URL=sqlite:///.db/data.db uv run python -m hikarie_bot sync --from-cache .cache/slack
```

The raw responses contain real user data: never commit or upload them.
