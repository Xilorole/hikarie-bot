#!/bin/bash

# Check if _version.py has been modified
if git diff --name-only | grep -q "hikarie_bot/_version.py"; then
    echo "_version.py has not been modified"
else
    echo "Staging _version.py"
    uv build
    git add hikarie_bot/_version.py
fi
