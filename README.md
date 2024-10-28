# Hikarie BOT

<div align="center">

[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

[![Ruff](https://github.com/Xilorole/python-uv/actions/workflows/ruff.yml/badge.svg)](https://github.com/Xilorole/python-uv/actions/workflows/ruff.yml)
[![Test](https://github.com/Xilorole/python-uv/actions/workflows/test.yml/badge.svg)](https://github.com/Xilorole/python-uv/actions/workflows/test.yml)
[![Docker](https://github.com/Xilorole/python-uv/actions/workflows/docker.yml/badge.svg)](https://github.com/Xilorole/python-uv/actions/workflows/docker.yml)

</div>

## Overview
This repository contains configurations to set up a Python development environment using VSCode's Dev Container feature.
The environment includes uv, and Ruff.

If the Ruff format does not work, try reloading the VS Code window.
Specifically, you can solve this problem by following the steps below.

1. Type `⌘+⇧+P` to open the command palette
2. Type `Developer: Reload Window` in the command palette to reload the window

## GitHub Actions
- `docker.yml`
  - Workflow to check if you can build with Docker
- `test.yml`
  - Workflow to check if all the described tests can be passed with pytest
- `ruff.yml`
  - Workflow to check if you can go through Formatter and Linter with Ruff
