<div align="center">  
  <h1>QueryWeaver (Text2SQL)</h1>

**REST API · MCP · Graph-powered** 

QueryWeaver is an **open-source Text2SQL** tool that converts plain-English questions into SQL using **graph-powered schema understanding**. It helps you ask databases natural-language questions and returns SQL and results.

Connect and ask questions: [![Discord](https://img.shields.io/badge/Discord-%235865F2.svg?&logo=discord&logoColor=white)](https://discord.gg/b32KEzMzce)

[![Try Free](https://img.shields.io/badge/Try%20Free-FalkorDB%20Cloud-FF8101?labelColor=FDE900&link=https://app.falkordb.cloud)](https://app.falkordb.cloud)
[![PyPI](https://img.shields.io/pypi/v/queryweaver?label=PyPI&logo=pypi&logoColor=white)](https://pypi.org/project/queryweaver/)
[![Dockerhub](https://img.shields.io/docker/pulls/falkordb/queryweaver?label=Docker)](https://hub.docker.com/r/falkordb/queryweaver/)
[![Tests](https://github.com/FalkorDB/QueryWeaver/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/FalkorDB/QueryWeaver/actions/workflows/tests.yml)
[![Swagger UI](https://img.shields.io/badge/API-Swagger-11B48A?logo=swagger&logoColor=white)](https://app.queryweaver.ai/docs)
</div>

![new-qw-ui-gif](https://github.com/user-attachments/assets/34663279-0273-4c21-88a8-d20700020a07)


## Get Started

### Docker

> 💡 Recommended for evaluation purposes (Local Python or Node are not required)
```bash
docker run -p 5000:5000 -it falkordb/queryweaver
```


Launch: http://localhost:5000

---

### Use an .env file (Recommended)

Create a local `.env` by copying `.env.example` and passing it to Docker. This is the simplest way to provide all required configuration:

```bash
cp .env.example .env
# edit .env to set your values, then:
docker run -p 5000:5000 --env-file .env falkordb/queryweaver
```

### Alternative: Pass individual environment variables

If you prefer to pass variables on the command line, use `-e` flags (less convenient for many variables):

```bash
docker run -p 5000:5000 -it \
  -e APP_ENV=production \
  -e FASTAPI_SECRET_KEY=your_super_secret_key_here \
  -e GOOGLE_CLIENT_ID=your_google_client_id \
  -e GOOGLE_CLIENT_SECRET=your_google_client_secret \
  -e GITHUB_CLIENT_ID=your_github_client_id \
  -e GITHUB_CLIENT_SECRET=your_github_client_secret \
  -e AZURE_API_KEY=your_azure_api_key \
  falkordb/queryweaver
```

> Note: QueryWeaver supports multiple AI providers. You can use `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, or `AZURE_API_KEY`. See the [AI/LLM configuration](#aillm-configuration) section for details.

> For a full list of configuration options, consult `.env.example`.

## Memory TTL (optional)

QueryWeaver stores per-user conversation memory in FalkorDB. By default these graphs persist indefinitely. Set `MEMORY_TTL_SECONDS` to apply a Redis TTL (in seconds) so idle memory graphs are automatically cleaned up.

```bash
# Expire memory graphs after 1 week of inactivity
MEMORY_TTL_SECONDS=604800
```

The TTL is refreshed on every user interaction, so active users keep their memory.

## MCP server: host or connect (optional)

QueryWeaver includes optional support for the Model Context Protocol (MCP). You can either have QueryWeaver expose an MCP-compatible HTTP surface (so other services can call QueryWeaver as an MCP server), or configure QueryWeaver to call an external MCP server for model/context services.

What QueryWeaver provides
- The app registers MCP operations focused on Text2SQL flows:
   - `list_databases`
   - `connect_database`
   - `database_schema`
   - `query_database`

- To disable the built-in MCP endpoints set `DISABLE_MCP=true` in your `.env` or environment (default: MCP enabled).
- Configuration

- `DISABLE_MCP` — disable QueryWeaver's built-in MCP HTTP surface. Set to `true` to disable. Default: `false` (MCP enabled).

Examples

Disable the built-in MCP when running with Docker:

```bash
docker run -p 5000:5000 -it --env DISABLE_MCP=true falkordb/queryweaver
```

Calling the built-in MCP endpoints (example)
- The MCP surface is exposed as HTTP endpoints. 


### Server Configuration

Below is a minimal example `mcp.json` client configuration that targets a local QueryWeaver instance exposing the MCP HTTP surface at `/mcp`.

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

## REST API 

### API Documentation

Swagger UI: https://app.queryweaver.ai/docs

OpenAPI JSON: https://app.queryweaver.ai/openapi.json

### Overview

QueryWeaver exposes a small REST API for managing graphs (database schemas) and running Text2SQL queries. All endpoints that modify or access user-scoped data require authentication. In the browser the app uses a signed session cookie established by OAuth or email/password; for CLI and scripts you can use an API token (see `tokens` routes or the web UI to create one).

Core endpoints
- GET /graphs — list available graphs for the authenticated user
- GET /graphs/{graph_id}/data — return nodes/links (tables, columns, foreign keys) for the graph
- POST /graphs — upload or create a graph (JSON payload or file upload)
- POST /graphs/{graph_id} — run a Text2SQL chat query against the named graph (streaming response)

Authentication
- Add an Authorization header: `Authorization: Bearer <API_TOKEN>`

#### Three separate credentials

QueryWeaver keeps its three kinds of "login" independent of one another, so a
failure in one never looks like a failure in another:

| Credential | What it proves | Where it lives | Depends on FalkorDB? |
| --- | --- | --- | --- |
| Browser login | Who is using the app | Signed session cookie, established once by OAuth or a password | No |
| API token | A script may act as a user | `Token` node in the Organizations graph, sent as `Authorization: Bearer …` | Yes |
| Data-source connection | Access to *your* database | Supplied per request, never stored | No (it is your own database) |

Because the browser login is a signed cookie, staying logged in costs no database
round trip and survives a FalkorDB outage — you keep your session and only the
operations that genuinely need the graph fail. Requests that supply an API token
explicitly are always checked against the database and are answered with `503`
(not `401`) when it cannot be reached, so clients retry instead of re-authenticating.

A browser login lasts 24 hours by default; set `BROWSER_SESSION_TTL_HOURS` to
change that. Logging out clears the session cookie and revokes the API token
issued alongside it.

The trade-off of a signed session cookie is that it cannot be revoked from
the server before it expires: the TTL bounds the damage, and rotating
`FASTAPI_SECRET_KEY` invalidates every browser login at once. API tokens keep
their server-side record and so can still be revoked individually and
immediately. Shorten `BROWSER_SESSION_TTL_HOURS` if you need a tighter window.

Examples

1) List graphs (GET)

curl example:

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
   https://app.queryweaver.ai/graphs
```

Python example:

```python
import requests
resp = requests.get('https://app.queryweaver.ai/graphs', headers={'Authorization': f'Bearer {TOKEN}'})
print(resp.json())
```

2) Get graph schema (GET)

curl example:

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
   https://app.queryweaver.ai/graphs/my_database/data
```

Python example:

```python
resp = requests.get('https://app.queryweaver.ai/graphs/my_database/data', headers={'Authorization': f'Bearer {TOKEN}'})
print(resp.json())
```

3) Load a graph (POST) — JSON payload

```bash
curl -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
   -d '{"database": "my_database", "tables": [...]}' \
   https://app.queryweaver.ai/graphs
```

Or upload a file (multipart/form-data):

```bash
curl -H "Authorization: Bearer $TOKEN" -F "file=@schema.json" \
   https://app.queryweaver.ai/graphs
```

4) Query a graph (POST) — run a chat-based Text2SQL request

The `POST /graphs/{graph_id}` endpoint accepts a JSON body with at least a `chat` field (an array of messages). The endpoint streams processing steps and the final SQL back as server-sent-message chunks delimited by a special boundary used by the frontend. For simple scripting you can call it and read the final JSON object from the streamed messages.

Example payload:

```json
{
   "chat": ["How many users signed up last month?"],
   "result": [],
   "instructions": "Prefer PostgreSQL compatible SQL"
}
```

curl example (simple, collects whole response):

```bash
curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
   -d '{"chat": ["Count orders last week"]}' \
   https://app.queryweaver.ai/graphs/my_database
```

Python example (stream-aware):

```python
import requests
import json

url = 'https://app.queryweaver.ai/graphs/my_database'
headers = {'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'}
with requests.post(url, headers=headers, json={"chat": ["Count orders last week"]}, stream=True) as r:
      # The server yields JSON objects delimited by a message boundary string
      boundary = '|||FALKORDB_MESSAGE_BOUNDARY|||'
      buffer = ''
      for chunk in r.iter_content(decode_unicode=True, chunk_size=1024):
            buffer += chunk
            while boundary in buffer:
                  part, buffer = buffer.split(boundary, 1)
                  if not part.strip():
                        continue
                  obj = json.loads(part)
                  print('STREAM:', obj)
```

Notes & tips
- Graph IDs are namespaced per-user. When calling the API directly use the plain graph id (the server will namespace by the authenticated user). For uploaded files the `database` field determines the saved graph id.
- The streaming response includes intermediate reasoning steps, follow-up questions (if the query is ambiguous or off-topic), and the final SQL. The frontend expects the boundary string `|||FALKORDB_MESSAGE_BOUNDARY|||` between messages.
- For destructive SQL (INSERT/UPDATE/DELETE etc) the service will include a confirmation step in the stream; the frontend handles this flow. If you automate destructive operations, ensure you handle confirmation properly (see the `ConfirmRequest` model in the code).

## Python SDK

The QueryWeaver Python SDK allows you to use Text2SQL functionality directly in your Python applications **without running a web server**.

### Installation

```bash
# SDK only (minimal dependencies)
pip install queryweaver

# With server dependencies (FastAPI, etc.)
pip install queryweaver[server]

# Development (includes testing tools)
pip install queryweaver[dev]
```

### Quick Start

```python
import asyncio
from queryweaver import QueryWeaver

async def main():
    # Initialize with FalkorDB connection
    qw = QueryWeaver(falkordb_url="redis://localhost:6379")

    # Connect a PostgreSQL or MySQL database
    conn = await qw.connect_database("postgresql://user:pass@host:5432/mydb")
    print(f"Connected: {conn.database_id}")  # "mydb"

    # Convert natural language to SQL and execute — pass the database_id
    # returned by connect_database (un-prefixed; namespacing is internal).
    result = await qw.query(conn.database_id, "Show me all customers from NYC")
    print(result.sql_query)    # SELECT * FROM customers WHERE city = 'NYC'
    print(result.results)       # [{"id": 1, "name": "Alice", "city": "NYC"}, ...]
    print(result.ai_response)   # "Found 42 customers from NYC..."

    await qw.close()

asyncio.run(main())
```

### Context Manager

```python
async with QueryWeaver(falkordb_url="redis://localhost:6379") as qw:
    conn = await qw.connect_database("postgresql://user:pass@host/mydb")
    result = await qw.query(conn.database_id, "Count orders by status")
# close() runs automatically, awaiting any in-flight background memory writes.
```

### Multiple Instances

Multiple `QueryWeaver` instances can run side-by-side in the same process.
Each holds its own FalkorDB connection and passes it explicitly through
every call, so there is no shared global state to collide over.

```python
async with QueryWeaver(falkordb_url="redis://host-a:6379", user_id="tenant_a") as a, \
           QueryWeaver(falkordb_url="redis://host-b:6379", user_id="tenant_b") as b:
    sales = await a.connect_database("postgresql://user:pass@host-a/sales")
    ops = await b.connect_database("postgresql://user:pass@host-b/ops")
    await a.query(sales.database_id, "Show top customers")
    await b.query(ops.database_id, "Count open tickets")
```

### Available Methods

| Method | Description |
|--------|-------------|
| `connect_database(db_url)` | Connect PostgreSQL/MySQL and load schema |
| `query(database, question)` | Convert natural language to SQL and execute |
| `get_schema(database)` | Retrieve database schema (tables and relationships) |
| `list_databases()` | List all connected databases |
| `delete_database(database)` | Remove database from FalkorDB |
| `refresh_schema(database)` | Re-sync schema after database changes |
| `execute_confirmed(database, sql)` | Execute confirmed destructive operations |

### Advanced Query Options

For multi-turn conversations, custom instructions, or per-request LLM overrides:

```python
from queryweaver import QueryWeaver, QueryRequest

request = QueryRequest(
    question="Show their recent orders",
    chat_history=["Show all customers from NYC"],
    result_history=["Found 42 customers..."],
    instructions="Use created_at for date filtering",
    # Optional per-request LLM overrides — bypass env-based config
    custom_api_key="sk-...",
    custom_model="openai/gpt-4.1",
)

result = await qw.query("mydb", request)
```

### Handling Destructive Operations

INSERT, UPDATE, DELETE operations require confirmation:

```python
result = await qw.query("mydb", "Delete inactive users")

if result.requires_confirmation:
    print(f"Destructive SQL: {result.sql_query}")
    # Execute after user confirms
    confirmed = await qw.execute_confirmed("mydb", result.sql_query)
```

### Requirements

- Python 3.12+
- FalkorDB instance (local or remote)
- OpenAI or Azure OpenAI API key (for LLM)
- Target SQL database (PostgreSQL or MySQL)

## Development

Follow these steps to run and develop QueryWeaver from source.

### Prerequisites

- Python 3.12+
- uv (Python package manager)
- A FalkorDB instance (local or remote)
- Node.js and npm (for the React frontend)

### Install and configure

Quickstart (recommended for development):

```bash
# Clone the repo
git clone https://github.com/FalkorDB/QueryWeaver.git
cd QueryWeaver

# Install dependencies (backend + frontend) and start the dev server
make install
make run-dev
```

If you prefer to set up manually or need a custom environment, use uv:

```bash
# Install Python (backend) and frontend dependencies
uv sync

# Create a local environment file
cp .env.example .env
# Edit .env with your values (set APP_ENV=development for local development)
```

### Run the app locally

```bash
uv run uvicorn api.index:app --host 0.0.0.0 --port 5000 --reload
```

The server will be available at http://localhost:5000

Alternatively, the repository provides Make targets for running the app:

```bash
make run-dev   # development server (reload, debug-friendly)
make run-prod  # production mode (ensure frontend build if needed)
```

### Frontend build (when needed)

The frontend is a modern React + Vite app in `app/`. Build before production runs or after frontend changes:

```bash
make install       # installs backend and frontend deps
make build-prod    # builds the frontend into app/dist/

# or manually
cd app
npm ci
npm run build
```

### OAuth configuration

QueryWeaver supports Google and GitHub OAuth. Create OAuth credentials for each provider and paste the client IDs/secrets into your `.env` file.

- Google: set authorized origin and callback `http://localhost:5000/login/google/authorized`
- GitHub: set homepage and callback `http://localhost:5000/login/github/authorized`

#### Environment-specific OAuth settings

For production/staging deployments, session cookies are HTTPS-only by default. Only an `APP_ENV` that reads as `development` once trimmed and lower-cased turns that off, so a deployment that forgets the variable still gets secure cookies. Set `APP_ENV=development` for plain-HTTP local runs, otherwise the browser drops the cookie and you get OAuth CSRF state mismatch errors.

The signed session cookie is the browser's only credential. An `api_token` is never written to a browser cookie - a bearer token in a cookie sits on disk in clear text for its whole lifetime - so programmatic clients fetch one from the tokens API instead. Sessions issued before this change keep working: the legacy `api_token` cookie is still accepted, just no longer handed out.

```bash
# For production/staging (HTTPS-only session cookies - also the default)
APP_ENV=production

# For development (allows HTTP session cookies)
APP_ENV=development
```

**Important**: If you're getting "mismatching_state: CSRF Warning!" errors on a plain-HTTP environment, ensure `APP_ENV` is set to `development`.

### AI/LLM configuration

QueryWeaver supports multiple AI providers. Set one API key and QueryWeaver auto-detects which provider to use.

**Priority order:** Ollama > OpenAI > Gemini > Anthropic > Cohere > Azure (default)

| Provider | API Key | Default Models |
|----------|---------|----------------|
| Ollama | `OLLAMA_MODEL` | `ollama/<your-model>`, `ollama/nomic-embed-text` |
| OpenAI | `OPENAI_API_KEY` | `openai/gpt-4.1`, `openai/text-embedding-ada-002` |
| Google Gemini | `GEMINI_API_KEY` | `gemini/gemini-3-pro-preview`, `gemini/gemini-embedding-001` |
| Anthropic | `ANTHROPIC_API_KEY` | `anthropic/claude-sonnet-4-5-20250929`, `voyage/voyage-3`* |
| Cohere | `COHERE_API_KEY` | `cohere/command-a-03-2025`, `cohere/embed-v4.0` |
| Azure OpenAI | `AZURE_API_KEY` | `azure/gpt-4.1`, `azure/text-embedding-ada-002` |

\* Anthropic has no native embeddings. You must set `VOYAGE_API_KEY` or `EMBEDDING_MODEL` for embeddings, otherwise startup will fail with an error.

**Optional: Override default models**

```bash
COMPLETION_MODEL=gemini/gemini-3-pro-preview
EMBEDDING_MODEL=gemini/gemini-embedding-001
```

Both must match your API key's provider.

#### Docker examples with AI configuration

Using OpenAI:
```bash
docker run -p 5000:5000 -it \
  -e FASTAPI_SECRET_KEY=your_secret_key \
  -e OPENAI_API_KEY=your_openai_api_key \
  falkordb/queryweaver
```

Using Google Gemini:
```bash
docker run -p 5000:5000 -it \
  -e FASTAPI_SECRET_KEY=your_secret_key \
  -e GEMINI_API_KEY=your_gemini_api_key \
  falkordb/queryweaver
```

Using Anthropic:
```bash
docker run -p 5000:5000 -it \
  -e FASTAPI_SECRET_KEY=your_secret_key \
  -e ANTHROPIC_API_KEY=your_anthropic_api_key \
  falkordb/queryweaver
```

Using Azure OpenAI:
```bash
docker run -p 5000:5000 -it \
  -e FASTAPI_SECRET_KEY=your_secret_key \
  -e AZURE_API_KEY=your_azure_api_key \
  -e AZURE_API_BASE=https://your-resource.openai.azure.com/ \
  -e AZURE_API_VERSION=2025-03-01-preview \
  falkordb/queryweaver
```

## Testing

> Quick note: many tests require FalkorDB to be available. Use the included helper to run a test DB in Docker if needed.

### Prerequisites

- Install dev dependencies: `uv sync`
- Start FalkorDB (see `make docker-falkordb`)
- Install Playwright browsers: `uv run playwright install`

### Quick commands

Recommended: prepare the development/test environment using the Make helper (installs dependencies and Playwright browsers):

```bash
# Prepare development/test environment (installs deps and Playwright browsers)
make setup-dev
```

Alternatively, you can run the E2E-specific setup script and then run tests manually:

```bash
# Prepare E2E test environment (installs browsers and other setup)
./setup_e2e_tests.sh

# Run all tests
make test

# Run unit tests only (faster)
make test-unit

# Run E2E tests (headless)
make test-e2e

# Run E2E tests with a visible browser for debugging
make test-e2e-headed
```

### Test types

- Unit tests: focus on individual modules and utilities. Run with `make test-unit` or `uv run python -m pytest tests/ -k "not e2e"`.
- End-to-end (E2E) tests: run via Playwright and exercise UI flows, OAuth, file uploads, schema processing, chat queries, and API endpoints. Use `make test-e2e`.

See `tests/e2e/README.md` for full E2E test instructions.

### CI/CD

GitHub Actions run unit and E2E tests on pushes and pull requests. Failures capture screenshots and artifacts for debugging.

## Troubleshooting

- FalkorDB connection issues: start the DB helper `make docker-falkordb` or check network/host settings.
- Playwright/browser failures: install browsers with `uv run playwright install` and ensure system deps are present.
- Missing environment variables: copy `.env.example` and fill required values.
- **OAuth "mismatching_state: CSRF Warning!" errors**: Session cookies are HTTPS-only unless `APP_ENV` reads as `development` once trimmed and lower-cased. Set `APP_ENV=development` for plain-HTTP environments; use `production` or `staging` (or leave the variable out entirely) for HTTPS deployments.

## Project layout (high level)

- `api/` – FastAPI backend
- `app/` – React + Vite frontend
- `tests/` – unit and E2E tests


## License

Licensed under the GNU Affero General Public License (AGPL). See [LICENSE](LICENSE.txt).

Copyright FalkorDB Ltd. 2025

