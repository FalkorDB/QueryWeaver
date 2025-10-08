# QueryWeaver Python client

Lightweight Python client for interacting with a QueryWeaver server.

This folder contains a small package, `queryweaver_client`, that wraps the
QueryWeaver HTTP API. The package uses aiohttp for async HTTP requests and is
configured to be used with pipenv (Pipfile) or a plain virtualenv.

## Getting started

### Install from PyPI (end users)

If you just want to use the client (not develop it), install the published package from PyPI:

```bash
pip install queryweaver-client
```

This installs the latest released version. For development and tests use the pipenv/venv instructions below.

### Usage example

Basic async usage (API token auth):

```python
import asyncio
from queryweaver_client import QueryWeaverClient

async def main():
    async with QueryWeaverClient("http://localhost:5000", api_token="YOUR_API_TOKEN") as client:
        # List available databases/schemas
        schemas = await client.list_schemas()
        print(schemas)

        # Connect to a database and get the final result
        result = await client.connect_database("postgresql://user:pass@host/db")
        print(result)

        # Run a natural language query and get the final result
        chat_data = {
            "messages": [
                {"role": "user", "content": "List the top 5 customers by total_spend"}
            ]
        }
        result = await client.query("my_database_schema", chat_data)
        print(result)

# Run the async function
asyncio.run(main())
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
pytest -q tests/test_client_basic.py::test_connect_database_sync
```

## Notes & troubleshooting
-----------------------
- The `Pipfile` specifies Python 3.12; use a compatible interpreter if you need exact parity.
- If `pipenv install` fails because `pipenv` isn't available, install it (`pip install pipenv`) or use the plain venv flow above.
- The client supports two auth modes:
  - API token: pass `api_token` to `QueryWeaverClient` (sent as Bearer Authorization header)
  - Session cookie: construct an `aiohttp.ClientSession()` with cookies (for web OAuth session flows) and pass it to `QueryWeaverClient(session=your_session)`
- All API calls are async and must be awaited
- Use the client as an async context manager (`async with`) for proper session lifecycle management

## Want more?
-----------
If you'd like typed request/response models (pydantic), better streaming helpers, or integration tests that run against a local QueryWeaver instance (requires FalkorDB and env setup), I can add those next.
