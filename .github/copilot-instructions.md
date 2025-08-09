# QueryWeaver Copilot Instructions

This file provides essential information for coding agents working with the QueryWeaver repository. Follow these instructions to work efficiently and avoid common pitfalls.

## Repository Overview

QueryWeaver is an open-source Text2SQL tool that transforms natural language into SQL using graph-powered schema understanding. Built with Python/Flask and FalkorDB (graph database), it provides a web interface for natural language database queries with OAuth authentication.

**Key Technologies:**
- **Backend**: Python 3.12+, Flask 3.1+, FalkorDB (Redis-based graph database)
- **AI/ML**: LiteLLM with Azure OpenAI/OpenAI integration for text-to-SQL generation
- **Testing**: pytest for unit tests, Playwright for E2E testing
- **Dependencies**: pipenv for package management
- **Authentication**: Flask-Dance with Google/GitHub OAuth
- **Deployment**: Docker support, Vercel configuration

**Repository Size**: ~50 Python files, medium complexity web application with comprehensive test suite.

## Essential Build & Validation Commands

**CRITICAL**: Always run these commands in the exact order specified. Many commands will fail if prerequisites are not met.

### 1. Initial Setup (Required for all operations)
```bash
# Install pipenv if not available
pip install pipenv

# Install all dependencies (ALWAYS run this first)
make install
# OR manually: pipenv sync --dev

# Set up environment file (REQUIRED)
cp .env.example .env
# Edit .env with required values (see Environment Setup section)
```

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
# Start FalkorDB for testing (requires Docker)
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
# OR manually: pipenv run flask --app api.index run --debug

# Production mode
make run-prod
# OR manually: pipenv run flask --app api.index run
```

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

**CRITICAL**: Create `.env` file from `.env.example` and configure these essential variables:

```bash
# REQUIRED for Flask to start
FLASK_SECRET_KEY=your_super_secret_key_here
FLASK_DEBUG=False

# REQUIRED for database connection (most functionality)
FALKORDB_HOST=localhost
FALKORDB_PORT=6379

# REQUIRED for full functionality (OAuth)
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret

# OPTIONAL: AI model configuration (defaults in api/config.py)
# AZURE_API_KEY=your_azure_api_key
# OPENAI_API_KEY=your_openai_api_key
```

**For testing in CI/development**, minimal `.env` setup:
```bash
FLASK_SECRET_KEY=test-secret-key
FLASK_DEBUG=False
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
**Error**: Flask app fails to start on port 5000
**Solution**: Check if port is in use, kill conflicting processes or change port

## Project Architecture & Layout

### Core Application Structure
```
api/                          # Main application package
├── index.py                 # Flask application entry point
├── app_factory.py           # Application factory pattern
├── config.py                # AI model configuration and prompts
├── agents/                  # AI agents for query processing
│   ├── analysis_agent.py    # Query analysis
│   ├── relevancy_agent.py   # Schema relevance detection
│   └── follow_up_agent.py   # Follow-up question generation
├── auth/                    # Authentication modules
├── routes/                  # Flask route handlers
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
- **Flask ecosystem**: Flask, Flask-Dance (OAuth)
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
- .env file creation with test values
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
- `api/index.py`: Main Flask app entry point
- `api/app_factory.py`: Application factory with OAuth setup (lines 1-50 contain core configuration)

### Configuration & Prompts
- `api/config.py`: AI model configuration and system prompts for Text2SQL generation
- `.env.example`: All required environment variables with examples

### Core Logic
- `api/agents/`: Contains the AI agents that process natural language queries
- `api/loaders/`: Database schema loading and graph construction
- `api/routes/`: Flask routes for web interface and API

### Testing Infrastructure
- `tests/conftest.py`: Pytest fixtures and test configuration
- `tests/e2e/README.md`: Comprehensive E2E testing documentation
- `setup_e2e_tests.sh`: Automated test environment setup script

## Trust These Instructions

These instructions have been validated by running all commands and testing the complete workflow. Only search for additional information if:
1. The instructions are incomplete for your specific task
2. You encounter errors not covered in the "Common Issues" section
3. You need to understand implementation details not covered here

Always prefer using the documented commands over manual alternatives to avoid configuration issues and ensure consistency with the CI/CD pipeline.