# Code Style Guidelines

This document outlines the code style conventions for the hikarie_bot project. Adhering to these guidelines ensures consistency and readability across the codebase.

## 1. Linting and Formatting

- **Linting and formatting are enforced by [ruff](https://docs.astral.sh/ruff/).**
- See `ruff.toml` for the full set of enforced rules (line length, indentation, exclusions, etc.).
- Run `uv run ruff check` and `uv run ruff format` before committing.

## 2. Naming Conventions

- **Modules & files:** Use `snake_case`.
- **Classes:** Use `CamelCase`.
- **Functions & methods:** Use `snake_case`.
- **Constants:** Use `UPPER_CASE`.
- **Variables:** Use `snake_case`.

## 3. Docstrings

- All public modules, classes, functions, and methods should have docstrings.
- Use [Google style](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings) or [NumPy style](https://numpydoc.readthedocs.io/en/latest/format.html) for docstrings.
- Private/internal functions may use brief comments if appropriate.

## 4. Imports

- Group imports in the following order:
  1. Standard library imports
  2. Third-party imports
  3. Local application imports
- Use absolute imports where possible.

## 5. Comments

- Write clear, concise comments where necessary.
- Use `# TODO:` or `# FIXME:` for actionable items (see `TODO_RULES.md`).

## 6. Type Annotations

- Use type annotations for all function signatures and return types.
- Use `Optional`, `List`, `Dict`, etc., from `typing` as needed.

## 7. Miscellaneous

- Avoid long functions; break into smaller units where possible.
- Prefer explicit over implicit code.
- Follow the Zen of Python (`import this`).

For any questions, refer to `ruff.toml` or ask a maintainer.
