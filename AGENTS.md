# AGENTS.md — QueryWeaver (Text2SQL)

## Project Overview

QueryWeaver is an open-source Text2SQL tool that converts natural-language questions into SQL using graph-powered schema understanding backed by FalkorDB. It is a full-stack monorepo with a Python/FastAPI backend (`api/`) and a React/TypeScript frontend (`app/`).

Repository: `FalkorDB/QueryWeaver`

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12+, FastAPI, Uvicorn |
| Frontend | React 18, TypeScript 5.8, Vite 7, Tailwind CSS |
| Graph DB | FalkorDB |
| LLM | LiteLLM (multi-provider: OpenAI, Gemini, Anthropic, Cohere, Azure, Ollama) |
| Auth | OAuth 2.0 (Google, GitHub) via authlib |
| Package mgmt | uv (Python), npm (Node) |
| Testing | pytest (unit), Playwright (E2E) |
| Linting | pylint (Python), ESLint (TypeScript) |
| CI/CD | GitHub Actions |

## Directory Structure

```
api/              Python backend (FastAPI)
  agents/         AI agents (analysis, healing, relevancy, follow-up)
  analyzers/      Code/syntax analyzers
  auth/           OAuth handlers, user management
  core/           Core text2sql logic, schema loading, errors
  entities/       Data models / DTOs
  loaders/        Database loaders (PostgreSQL, MySQL)
  memory/         Conversation memory management
  routes/         API endpoints (auth, graphs, database, tokens, settings)
  sql_utils/      SQL sanitization
  config.py       LLM provider detection, configuration
  app_factory.py  FastAPI app init, middleware
  index.py        Application entry point
app/              React + Vite frontend
  src/components/ React components
  src/contexts/   React contexts (Auth, Chat, Database, Settings)
  src/services/   API service layer
  src/types/      TypeScript type definitions
tests/            Unit tests (pytest)
e2e/              End-to-end tests (Playwright)
docs/             Documentation
.github/workflows/ CI/CD pipelines
```

## Quick Reference

### Install & Setup

```bash
make install          # uv sync + npm ci
make setup-dev        # install + Playwright browsers
cp .env.example .env  # configure environment
```

### Run

```bash
make run-dev          # dev server with hot reload (localhost:5000)
make run-prod         # production server
make docker-falkordb  # start FalkorDB in Docker
```

### Test

```bash
make test-unit        # pytest unit tests
make test-e2e         # Playwright E2E (headless)
make test-e2e-headed  # Playwright E2E (visible browser)
make test             # build + unit + E2E
```

### Lint

```bash
make lint             # pylint + ESLint
make lint-frontend    # ESLint only
```

### Build

```bash
make build-dev        # Vite dev build
make build-prod       # Vite production build
```

## Code Conventions

### Python (backend)

- PEP 8 with **120-char line limit**
- Type hints throughout
- pylint for linting (docstring checks disabled)
- FastAPI routers split by domain under `api/routes/`
- Custom exceptions in `api/core/errors.py` (GraphNotFoundError, InternalError, InvalidArgumentError)
- Middleware: CSRF (double-submit cookies), HSTS headers
- Environment config via dotenv; see `api/config.py` for defaults and provider detection
- Run backend: `uv run uvicorn api.index:app`

### TypeScript / React (frontend)

- Strict TypeScript
- ESLint with `@typescript-eslint`; unused vars prefixed with `_` are allowed
- State management via React Context API
- API calls through service layer (`app/src/services/`)
- Styling with Tailwind CSS + Radix UI primitives
- Routing with React Router v7
- Forms with React Hook Form + Zod validation
- Build tool: Vite (dev proxy to backend on port 5000)

### Testing

- **Unit tests** (`tests/`): pytest with markers `e2e`, `slow`, `auth`, `integration`, `unit`
- **E2E tests** (`e2e/`): Playwright with Page Object Model pattern; auth setup runs first
- E2E infra lives in `e2e/infra/`, page objects in `e2e/logic/pom/`
- Test data (SQL init scripts) in `e2e/test-data/`

## Environment Variables

Required:
- `FASTAPI_SECRET_KEY` — session secret
- `FALKORDB_URL` — FalkorDB connection string (e.g. `redis://localhost:6379/0`)

LLM provider (set one): `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `COHERE_API_KEY`, `AZURE_API_KEY`, or `OLLAMA_MODEL`

Optional overrides: `COMPLETION_MODEL`, `EMBEDDING_MODEL` (must match provider)

See `.env.example` for the full list.

## CI/CD

GitHub Actions workflows (`.github/workflows/`):
- **tests.yml** — unit tests + lint on push/PR to main/staging
- **playwright.yml** — dedicated Playwright E2E suite
- **pylint.yml** — Python linting
- **spellcheck.yml** — docs spellcheck
- **publish-docker.yml** — build & push Docker image to DockerHub
- **dependency-review.yml** — dependency security review

## Branching

- `main` — production branch, target for PRs
- `staging` — integration branch
