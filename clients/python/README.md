# QueryWeaver Python client

Lightweight Python client for interacting with a QueryWeaver server.

This folder contains a small package, `queryweaver_client`, that wraps the
QueryWeaver HTTP API. The package is dependency-light (requests) and is
configured to be used with pipenv (Pipfile) or a plain virtualenv.

## Getting started

### Install from PyPI (end users)

If you just want to use the client (not develop it), install the published package from PyPI:

```bash
pip install queryweaver_client
```

This installs the latest released version. For development and tests use the pipenv/venv instructions below.

### Usage example

Basic usage (API token auth):

```python
from queryweaver_client import QueryWeaverClient

client = QueryWeaverClient("http://localhost:5000", api_token="YOUR_API_TOKEN")
print(client.list_graphs())

# Streaming example for database connect
for msg in client.connect_database("postgresql://user:pass@host/db"):
  print(msg)

# Example: run a natural language query against a loaded graph
# `chat_data` should match the server's ChatRequest shape; a minimal example:
chat_data = {
  "messages": [
    {"role": "user", "content": "List the top 5 customers by total_spend"}
  ]
}

for event in client.query("my_database_graph", chat_data):
  # each event is a JSON chunk from the server (progress/result/SQL/etc.)
  print(event)
```


## Build from code (developers)


### Quick install (pipenv - recommended)

1. Change to the client directory:

```bash
cd ./clients/python
```

2. Install dependencies and the package into a pipenv virtualenv (editable install supported):

```bash
pipenv install --dev
# Install the local package into the pipenv virtualenv in editable mode
pipenv install -e .
```

### Running tests

Unit tests live in `tests/` and are lightweight (they mock network calls and do NOT
require a running QueryWeaver server). Use pytest to run them.

With pipenv:

```bash
pipenv run pytest -q
```

With venv/pip:

```bash
pytest -q
```

Run a single test file or test:

```bash
pytest -q tests/test_client_basic.py
pytest -q tests/test_client_basic.py::test_connect_database_stream
```

## Notes & troubleshooting
-----------------------
- The `Pipfile` specifies Python 3.12; use a compatible interpreter if you need exact parity.
- If `pipenv install` fails because `pipenv` isn't available, install it (`pip install pipenv`) or use the plain venv flow above.
- The client supports two auth modes:
  - API token: pass `api_token` to `QueryWeaverClient` (sent as Bearer Authorization header)
  - Session cookie: construct a `requests.Session()` with cookies (for web OAuth session flows) and pass it to `QueryWeaverClient(session=your_session)`
- Streaming endpoints try to parse JSON per-line; if you want strict delimiter handling (server uses an internal message delimiter), tell me and I can wire the exact delimiter into parsing.

## Want more?
-----------
If you'd like typed request/response models (pydantic), better streaming helpers, or integration tests that run against a local QueryWeaver instance (requires FalkorDB and env setup), I can add those next.
