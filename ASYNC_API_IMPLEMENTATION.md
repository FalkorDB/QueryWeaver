# QueryWeaver Async API Implementation

## Overview

Successfully added a full async API to the QueryWeaver library, providing high-performance async/await support for applications that can benefit from concurrency.

## What Was Added

### 1. AsyncQueryWeaverClient Class

Created a complete async version of the QueryWeaver client with:

- **Same Interface**: All methods match the sync API but with `async`/`await`
- **Context Manager Support**: `async with` for automatic resource cleanup
- **Concurrent Operations**: Multiple operations can run simultaneously
- **Performance Benefits**: Non-blocking I/O for better throughput

### 2. Async Methods

All major operations are now available in async versions:

- `async load_database()` - Load database schemas asynchronously
- `async text_to_sql()` - Generate SQL with async processing
- `async query()` - Full query processing with async execution
- `async get_database_schema()` - Retrieve schema information asynchronously

### 3. Context Manager Support

```python
async with AsyncQueryWeaverClient(...) as client:
    await client.load_database(...)
    sql = await client.text_to_sql(...)
# Automatically closed when exiting context
```

### 4. Concurrency Features

#### Concurrent Database Loading
```python
await asyncio.gather(
    client.load_database("db1", "postgresql://..."),
    client.load_database("db2", "mysql://..."),
    client.load_database("db3", "postgresql://...")
)
```

#### Concurrent Query Processing
```python
queries = ["query 1", "query 2", "query 3"]
results = await asyncio.gather(*[
    client.text_to_sql("mydb", query) for query in queries
])
```

#### Batch Processing with Resource Management
```python
async def process_in_batches(queries, batch_size=5):
    for i in range(0, len(queries), batch_size):
        batch = queries[i:i + batch_size]
        batch_results = await asyncio.gather(*[
            client.text_to_sql("mydb", q) for q in batch
        ])
        await asyncio.sleep(0.1)  # Brief pause between batches
```

## Technical Implementation

### Design Approach

1. **Composition over Inheritance**: AsyncQueryWeaverClient uses the sync client for initialization logic, then provides its own async methods
2. **Native Async**: All I/O operations use the existing async infrastructure from QueryWeaver core
3. **Same API Surface**: Method signatures match the sync version for easy migration
4. **Resource Management**: Proper cleanup with context managers

### Key Features

- **Non-blocking Operations**: All database and AI operations are non-blocking
- **Error Handling**: Same exception types and error handling as sync API
- **Memory Efficiency**: Shared state with sync client where possible
- **Type Hints**: Full type annotation support
- **Context Managers**: `async with` support for automatic cleanup

## Usage Patterns

### Basic Async Usage
```python
import asyncio
from queryweaver import AsyncQueryWeaverClient

async def main():
    async with AsyncQueryWeaverClient(
        falkordb_url="redis://localhost:6379/0",
        openai_api_key="your-api-key"
    ) as client:
        
        await client.load_database("mydb", "postgresql://...")
        sql = await client.text_to_sql("mydb", "Show all customers")
        result = await client.query("mydb", "Count orders")

asyncio.run(main())
```

### High-Performance Concurrent Processing
```python
async def process_many_queries():
    async with AsyncQueryWeaverClient(...) as client:
        await client.load_database("mydb", "postgresql://...")
        
        # Process 100 queries concurrently in batches
        queries = [f"Query {i}" for i in range(100)]
        
        results = []
        for i in range(0, len(queries), 10):  # Batches of 10
            batch = queries[i:i+10]
            batch_results = await asyncio.gather(*[
                client.text_to_sql("mydb", query) for query in batch
            ], return_exceptions=True)
            results.extend(batch_results)
```

### Mixed Sync/Async Applications
```python
# You can use both APIs in the same application
from queryweaver import QueryWeaverClient, AsyncQueryWeaverClient

# Sync API for simple operations
sync_client = QueryWeaverClient(...)
sync_client.load_database("mydb", "postgresql://...")

# Async API for high-performance operations
async def process_batch():
    async_client = AsyncQueryWeaverClient(...)
    async_client._loaded_databases = sync_client._loaded_databases  # Share state
    
    queries = ["query1", "query2", "query3"]
    return await asyncio.gather(*[
        async_client.text_to_sql("mydb", q) for q in queries
    ])
```

## Performance Benefits

### Concurrency
- **Multiple Queries**: Process many queries simultaneously
- **Database Loading**: Load multiple database schemas in parallel
- **I/O Overlap**: Hide network latency with concurrent operations

### Resource Efficiency
- **Memory**: Shared state between sync and async clients where possible
- **Connections**: Async operations don't block threads
- **Throughput**: Much higher query throughput for batch operations

### Scalability
- **Event Loop**: Integrates with existing async applications
- **Backpressure**: Built-in support for rate limiting with batching
- **Resource Management**: Proper cleanup with context managers

## Testing

Comprehensive test suite added:

- **Unit Tests**: All async methods tested with mocking
- **Context Manager Tests**: Async context manager functionality
- **Concurrency Tests**: Parallel operation testing
- **Error Handling**: Exception propagation in async context
- **Integration Tests**: Real async operation testing

## Files Added/Modified

### New Files
- `examples/async_library_usage.py` - Comprehensive async examples
- `tests/test_async_library_api.py` - Async API unit tests

### Modified Files
- `queryweaver.py` - Added AsyncQueryWeaverClient class
- `__init__.py` - Export async classes
- `docs/library-usage.md` - Added async documentation

## Migration Guide

### From Sync to Async

```python
# Sync version
client = QueryWeaverClient(...)
client.load_database("mydb", "postgresql://...")
sql = client.text_to_sql("mydb", "query")

# Async version
async with AsyncQueryWeaverClient(...) as client:
    await client.load_database("mydb", "postgresql://...")
    sql = await client.text_to_sql("mydb", "query")
```

### Adding Concurrency

```python
# Sequential processing (slow)
results = []
for query in queries:
    result = await client.text_to_sql("mydb", query)
    results.append(result)

# Concurrent processing (fast)
results = await asyncio.gather(*[
    client.text_to_sql("mydb", query) for query in queries
])
```

## Best Practices

1. **Use Context Managers**: Always use `async with` for automatic cleanup
2. **Batch Operations**: Process multiple queries concurrently when possible
3. **Rate Limiting**: Use batches to avoid overwhelming the system
4. **Error Handling**: Use `return_exceptions=True` in `asyncio.gather()` for robust error handling
5. **Resource Management**: Call `await client.close()` if not using context managers

## Future Enhancements

The async API provides a foundation for:

1. **Connection Pooling**: Async database connection pools
2. **Streaming Results**: Async generators for large result sets
3. **Real-time Processing**: WebSocket integration for real-time queries
4. **Distributed Processing**: Integration with async task queues
5. **Monitoring**: Async metrics and monitoring integration

## Conclusion

The async API provides significant performance benefits for applications that need to process multiple queries or can benefit from concurrent operations. It maintains the same simple, intuitive interface as the sync API while enabling high-performance async/await patterns.