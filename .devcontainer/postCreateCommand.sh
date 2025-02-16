#!/bin/bash

# Install starship
echo "$(starship init zsh)" >> ~/.zshrc

# install dependencies
uv sync --dev
# uv run jupyter --paths
