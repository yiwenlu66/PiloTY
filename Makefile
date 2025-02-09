.PHONY: help install dev-install clean lint format test coverage check all dev-env build

# Colors for terminal output
COLOR_RESET = \033[0m
COLOR_BOLD = \033[1m
COLOR_GREEN = \033[32m
COLOR_YELLOW = \033[33m
COLOR_RED = \033[31m

# Python settings
PYTHON = python3
VENV = .venv
BIN = $(VENV)/bin
PACKAGE_NAME = pty_mcp

help:  ## Show this help
	@echo "$(COLOR_BOLD)Available commands:$(COLOR_RESET)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(COLOR_GREEN)%-20s$(COLOR_RESET) %s\n", $$1, $$2}'

$(VENV):  ## Create virtual environment
	@echo "$(COLOR_YELLOW)Creating virtual environment...$(COLOR_RESET)"
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	@echo "$(COLOR_GREEN)Virtual environment created!$(COLOR_RESET)"

install: $(VENV)  ## Install production dependencies
	@echo "$(COLOR_YELLOW)Installing production dependencies...$(COLOR_RESET)"
	$(BIN)/pip install -e .
	@echo "$(COLOR_GREEN)Installation complete!$(COLOR_RESET)"

dev-install: $(VENV)  ## Install development dependencies
	@echo "$(COLOR_YELLOW)Installing development dependencies...$(COLOR_RESET)"
	$(BIN)/pip install -e ".[dev]"
	@echo "$(COLOR_GREEN)Development installation complete!$(COLOR_RESET)"

clean:  ## Clean generated files and caches
	@echo "$(COLOR_YELLOW)Cleaning generated files and caches...$(COLOR_RESET)"
	rm -rf build/ dist/ *.egg-info .eggs/ .pytest_cache/ .coverage coverage.xml htmlcov/
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	@echo "$(COLOR_GREEN)Clean complete!$(COLOR_RESET)"

format:  ## Format code with black and isort
	@echo "$(COLOR_YELLOW)Formatting code...$(COLOR_RESET)"
	$(BIN)/black .
	$(BIN)/ruff check --fix .
	@echo "$(COLOR_GREEN)Formatting complete!$(COLOR_RESET)"

lint:  ## Run linting checks
	@echo "$(COLOR_YELLOW)Running linting checks...$(COLOR_RESET)"
	$(BIN)/ruff check .
	$(BIN)/black --check .
	$(BIN)/mypy $(PACKAGE_NAME)

test:  ## Run tests
	@echo "$(COLOR_YELLOW)Running tests...$(COLOR_RESET)"
	$(BIN)/pytest -v
	@echo "$(COLOR_GREEN)Tests complete!$(COLOR_RESET)"

coverage:  ## Run tests with coverage report
	@echo "$(COLOR_YELLOW)Running tests with coverage...$(COLOR_RESET)"
	$(BIN)/pytest --cov=$(PACKAGE_NAME) --cov-report=xml --cov-report=html
	@echo "$(COLOR_GREEN)Coverage report generated!$(COLOR_RESET)"
	@echo "Open htmlcov/index.html to view the report"

check: lint test  ## Run all checks (lint and test)
	@echo "$(COLOR_GREEN)All checks passed!$(COLOR_RESET)"

build: clean  ## Build package
	@echo "$(COLOR_YELLOW)Building package...$(COLOR_RESET)"
	$(BIN)/pip install --upgrade build
	$(PYTHON) -m build
	@echo "$(COLOR_GREEN)Build complete!$(COLOR_RESET)"

dev-env: dev-install  ## Set up development environment
	@echo "$(COLOR_GREEN)Development environment setup complete!$(COLOR_RESET)"
	@echo "Run 'source $(VENV)/bin/activate' to activate the virtual environment"

all: clean install format lint test  ## Run all build steps
	@echo "$(COLOR_GREEN)All steps completed successfully!$(COLOR_RESET)"