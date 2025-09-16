# QueryWeaver Python Library

QueryWeaver can be used as a Python library for direct integration into your applications, without running the FastAPI server. The library provides both synchronous and asynchronous APIs.

## Installation

### From Source
```bash
# Clone the repository
git clone https://github.com/FalkorDB/QueryWeaver.git
cd QueryWeaver

# Install as a library
pip install -e .

# Or install with development dependencies
pip install -e ".[dev]"
```

### Dependencies
The library requires:
- Python 3.11+
- FalkorDB (for schema storage)
- OpenAI API key or Azure OpenAI credentials

## Quick Start

### Synchronous API
```python
from queryweaver import QueryWeaverClient

# Initialize client
client = QueryWeaverClient(
    falkordb_url="redis://localhost:6379/0",
    openai_api_key="your-api-key"
)

# Load a database schema
client.load_database("mydb", "postgresql://user:pass@host:port/database")

# Generate SQL from natural language
sql = client.text_to_sql("mydb", "Show all customers from California")
print(sql)  # SELECT * FROM customers WHERE state = 'CA'

# Execute query and get results
result = client.query("mydb", "How many orders were placed last month?")
print(result['sql_query'])  # Generated SQL
print(result['results'])    # Query results
```

### Asynchronous API
```python
import asyncio
from queryweaver import AsyncQueryWeaverClient

async def main():
    # Initialize async client with context manager
    async with AsyncQueryWeaverClient(
        falkordb_url="redis://localhost:6379/0",
        openai_api_key="your-api-key"
    ) as client:
        
        # Load database schema (async)
        await client.load_database("mydb", "postgresql://user:pass@host/db")
        
        # Generate SQL (async)
        sql = await client.text_to_sql("mydb", "Show all customers")
        print(sql)
        
        # Execute query (async)
        result = await client.query("mydb", "Count total orders")
        print(result['results'])

# Run async code
asyncio.run(main())
```

## API Reference

### Synchronous API

#### QueryWeaverClient

##### `__init__(falkordb_url, openai_api_key=None, azure_api_key=None, ...)`
Initialize the QueryWeaver client.

**Parameters:**
- `falkordb_url` (str): Redis URL for FalkorDB connection
- `openai_api_key` (str, optional): OpenAI API key
- `azure_api_key` (str, optional): Azure OpenAI API key (alternative to OpenAI)
- `completion_model` (str, optional): Override default completion model
- `embedding_model` (str, optional): Override default embedding model

##### `load_database(database_name, database_url)`
Load a database schema into FalkorDB for querying.

**Parameters:**
- `database_name` (str): Unique identifier for this database
- `database_url` (str): Connection URL (PostgreSQL or MySQL)

**Returns:** `bool` - True if successful

##### `text_to_sql(database_name, query, instructions=None, chat_history=None)`
Generate SQL from natural language query.

**Parameters:**
- `database_name` (str): Name of loaded database
- `query` (str): Natural language query
- `instructions` (str, optional): Additional instructions for SQL generation
- `chat_history` (list, optional): Previous queries for context

**Returns:** `str` - Generated SQL query

##### `query(database_name, query, instructions=None, chat_history=None, execute_sql=True)`
Generate and optionally execute SQL query.

**Parameters:**
- `database_name` (str): Name of loaded database
- `query` (str): Natural language query
- `instructions` (str, optional): Additional instructions
- `chat_history` (list, optional): Previous queries for context
- `execute_sql` (bool): Whether to execute SQL or just generate it

**Returns:** `dict` with keys:
- `sql_query` (str): Generated SQL
- `results` (list): Query results (if executed)
- `error` (str): Error message (if any)
- `analysis` (dict): Query analysis with explanation, assumptions, etc.

##### `list_loaded_databases()`
Get list of currently loaded databases.

**Returns:** `list[str]` - Database names

##### `get_database_schema(database_name)`
Get schema information for a loaded database.

**Returns:** `dict` - Schema information

### Asynchronous API

#### AsyncQueryWeaverClient

The async client provides the same methods as the synchronous client, but all I/O operations are async:

##### `async load_database(database_name, database_url)`
Async version of database loading.

##### `async text_to_sql(database_name, query, instructions=None, chat_history=None)`
Async version of SQL generation.

##### `async query(database_name, query, instructions=None, chat_history=None, execute_sql=True)`
Async version of query execution.

##### `async get_database_schema(database_name)`
Async version of schema retrieval.

##### `async close()`
Close the async client and cleanup resources.

##### Context Manager Support
The async client supports async context managers:

```python
async with AsyncQueryWeaverClient(...) as client:
    # Use client
    await client.load_database(...)
# Automatically closed when exiting context
```

## Concurrency and Performance

### Concurrent Operations
The async API allows for concurrent operations:

```python
async with AsyncQueryWeaverClient(...) as client:
    # Load multiple databases concurrently
    await asyncio.gather(
        client.load_database("db1", "postgresql://..."),
        client.load_database("db2", "mysql://..."),
        client.load_database("db3", "postgresql://...")
    )
    
    # Process multiple queries concurrently
    queries = ["query 1", "query 2", "query 3"]
    sql_results = await asyncio.gather(*[
        client.text_to_sql("db1", query) for query in queries
    ])
```

### Batch Processing
```python
async def process_queries_in_batches(client, queries, batch_size=5):
    """Process queries in batches for better resource management."""
    results = []
    for i in range(0, len(queries), batch_size):
        batch = queries[i:i + batch_size]
        batch_results = await asyncio.gather(*[
            client.text_to_sql("mydb", query) for query in batch
        ], return_exceptions=True)
        results.extend(batch_results)
        await asyncio.sleep(0.1)  # Brief pause between batches
    return results
```

## Environment Variables

You can use environment variables instead of passing API keys directly:

```bash
export OPENAI_API_KEY="your-openai-key"
export AZURE_API_KEY="your-azure-key"
export FALKORDB_URL="redis://localhost:6379/0"
```

```python
import os
from queryweaver import create_client, create_async_client

# Sync client
client = create_client(
    falkordb_url=os.environ["FALKORDB_URL"],
    openai_api_key=os.environ.get("OPENAI_API_KEY")
)

# Async client
async_client = create_async_client(
    falkordb_url=os.environ["FALKORDB_URL"],
    openai_api_key=os.environ.get("OPENAI_API_KEY")
)
```

## Supported Databases

The library supports loading schemas from:
- **PostgreSQL**: `postgresql://user:pass@host:port/database`
- **MySQL**: `mysql://user:pass@host:port/database`

## Examples

See `examples/library_usage.py` for comprehensive usage examples including:
- Basic usage
- Error handling
- Chat history and context
- Azure OpenAI integration
- Batch processing

## Error Handling

The library raises specific exceptions:
- `ValueError`: Invalid parameters or configuration
- `ConnectionError`: Cannot connect to FalkorDB or source database
- `RuntimeError`: Processing errors (SQL generation, execution, etc.)

```python
try:
    client = QueryWeaverClient(falkordb_url="redis://localhost:6379")
    client.load_database("test", "postgresql://user:pass@host/db")
    sql = client.text_to_sql("test", "show data")
except ConnectionError as e:
    print(f"Connection failed: {e}")
except ValueError as e:
    print(f"Invalid configuration: {e}")
except RuntimeError as e:
    print(f"Processing error: {e}")
```