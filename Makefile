.PHONY: help install dev test lint format type-check security clean examples doc-coverage check

PYTHON ?= python3
POETRY ?= poetry

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install production dependencies
	$(POETRY) install --only main

dev: ## Install all dependencies (including dev)
	$(POETRY) install

test: ## Run tests with the 100% line+branch coverage gate
	$(POETRY) run pytest tests/ \
		--cov=pain001_mcp --cov-branch \
		--cov-report=term-missing --cov-fail-under=100 -v

lint: ## Run linters (ruff + black check)
	$(POETRY) run ruff check pain001_mcp/ tests/
	$(POETRY) run black --check pain001_mcp/ tests/

format: ## Auto-format code (ruff fix + black)
	$(POETRY) run ruff check --fix pain001_mcp/ tests/
	$(POETRY) run black pain001_mcp/ tests/

type-check: ## Run mypy type checking
	$(POETRY) run mypy pain001_mcp/

security: ## Run security scan (bandit)
	$(POETRY) run bandit -r pain001_mcp/ -c pyproject.toml 2>/dev/null || \
		$(POETRY) run bandit -r pain001_mcp/ -ll

clean: ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info .eggs/
	rm -rf .pytest_cache/ .mypy_cache/ .ruff_cache/ htmlcov/
	rm -rf coverage.xml .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true

examples: ## Verify example scripts run
	$(POETRY) run python examples/01_mcp_tools.py
	$(POETRY) run python examples/02_validate_pipeline.py
	$(POETRY) run python examples/03_parse_bank_replies.py

doc-coverage: ## Enforce the 100% docstring coverage gate
	$(POETRY) run interrogate -c pyproject.toml -v pain001_mcp

check: lint type-check test doc-coverage examples ## Run all gates
