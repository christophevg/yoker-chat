include ~/.claude/Makefile

.PHONY: env-dev env-run install-pythons test test-cov test-all format lint typecheck check run docs docs-view all help

env-dev: ## Install all dependencies (dev + docs)
	uv sync --all-extras

env-run: ## Install runtime dependencies
	uv sync

install-pythons: ## Install all supported Python versions
	uv python install 3.10 3.11 3.12

# Testing
test: env-dev ## Run all tests
	uv run pytest -v

test-cov: env-dev ## Run tests with coverage report
	uv run pytest --cov=src --cov-report=term-missing

test-all: env-dev ## Run tests on all Python versions (tox)
	uv run tox

# Code Quality
format: env-dev ## Format code and auto-fix linting issues
	uv run ruff format src tests
	uv run ruff check --fix src tests

lint: env-dev ## Check code for linting issues
	uv run ruff check src tests

typecheck: env-dev ## Run type checking
	uv run mypy src

check: format lint typecheck test ## Run all quality checks

# Running
run: env-run ## Run the application
	uv run yoker-chat --help

# Documentation
docs: env-dev ## Build HTML documentation
	cd docs && uv run sphinx-build -M html . _build

docs-view: docs ## Build and open documentation in browser
	open docs/_build/html/index.html

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' Makefile | grep -v "install-pythons\|sync" | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'


client:
	uv run python -m yoker_chat \
	  --server-url http://localhost:8081 \
	  --agent ../yoker/examples/agents/main.md \
	  --config ../yoker/yoker.toml \
	  --name "TestBot"

online-client:
	uv run python -m yoker_chat \
	  --server-url https://roomz.app.homemadebycvg.com \
	  --agent ../c3/agents/assistant.md \
	  --config ../yoker/yoker.toml \
	  --name "Eira"
