# Scripts Guide

This document provides documentation for custom scripts used in the hikarie_bot project. It explains the purpose of each script, how to use them, and any important notes or troubleshooting tips.

## scripts/add_version_file.sh

- **Purpose:** Ensures that `hikarie_bot/_version.py` is created or updated as needed, typically after version changes or during the build process.
- **Usage:** This script is run automatically by pre-commit hooks. You can also run it manually:
  ```
  bash scripts/add_version_file.sh
  ```
- **Notes:**
  - The script is intended to work with setuptools_scm for dynamic versioning.
  - If you encounter issues with versioning, ensure that setuptools_scm is installed and configured in `pyproject.toml`.

## Adding New Scripts

- Place new scripts in the `scripts/` directory.
- Document each new script in this file, including its purpose, usage, and any dependencies or caveats.

## Troubleshooting

- If a script fails, check that all dependencies are installed and that you have the necessary permissions.
- For issues related to pre-commit hooks, try running `pre-commit clean` and `pre-commit install` to reset the environment.
