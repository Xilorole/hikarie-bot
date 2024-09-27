#!/bin/bash

uv sync --dev
uv run jupyter --paths

# Install starship
echo "$(starship init zsh)" >> ~/.zshrc
