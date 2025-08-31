.PHONY: help install test test-unit test-e2e test-e2e-headed lint format clean setup-dev build lint-frontend

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install dependencies
	pipenv sync --dev
	npm install --prefix ./app


setup-dev: install ## Set up development environment
	pipenv run playwright install chromium
	pipenv run playwright install-deps
	@echo "Development environment setup complete!"
	@echo "Don't forget to copy .env.example to .env and configure your settings"

build-dev:
	npm --prefix ./app run build:dev

build-prod:
	npm --prefix ./app run build

test: build-dev test-unit test-e2e ## Run all tests

test-unit: ## Run unit tests only
	pipenv run python -m pytest tests/ -k "not e2e" --verbose


test-e2e: build-dev ## Run E2E tests headless
	pipenv run python -m pytest tests/e2e/ --browser chromium --video=on --screenshot=on


test-e2e-headed: build-dev ## Run E2E tests with browser visible
	pipenv run python -m pytest tests/e2e/ --browser chromium --headed


test-e2e-debug: build-dev ## Run E2E tests with debugging enabled
	pipenv run python -m pytest tests/e2e/ --browser chromium --slowmo=1000

lint: ## Run linting (backend + frontend)
	@echo "Running backend lint (pylint)"
	pipenv run pylint $(shell git ls-files '*.py') || true
	@echo "Running frontend lint (eslint)"
	make lint-frontend

lint-frontend: ## Run frontend lint (ESLint)
	npm --prefix ./app run lint
	
format: ## Format code (placeholder - add black/autopep8 if needed)
	@echo "Add code formatting tool like black here"

clean: ## Clean up test artifacts
	rm -rf test-results/
	rm -rf playwright-report/
	rm -rf tests/e2e/screenshots/
	rm -rf __pycache__/
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete

run-dev: build-dev ## Run development server
	pipenv run uvicorn api.index:app --host $${HOST:-127.0.0.1} --port $${PORT:-5000} --reload

run-prod: build-prod ## Run production server
	pipenv run uvicorn api.index:app --host $${HOST:-0.0.0.0} --port $${PORT:-5000}

docker-falkordb: ## Start FalkorDB in Docker for testing
	docker run -d --name falkordb-test -p 6379:6379 falkordb/falkordb:latest

docker-stop: ## Stop test containers
	docker stop falkordb-test || true
	docker rm falkordb-test || true
