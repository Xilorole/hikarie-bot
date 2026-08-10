#!/usr/bin/env bash
# Create (or reuse) a git worktree for a branch and make it ready to work in.
#
#   scripts/worktree.sh <branch> [base-ref]
#
# Worktrees live in .worktrees/ inside the repository. That directory is
# gitignored, so pytest (testpaths = tests) and ruff (which honours
# .gitignore) never descend into it.
set -euo pipefail

branch="${1:-}"
base="${2:-origin/main}"

if [[ -z "$branch" ]]; then
  echo "usage: scripts/worktree.sh <branch> [base-ref]" >&2
  exit 2
fi

repo_root="$(git rev-parse --path-format=absolute --git-common-dir)"
repo_root="$(dirname "$repo_root")"
slug="${branch//\//-}"
path="$repo_root/.worktrees/$slug"

if [[ -d "$path" ]]; then
  echo "worktree already exists: $path"
else
  git -C "$repo_root" fetch origin --prune

  if git -C "$repo_root" show-ref --verify --quiet "refs/heads/$branch"; then
    git -C "$repo_root" worktree add "$path" "$branch"
  elif git -C "$repo_root" show-ref --verify --quiet "refs/remotes/origin/$branch"; then
    git -C "$repo_root" worktree add --track -b "$branch" "$path" "origin/$branch"
  else
    git -C "$repo_root" worktree add -b "$branch" "$path" "$base"
  fi
fi

# .env is gitignored but needed to run the bot; share the main clone's copy.
for env_file in .env .env.template; do
  if [[ -f "$repo_root/$env_file" && ! -e "$path/$env_file" ]]; then
    ln -s "$repo_root/$env_file" "$path/$env_file"
  fi
done

echo "syncing dependencies..."
(cd "$path" && uv sync --quiet)

echo
echo "ready: $path"
echo "  cd $path && make check"
