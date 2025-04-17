# Contributing Guidelines

Thank you for considering contributing to hikarie_bot! This document outlines the process for contributing code, documentation, and ideas to the project.

## Getting Started

- Fork the repository and create your branch from `main`.
- Ensure your code follows the [Code Style Guidelines](./CODE_STYLE.md).
- Run linting and formatting: `uv run ruff check` and `uv run ruff format`.
- Run tests: `uv run pytest`.

## Pull Request Process

1. Ensure your branch is up to date with `main`.
2. Open a pull request (PR) with a clear description of your changes.
3. Fill out the [Pull Request Template](./PULL_REQUEST_TEMPLATE.md).
4. Link any related issues in the PR description.
5. Ensure all checks (lint, format, tests) pass.
6. Request a review from a maintainer.

## Branch Naming

- Use descriptive branch names, e.g., `feature/add-slack-support`, `bugfix/fix-db-connection`.

## Commit Messages

- Follow the [Commit Message Template](./COMMIT_MESSAGE_TEMPLATE.txt).
- Use clear, concise messages describing the change.

## Code Review

- Address reviewer comments promptly.
- Be open to feedback and suggestions.

## Additional Notes

- Document any new dependencies or scripts in the appropriate `.clinerules/` file.
- For major changes, discuss your proposal in an issue before starting work.

Thank you for helping improve hikarie_bot!
