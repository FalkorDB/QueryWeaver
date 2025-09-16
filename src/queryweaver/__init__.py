"""
QueryWeaver Python Library

A Python library for Text2SQL using graph-powered schema understanding.

This package provides both synchronous and asynchronous clients for
QueryWeaver functionality, allowing you to:
- Load database schemas from PostgreSQL or MySQL
- Generate SQL from natural language queries  
- Execute queries and return results
- Work with FalkorDB for schema storage

Quick Start:

Synchronous API:
    from queryweaver import QueryWeaverClient
    
    client = QueryWeaverClient(
        falkordb_url="redis://localhost:6379/0",
        openai_api_key="your-api-key"
    )
    
    client.load_database("mydatabase", "postgresql://user:pass@host:port/db")
    sql = client.text_to_sql("mydatabase", "Show all customers from California")
    results = client.query("mydatabase", "Show all customers from California")

Asynchronous API:
    from queryweaver import AsyncQueryWeaverClient
    import asyncio
    
    async def main():
        async with AsyncQueryWeaverClient(
            falkordb_url="redis://localhost:6379/0",
            openai_api_key="your-api-key"
        ) as client:
            await client.load_database("mydatabase", "postgresql://user:pass@host:port/db")
            sql = await client.text_to_sql("mydatabase", "Show all customers")
            results = await client.query("mydatabase", "Show all customers")
    
    asyncio.run(main())
"""

# Package metadata
__version__ = "0.1.0"
__author__ = "FalkorDB"
__description__ = "Python library for Text2SQL using graph-powered schema understanding"
__license__ = "MIT"

# Import main classes with fallback for optional dependencies
try:
    from .sync import QueryWeaverClient, create_client
    _sync_available = True
except ImportError as e:
    import warnings
    warnings.warn(
        f"Sync QueryWeaver client not available due to missing dependencies: {e}. "
        "Please install all required dependencies.",
        ImportWarning
    )
    QueryWeaverClient = None
    create_client = None
    _sync_available = False

try:
    from .async_client import AsyncQueryWeaverClient, create_async_client
    _async_available = True
except ImportError as e:
    import warnings
    warnings.warn(
        f"Async QueryWeaver client not available due to missing dependencies: {e}. "
        "Please install all required dependencies.",
        ImportWarning
    )
    AsyncQueryWeaverClient = None
    create_async_client = None
    _async_available = False

# Build __all__ based on what's available
__all__ = []
if _sync_available:
    __all__.extend(["QueryWeaverClient", "create_client"])
if _async_available:
    __all__.extend(["AsyncQueryWeaverClient", "create_async_client"])