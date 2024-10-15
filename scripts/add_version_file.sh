#!/bin/bash

# Check if _version.py is not already staged
if ! git diff --cached --name-only | grep -q "hikarie_bot/_version.py"; then
    echo "_version.py is not staged. Running 'uv build'."
    uv build

    # Check if _version.py has been modified after running 'uv build'
    if git diff --name-only | grep -q "hikarie_bot/_version.py"; then
        echo "Staging _version.py"
        git add hikarie_bot/_version.py
    else
        echo "_version.py has not been modified after 'uv build'"
    fi
else
    echo "_version.py is already staged"
fi
