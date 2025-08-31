# QueryWeaver Copilot Instructions

This file provides essential information for coding agents working with the QueryWeaver repository. Follow these instructions to work efficiently and avoid common pitfalls.

## Repository Overview

QueryWeaver is an open-source Text2SQL tool that transforms natural language into SQL using graph-powered schema understanding. Built with Python/FastAPI and FalkorDB (graph database), it provides a web interface for natural language database queries with OAuth authentication.

**Key Technologies:**
- **Backend**: Python 3.12+, FastAPI 0.115.0+, FalkorDB (Redis-based graph database)
- **AI/ML**: LiteLLM with Azure OpenAI/OpenAI integration for text-to-SQL generation
- **Testing**: pytest for unit tests, Playwright for E2E testing
- **Dependencies**: pipenv for package management
- **Authentication**: authlib with Google/GitHub OAuth
- **Deployment**: Docker support, Vercel configuration

**Repository Size**: ~50 Python files, medium complexity web application with comprehensive test suite.

## Essential Build & Validation Commands

Follow this order for a reliable local setup; if you customize the steps, ensure each prerequisite (dependencies, `.env`, Playwright) is completed.

### 1. Initial Setup (recommended for new contributors)
```bash
# Install pipenv if not available
pip install pipenv

# Install dependencies (backend + frontend) and prepare dev tools
# Recommended: use the Make helper which installs Python deps and frontend deps
make install

# Prepare the full development environment (installs Playwright browsers too)
# This runs `make install` then Playwright install steps.
make setup-dev

# OR manual steps if you prefer more granular control:
# pipenv sync --dev
# pipenv run playwright install chromium
# pipenv run playwright install-deps

# Set up environment file
cp .env.example .env
# Edit .env with required values (see Environment Setup section)
```

Note: This project includes a TypeScript frontend in `app/` that must be built before a production run. Node.js and npm are required for the frontend build; `make install` will attempt to install frontend deps in `app/` when present. After `make install`, run `make build-prod` (or `cd app && npm run build`) to compile the TypeScript into the static bundle (build output: `app/public/js/app.js`).

### 2. Development Environment Setup
```bash
# Complete development setup (includes Playwright browsers)
make setup-dev

# OR manual steps:
pipenv sync --dev
pipenv run playwright install chromium
pipenv run playwright install-deps
```

### 3. Testing Commands
```bash
# IMPORTANT: Unit tests require FalkorDB running or will fail with connection errors
# You can start a local test FalkorDB using the included Make helper
make docker-falkordb

# Run unit tests only (safer, doesn't require browser)
make test-unit

# Run E2E tests (requires Playwright setup)
make test-e2e

# Run E2E tests with visible browser (for debugging)
make test-e2e-headed

# Run all tests
make test

# Stop test database when done
make docker-stop
```

### 4. Linting & Code Quality
```bash
# Run pylint (can be run without FalkorDB)
make lint
# OR manually: pipenv run pylint $(git ls-files '*.py')
```

### 5. Running the Application

```bash
# Development server with debug mode
make run-dev
# OR manually: pipenv run uvicorn api.index:app --host "localhost" --port "5000" --reload

# Production mode
make run-prod
# OR manually: pipenv run uvicorn api.index:app --host "localhost" --port "5000"
```

Important: If you're preparing a production deployment or have changed frontend code, run `make build-prod` (or `make build-dev` for a development build) first to produce the static bundle used by the app.

### 5a. Running with Docker

You can run QueryWeaver using Docker without installing Python dependencies locally:

```bash
docker run -p 5000:5000 -it falkordb/queryweaver
```

#### Passing Environment Variables

You can pass environment variables individually using `-e` flags, or provide a full environment file using `--env-file`:

```bash
docker run -p 5000:5000 --env-file .env falkordb/queryweaver
```

Use the provided `.env.example` as a template:

```bash
cp .env.example .env
# Edit .env with your values, then run:
docker run -p 5000:5000 --env-file .env falkordb/queryweaver
```

### 6. Cleanup
```bash
# Clean test artifacts
make clean
```

## Environment Setup Requirements

Create `.env` file from `.env.example` and configure these essential variables:

```bash
# REQUIRED for FastAPI to start
FASTAPI_SECRET_KEY=your_super_secret_key_here

# Optional: set application environment (development, staging, production)
# Default: development (affects session cookie security for OAuth)
APP_ENV=development

# REQUIRED for database connection (preferred)
# Use a single connection string if possible. Example:
# FALKORDB_URL=redis://localhost:6379/0

# Optional: enable debug/reload when running the app directly
# FASTAPI_DEBUG=False

# REQUIRED for full functionality (OAuth, only if you use login flows)
# GOOGLE_CLIENT_ID=your_google_client_id
# GOOGLE_CLIENT_SECRET=your_google_client_secret
# GITHUB_CLIENT_ID=your_github_client_id
# GITHUB_CLIENT_SECRET=your_github_client_secret

# OPTIONAL: AI model configuration (defaults in api/config.py)
# AZURE_API_KEY=your_azure_api_key
# OPENAI_API_KEY=your_openai_api_key
```

**For testing in CI/development**, minimal `.env` setup:
```bash
FASTAPI_SECRET_KEY=test-secret-key
APP_ENV=development
FASTAPI_DEBUG=False
FALKORDB_HOST=localhost
FALKORDB_PORT=6379
```

## Common Issues & Solutions

### 1. FalkorDB Connection Errors
**Error**: `ConnectionError: Error 111 connecting to localhost:6379. Connection refused.`
**Solution**: 
```bash
# Start FalkorDB using Docker
make docker-falkordb
# OR manually: docker run -d --name falkordb-test -p 6379:6379 falkordb/falkordb:latest
```

### 2. Playwright Not Installed
**Error**: E2E tests fail with browser not found
**Solution**:
```bash
pipenv run playwright install chromium
pipenv run playwright install-deps
```

### 3. Missing Environment File
**Error**: Application fails to start, missing configuration
**Solution**:
```bash
cp .env.example .env
# Then edit .env with appropriate values
```

### 4. Import Errors During Testing
**Error**: Module import failures in tests
**Solution**: Ensure you're using pipenv and dependencies are installed:
```bash
pipenv sync --dev
pipenv run pytest tests/ -k "not e2e"
```

### 5. Port Conflicts
**Error**: FastAPI app fails to start on port 5000
**Solution**: Check if port is in use, kill conflicting processes or change port

## Project Architecture & Layout

### Core Application Structure
```
api/                          # Main application package
├── index.py                 # FastAPI application entry point
├── app_factory.py           # Application factory pattern
├── config.py                # AI model configuration and prompts
├── agents/                  # AI agents for query processing
│   ├── analysis_agent.py    # Query analysis
│   ├── relevancy_agent.py   # Schema relevance detection
│   └── follow_up_agent.py   # Follow-up question generation
├── auth/                    # Authentication modules
├── routes/                  # FastAPI route handlers
│   ├── auth.py             # Authentication routes
│   ├── graphs.py           # Graph/database routes
│   └── database.py         # Database management routes
├── loaders/                 # Data loading utilities
├── helpers/                 # Utility functions
├── static/                  # Frontend assets
└── templates/               # Jinja2 templates
```

### Testing Structure
```
tests/
├── conftest.py              # Pytest configuration and fixtures
├── test_*.py                # Unit tests
└── e2e/                     # End-to-end tests
    ├── pages/               # Page Object Model classes
    ├── fixtures/            # Test data and utilities
    └── test_*.py            # E2E test files
```

### Configuration Files
- `Pipfile` & `Pipfile.lock`: Python dependencies
- `pytest.ini`: Test configuration with custom markers
- `Makefile`: Build and development commands
- `.env.example`: Environment variable template
- `Dockerfile`: Container configuration
- `vercel.json`: Deployment configuration

### Key Dependencies
- **FastAPI ecosystem**: FastAPI, Authlib (OAuth)
- **Database**: falkordb, psycopg2-binary (PostgreSQL support)
- **AI/ML**: litellm (LLM abstraction), boto3 (AWS)
- **Development**: pytest, pylint, playwright
- **Data processing**: jsonschema, tqdm

## CI/CD Pipeline Requirements

### GitHub Actions Workflows
The repository has comprehensive CI/CD in `.github/workflows/`:

1. **tests.yml**: Main test pipeline
   - Runs unit tests with FalkorDB service
   - Runs E2E tests with Playwright
   - Uploads test artifacts on failure

2. **pylint.yml**: Code quality checks
   - Runs on every push
   - Uses same Python/pipenv setup

3. **e2e-tests.yml**: Dedicated E2E testing
   - Separate workflow for E2E tests
   - Captures screenshots and videos

4. **dependency-review.yml**: Security scanning
5. **spellcheck.yml**: Documentation quality

### CI Environment Setup
All workflows follow this pattern:
```yaml
- Python 3.12 setup
- pipenv installation
- pipenv sync --dev
- .env file creation with test values (use FALKORDB_URL in CI)
- FalkorDB service startup (for tests requiring DB)
- Playwright browser installation (for E2E tests)
```

### Test Artifacts
- Screenshots saved on E2E test failures
- Playwright reports with video recordings
- Test results stored for 30 days

## Validation Steps for Changes

Before submitting any changes, run these validation steps:

1. **Code Quality**: `make lint`
2. **Unit Tests**: `make test-unit` (with FalkorDB running)
3. **E2E Tests**: `make test-e2e` (if UI changes)
4. **Application Startup**: `make run-dev` and verify app loads
5. **Clean Environment Test**: Test changes in fresh environment with `make clean && make setup-dev`

## Key Files to Understand

### Application Entry Points
- `api/index.py`: Main FastAPI app entry point
- `api/app_factory.py`: Application factory with OAuth setup (lines 1-50 contain core configuration)

### Configuration & Prompts
- `api/config.py`: AI model configuration and system prompts for Text2SQL generation
- `.env.example`: All required environment variables with examples

### Core Logic
- `api/agents/`: Contains the AI agents that process natural language queries
- `api/loaders/`: Database schema loading and graph construction
- `api/routes/`: FastAPI routes for web interface and API

### Testing Infrastructure
- `tests/conftest.py`: Pytest fixtures and test configuration
- `tests/e2e/README.md`: Comprehensive E2E testing documentation
- `setup_e2e_tests.sh`: Automated test environment setup script

### MCP (Model Context Protocol)

QueryWeaver optionally exposes an MCP HTTP surface (mounted at `/mcp`) to allow external MCP clients to call QueryWeaver's Text2SQL operations. Key points for coding agents and reviewers:

- Runtime toggle: the built-in MCP endpoints can be disabled with the env var `DISABLE_MCP=true`. Default behavior is enabled.
- Client config: consumers typically use an `mcp.json` (or client-specific config) that points to the MCP URL, for example:

```json
{
   "servers": {
      "queryweaver": { 
         "type": "http", 
         "url": "http://127.0.0.1:5000/mcp", 
         "headers": { 
            "Authorization": "Bearer your_token_here" 
         } 
      }
   },
   "inputs": []
}
```

- Tools and examples: projects like GitMCP show common client configurations for Cursor, VSCode, and other MCP-capable tools; use those patterns for guidance when writing docs or adding examples in this repo.
- Security: avoid embedding bearer tokens in repo files. Prefer runtime injection via env files or secret managers. If you need to demonstrate a token in tests, use mocked tokens and don't commit them.

Example: generate `mcp.json` from an environment token (pseudo):

```bash
export MQW_TOKEN="secret-token"
cat > mcp.json <<EOF
{
   "servers": {"queryweaver": {"type":"http","url":"http://127.0.0.1:5000/mcp","headers":{"Authorization":"Bearer ${MQW_TOKEN}"}}},
   "inputs": []
}
EOF
```

If you change MCP wiring or add integrations, update `README.md` and `.env.example` accordingly and add tests that run with MCP enabled/disabled to cover both code paths.

## Trust These Instructions

These instructions have been validated by running all commands and testing the complete workflow. Only search for additional information if:
1. The instructions are incomplete for your specific task
2. You encounter errors not covered in the "Common Issues" section
3. You need to understand implementation details not covered here

Always prefer using the documented commands over manual alternatives to avoid configuration issues and ensure consistency with the CI/CD pipeline.