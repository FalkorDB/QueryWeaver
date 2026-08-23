.PHONY: help install test test-unit test-e2e test-e2e-no-ai test-e2e-headed lint format clean setup-dev build lint-frontend test-sdk docker-test-services docker-test-stop build-package

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install dependencies
	uv sync
	npm ci --prefix ./app


setup-dev: install ## Set up development environment
	uv run playwright install chromium
	uv run playwright install-deps
	@echo "Development environment setup complete!"
	@echo "Don't forget to copy .env.example to .env and configure your settings"

build-dev:
	npm --prefix ./app run build:dev

build-prod:
	npm --prefix ./app run build

build-package: ## Build distributable package (wheel + sdist)
	uv build
	@echo "Built packages in dist/"

test: build-dev test-unit test-e2e ## Run all tests

test-unit: ## Run unit tests only (excludes SDK and E2E tests)
	uv run python -m pytest tests/ -k "not e2e and not test_sdk" --ignore=tests/test_sdk --verbose


test-e2e: build-dev ## Run E2E tests headless
	npx playwright test --reporter=list


test-e2e-no-ai: build-dev ## Run E2E tests that do not need LLM secrets
	npx playwright test --grep-invert @requires-ai --reporter=list


test-e2e-headed: build-dev ## Run E2E tests with browser visible
	npx playwright test --headed --reporter=list


test-e2e-debug: build-dev ## Run E2E tests with debugging enabled
	npx playwright test --debug

lint: ## Run linting (backend + frontend)
	@echo "Running backend lint (pylint)"
	uv run python -m pylint $(shell git ls-files '*.py')
	@echo "Running frontend lint (eslint)"
	make lint-frontend

lint-frontend: ## Run frontend lint (ESLint)
	npm --prefix ./app run lint
	
format: ## Format code (placeholder - add black/autopep8 if needed)
	@echo "Add code formatting tool like black here"

clean: ## Clean up test artifacts
	rm -rf test-results/
	rm -rf playwright-report/
	rm -rf e2e/.auth/
	rm -rf __pycache__/
	rm -rf dist/
	rm -rf *.egg-info/
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete

run-dev: build-dev ## Run development server
	uv run uvicorn api.index:app --host $${HOST:-127.0.0.1} --port $${PORT:-5000} --reload

run-prod: build-prod ## Run production server
	uv run uvicorn api.index:app --host $${HOST:-0.0.0.0} --port $${PORT:-5000}

docker-falkordb: ## Start FalkorDB in Docker for testing
	docker run -d --name falkordb-test -p 6379:6379 falkordb/falkordb:latest

docker-stop: ## Stop test containers
	docker stop falkordb-test || true
	docker rm falkordb-test || true

# SDK Testing
docker-test-services: ## Start all test services (FalkorDB + PostgreSQL + MySQL)
	docker compose -f docker-compose.test.yml up -d
	@echo "Waiting for services to be ready..."
	@sleep 10

docker-test-stop: ## Stop all test services
	docker compose -f docker-compose.test.yml down -v

test-sdk: ## Run SDK integration tests (requires docker-test-services)
	uv run python -m pytest tests/test_sdk/ -v

test-sdk-quick: ## Run SDK tests without LLM (models and connection only)
	uv run python -m pytest tests/test_sdk/test_queryweaver.py::TestModels tests/test_sdk/test_queryweaver.py::TestQueryWeaverInit -v

test-all: test-unit test-sdk test-e2e ## Run all tests
