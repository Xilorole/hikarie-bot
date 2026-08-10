.DEFAULT_GOAL := help
UV ?= uv

.PHONY: help install fmt lint typecheck test check wt wt-list wt-rm

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install: ## Sync the virtualenv with pyproject.toml
	$(UV) sync

fmt: ## Format the code with ruff
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

lint: ## Check formatting and lint rules without modifying files
	$(UV) run ruff format --check .
	$(UV) run ruff check .

typecheck: ## Run pyright
	$(UV) run pyright

test: ## Run the test suite (pass ARGS="-k name" to filter)
	$(UV) run pytest $(ARGS)

check: lint test ## Everything CI checks, in one command

wt: ## Create/enter a worktree: make wt BRANCH=feature/x [BASE=origin/main]
	@test -n "$(BRANCH)" || { echo 'usage: make wt BRANCH=feature/x [BASE=origin/main]'; exit 2; }
	@scripts/worktree.sh "$(BRANCH)" "$(if $(BASE),$(BASE),origin/main)"

wt-list: ## List every worktree
	@git worktree list

wt-rm: ## Remove a worktree: make wt-rm BRANCH=feature/x
	@test -n "$(BRANCH)" || { echo 'usage: make wt-rm BRANCH=feature/x'; exit 2; }
	@git worktree remove ".worktrees/$(subst /,-,$(BRANCH))"
	@git worktree prune
