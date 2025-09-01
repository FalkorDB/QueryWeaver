[![Try Free](https://img.shields.io/badge/Try%20Free-FalkorDB%20Cloud-FF8101?labelColor=FDE900&link=https://app.falkordb.cloud)](https://app.falkordb.cloud)
[![Dockerhub](https://img.shields.io/docker/pulls/falkordb/queryweaver?label=Docker)](https://hub.docker.com/r/falkordb/queryweaver/)
[![Discord](https://img.shields.io/discord/1146782921294884966?style=flat-square)](https://discord.com/invite/6M4QwDXn2w)
[![Tests](https://github.com/FalkorDB/QueryWeaver/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/FalkorDB/QueryWeaver/actions/workflows/tests.yml)
[![Swagger UI](https://img.shields.io/badge/API-Swagger-11B48A?logo=swagger&logoColor=white)](https://app.queryweaver.ai/docs)

# QueryWeaver

QueryWeaver is an open-source Text2SQL tool that converts plain-English questions into SQL using graph-powered schema understanding. It helps you ask databases natural-language questions and returns SQL and results.

![Screenshot](https://github.com/user-attachments/assets/a0be7bbd-0c99-4399-a302-2b9f7b419dd2)

TL;DR
- Try quickly with Docker: `docker run -p 5000:5000 -it falkordb/queryweaver`
- Develop locally: see "Development" section below

## Quick start — Docker (recommended for evaluation)

Run the official image locally (no local Python or Node required):

```bash
docker run -p 5000:5000 -it falkordb/queryweaver
```

Open: http://localhost:5000

### Prefer using a .env file (recommended)

Create a local `.env` by copying `.env.example` and pass it to Docker. This is the simplest way to provide all required configuration:

```bash
cp .env.example .env
# edit .env to set your values, then:
docker run -p 5000:5000 --env-file .env falkordb/queryweaver
```

### Or pass individual environment variables

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

For a full list of configuration options, consult `.env.example`.

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

QueryWeaver exposes a small REST API for managing graphs (database schemas) and running Text2SQL queries. All endpoints that modify or access user-scoped data require authentication via a bearer token. In the browser the app uses session cookies and OAuth flows; for CLI and scripts you can use an API token (see `tokens` routes or the web UI to create one).

Core endpoints
- GET /graphs — list available graphs for the authenticated user
- GET /graphs/{graph_id}/data — return nodes/links (tables, columns, foreign keys) for the graph
- POST /graphs — upload or create a graph (JSON payload or file upload)
- POST /graphs/{graph_id} — run a Text2SQL chat query against the named graph (streaming response)

Authentication
- Add an Authorization header: `Authorization: Bearer <API_TOKEN>`

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

Notes & tips
- Graph IDs are namespaced per-user. When calling the API directly use the plain graph id (the server will namespace by the authenticated user). For uploaded files the `database` field determines the saved graph id.
- The streaming response includes intermediate reasoning steps, follow-up questions (if the query is ambiguous or off-topic), and the final SQL. The frontend expects the boundary string `|||FALKORDB_MESSAGE_BOUNDARY|||` between messages.
- For destructive SQL (INSERT/UPDATE/DELETE etc) the service will include a confirmation step in the stream; the frontend handles this flow. If you automate destructive operations, ensure you handle confirmation properly (see the `ConfirmRequest` model in the code).


## Development

Follow these steps to run and develop QueryWeaver from source.

### Prerequisites

- Python 3.12+
- pipenv
- A FalkorDB instance (local or remote)
- Node.js and npm (for the TypeScript frontend)

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

If you prefer to set up manually or need a custom environment, use Pipenv:

```bash
# Install Python (backend) and frontend dependencies
pipenv sync --dev

# Create a local environment file
cp .env.example .env
# Edit .env with your values (set APP_ENV=development for local development)
```

### Run the app locally

```bash
pipenv run uvicorn api.index:app --host 0.0.0.0 --port 5000 --reload
```

The server will be available at http://localhost:5000

Alternatively, the repository provides Make targets for running the app:

```bash
make run-dev   # development server (reload, debug-friendly)
make run-prod  # production mode (ensure frontend build if needed)
```

### Frontend build (when needed)

The frontend is a TypeScript app in `app/`. Build before production runs or after frontend changes:

```bash
make install       # installs backend and frontend deps
make build-prod    # builds the frontend into app/public/js/app.js

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

For production/staging deployments, set `APP_ENV=production` or `APP_ENV=staging` in your environment to enable secure session cookies (HTTPS-only). This prevents OAuth CSRF state mismatch errors.

```bash
# For production/staging (enables HTTPS-only session cookies)
APP_ENV=production

# For development (allows HTTP session cookies)
APP_ENV=development
```

**Important**: If you're getting "mismatching_state: CSRF Warning!" errors on staging/production, ensure `APP_ENV` is set to `production` or `staging` to enable secure session handling.

## Testing

> Quick note: many tests require FalkorDB to be available. Use the included helper to run a test DB in Docker if needed.

### Prerequisites

- Install dev dependencies: `pipenv sync --dev`
- Start FalkorDB (see `make docker-falkordb`)
- Install Playwright browsers: `pipenv run playwright install`

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

- Unit tests: focus on individual modules and utilities. Run with `make test-unit` or `pipenv run pytest tests/ -k "not e2e"`.
- End-to-end (E2E) tests: run via Playwright and exercise UI flows, OAuth, file uploads, schema processing, chat queries, and API endpoints. Use `make test-e2e`.

See `tests/e2e/README.md` for full E2E test instructions.

### CI/CD

GitHub Actions run unit and E2E tests on pushes and pull requests. Failures capture screenshots and artifacts for debugging.

## Troubleshooting

- FalkorDB connection issues: start the DB helper `make docker-falkordb` or check network/host settings.
- Playwright/browser failures: install browsers with `pipenv run playwright install` and ensure system deps are present.
- Missing environment variables: copy `.env.example` and fill required values.
- **OAuth "mismatching_state: CSRF Warning!" errors**: Set `APP_ENV=production` (or `staging`) in your environment for HTTPS deployments, or `APP_ENV=development` for HTTP development environments. This ensures session cookies are configured correctly for your deployment type.

## Project layout (high level)

- `api/` – FastAPI backend
- `app/` – TypeScript frontend
- `tests/` – unit and E2E tests


## License

Licensed under the GNU Affero General Public License (AGPL). See [LICENSE](LICENSE.txt).

Copyright FalkorDB Ltd. 2025

