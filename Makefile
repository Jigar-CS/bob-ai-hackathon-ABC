# Developer shortcuts. Windows users without make can run the underlying
# commands directly — each recipe is a single line.
.DEFAULT_GOAL := help
.PHONY: help install lint format typecheck test test-cov check run data docker-build docker-run clean

PYTHON ?= python

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install the package with development dependencies
	$(PYTHON) -m pip install -e ".[dev]"

lint: ## Run Ruff lint checks
	$(PYTHON) -m ruff check .

format: ## Apply Ruff formatting and autofixes
	$(PYTHON) -m ruff check --fix . && $(PYTHON) -m ruff format .

typecheck: ## Run mypy
	$(PYTHON) -m mypy

test: ## Run the test suite
	$(PYTHON) -m pytest

test-cov: ## Run the test suite with a coverage report
	$(PYTHON) -m pytest --cov --cov-report=term-missing

check: lint typecheck test ## Run everything CI runs

run: ## Start the development server on http://127.0.0.1:8000
	$(PYTHON) -m uvicorn portpulse.main:app --reload

data: ## Regenerate the sample vessel and berth datasets
	$(PYTHON) scripts/generate_sample_data.py

docker-build: ## Build the container image
	docker build -t portpulse:local .

docker-run: ## Run the container on http://127.0.0.1:8000
	docker run --rm -p 8000:8000 -e PORTPULSE_ENVIRONMENT=development portpulse:local

clean: ## Remove build and cache artefacts
	$(PYTHON) -c "import shutil,pathlib; [shutil.rmtree(p, ignore_errors=True) for p in ['build','dist','.pytest_cache','.mypy_cache','.ruff_cache','htmlcov']]; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]"
