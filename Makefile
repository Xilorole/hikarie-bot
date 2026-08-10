.DEFAULT_GOAL := help
UV ?= uv

.PHONY: help install fmt lint typecheck test check

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
