# Hikarie BOT

<div align="center">

[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

[![Ruff](https://github.com/Xilorole/hikarie-bot/actions/workflows/ruff.yml/badge.svg)](https://github.com/Xilorole/hikarie-bot/actions/workflows/ruff.yml)
[![Test](https://github.com/Xilorole/hikarie-bot/actions/workflows/test.yml/badge.svg)](https://github.com/Xilorole/hikarie-bot/actions/workflows/test.yml)
[![Docker](https://github.com/Xilorole/hikarie-bot/actions/workflows/docker.yml/badge.svg)](https://github.com/Xilorole/hikarie-bot/actions/workflows/docker.yml)

</div>

## Overview
This repository contains configurations to set up a Python development environment using VSCode's Dev Container feature.
The environment includes uv, and Ruff.

If the Ruff format does not work, try reloading the VS Code window.
Specifically, you can solve this problem by following the steps below.

1. Type `⌘+⇧+P` to open the command palette
2. Type `Developer: Reload Window` in the command palette to reload the window

## Development

### Verification

Everything CI checks runs with one command:

```bash
make check      # ruff format --check + ruff check + pytest
```

Other targets (`make help` lists them all):

| Command | What it does |
| --- | --- |
| `make test` | Run the test suite. Filter with `make test ARGS="-k badge"` |
| `make lint` | Ruff format check + lint, without modifying files |
| `make fmt` | Auto-format and auto-fix |
| `make typecheck` | Run pyright |

### Writing tests

Fixtures live in `tests/conftest.py`:

- `temp_db` — a `sessionmaker` bound to a throwaway in-memory SQLite database
- `session` — a ready-to-use `Session` with the badge master data already inserted

Helpers live in `tests/helpers.py`:

- `arrive(session, "2024-01-01 06:00:00", "user")` — register one arrival
- `BadgeScenario` / `Arrival` / `Expectation` — describe badge behaviour as data

Badge tests are declarative: adding a case to `SCENARIOS` in `tests/test_badges.py`
is all it takes, and each scenario shows up as its own parametrized test.

```python
BadgeScenario(
    id="id5_time_window",
    badge_types=[5],
    check="check_time_window",
    arrivals=[Arrival("2024-04-22 06:00:00", "user_1")],
    expectations=[Expectation("2024-04-22", "user_1", [MORNING])],
)
```

Failures report the scenario, the user, the date and the badge ids on both sides,
so a red test tells you what broke without reading the fixture code.

## GitHub Actions
- `docker.yml`
  - Workflow to check if you can build with Docker
- `test.yml`
  - Workflow to check if all the described tests can be passed with pytest
- `ruff.yml`
  - Workflow to check if you can go through Formatter and Linter with Ruff
