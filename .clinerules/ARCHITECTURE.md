# Project Architecture Overview

This document provides a high-level overview of the hikarie_bot project's architecture, including its main components and their responsibilities.

## Main Components

- **hikarie_bot/**: Core application package.
  - `__main__.py`: Entry point for running the bot.
  - `constants.py`: Project-wide constants.
  - `curd.py`: CRUD operations and business logic.
  - `database.py`: Database connection and ORM setup.
  - `exceptions.py`: Custom exception classes.
  - `modals.py`: Slack modal definitions and logic.
  - `models.py`: Database models and schemas.
  - `settings.py`: Configuration and environment settings.
  - `slack_components.py`: Slack UI components.
  - `slack_helper.py`: Slack API integration and helpers.
  - `utils.py`: Utility functions.
  - `db_data/`: Static or seed data for the database.

- **scripts/**: Utility scripts for development and automation (e.g., version file management).

- **tests/**: Unit and integration tests for the application.

- **notebook/**: Jupyter notebooks for experimentation or documentation.

## Data Flow

- The bot is started via `__main__.py`, which loads configuration from `settings.py`.
- Database models are defined in `models.py` and managed via `database.py`.
- Business logic and CRUD operations are implemented in `curd.py`.
- Slack interactions are handled by `slack_helper.py`, `slack_components.py`, and `modals.py`.
- Utility functions and constants are shared across modules.

## Design Principles

- Modular structure: Each file has a clear, single responsibility.
- Configuration via environment variables and `settings.py`.
- Linting, formatting, and testing are automated via pre-commit hooks.

For more details, see the code and individual module docstrings.
