#!/bin/bash

# Get the last commit hash
last_commit=$(git rev-parse HEAD)

# Check if hikarie_bot/_version.py was modified in the last commit
if git diff-tree --no-commit-id --name-only -r $last_commit | grep -q "hikarie_bot/_version.py"; then
    echo "Version file was updated in the last commit."
    exit 0
else
    echo "Error: Version file was not updated in the last commit."
    exit 1
fi
