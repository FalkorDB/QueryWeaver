"""
QueryWeaver Async Library Usage Examples

This file demonstrates how to use the async version of the QueryWeaver Python
library for high-performance applications that can benefit from async/await
patterns.
"""

import asyncio
import time
from queryweaver import AsyncQueryWeaverClient, create_async_client


# Example 1: Basic Async Usage
async def basic_async_example():
    """Basic async usage example with PostgreSQL database."""
    print("=== Basic Async Usage Example ===")

    # Initialize the async client
    async with AsyncQueryWeaverClient(
        falkordb_url="redis://localhost:6379/0",
        openai_api_key="your-openai-api-key",
    ) as client:

        # Load a database schema
        try:
            success = await client.load_database(
                database_name="ecommerce",
                database_url=(
                    "postgresql://user:password@localhost:5432/ecommerce_db"
                ),
            )
            print(f"Database loaded successfully: {success}")
        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"Error loading database: {e}")
            return

        # Generate SQL from natural language
        try:
            sql = await client.text_to_sql(
                database_name="ecommerce",
                query="Show all customers from California",
            )
            print(f"Generated SQL: {sql}")
        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"Error generating SQL: {e}")

        # Execute query and get results
        try:
            result = await client.query(
                database_name="ecommerce",
                query="How many orders were placed last month?",
                execute_sql=True,
            )
            print(f"SQL: {result['sql_query']}")
            print(f"Results: {result['results']}")
            if result["analysis"]:
                print(f"Explanation: {result['analysis']['explanation']}")
        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"Error executing query: {e}")


# Example 2: Concurrent Query Processing
async def concurrent_queries_example():
    """Example showing concurrent processing of multiple queries."""
    print("\n=== Concurrent Queries Example ===")

    client = AsyncQueryWeaverClient(
        falkordb_url="redis://localhost:6379/0",
        openai_api_key="your-openai-api-key",
    )

    try:
        # Load database first
        await client.load_database(
            "analytics", "postgresql://user:pass@localhost/analytics"
        )

        # Define multiple queries to process concurrently
        queries = [
            "What is the total revenue this year?",
            "How many new customers joined last month?",
            "Which product category has the highest sales?",
            "Show the top 5 customers by order value",
        ]

        # Process all queries concurrently
        print("Processing queries concurrently...")
        tasks = [client.text_to_sql("analytics", query) for query in queries]

        # Wait for all queries to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Display results
        for i, (query, result) in enumerate(zip(queries, results)):
            print(f"\nQuery {i+1}: {query}")
            if isinstance(result, Exception):
                print(f"Error: {result}")
            else:
                print(f"SQL: {result}")

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error in concurrent processing: {e}")
    finally:
        await client.close()


# Example 3: Async Context Manager Pattern
async def context_manager_example():
    """Example using async context manager for automatic cleanup."""
    print("\n=== Context Manager Example ===")

    async with AsyncQueryWeaverClient(
        falkordb_url="redis://localhost:6379/0",
        openai_api_key="your-openai-api-key",
    ) as client:

        # Load multiple databases concurrently
        load_tasks = [
            client.load_database("sales", "postgresql://user:pass@host/sales"),
            client.load_database("inventory", "mysql://user:pass@host/inventory"),
            client.load_database(
                "customers", "postgresql://user:pass@host/customers"
            ),
        ]

        try:
            results = await asyncio.gather(*load_tasks, return_exceptions=True)
            successful_loads = [i for i, r in enumerate(results) if r is True]
            print(f"Successfully loaded {len(successful_loads)} databases")

            # List loaded databases
            loaded_dbs = client.list_loaded_databases()
            print(f"Available databases: {loaded_dbs}")

        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"Error loading databases: {e}")

    # Client is automatically closed when exiting the context


# Example 4: High-Performance Batch Processing
async def batch_processing_example():
    """Example showing high-performance batch processing of queries."""
    print("\n=== Batch Processing Example ===")

    client = create_async_client(
        falkordb_url="redis://localhost:6379/0",
        openai_api_key="your-openai-api-key",
    )

    async with client:

        await client.load_database(
            "reporting", "postgresql://user:pass@host/reporting"
        )

        # Large batch of queries
        query_batch = [
            "Show monthly revenue trends",
            "Calculate customer retention rate",
            "Find top performing products",
            "Analyze seasonal sales patterns",
            "Identify high-value customer segments",
            "Track inventory turnover rates",
            "Measure campaign effectiveness",
            "Analyze geographic sales distribution",
        ]

        print(f"Processing {len(query_batch)} queries in batch...")

        # Process in chunks for better resource management
        chunk_size = 3
        results = []

        for i in range(0, len(query_batch), chunk_size):
            chunk = query_batch[i : i + chunk_size]
            print(f"Processing chunk {i//chunk_size + 1}...")

            # Process chunk concurrently
            chunk_tasks = [
                client.query("reporting", query, execute_sql=False) for query in chunk
            ]

            chunk_results = await asyncio.gather(*chunk_tasks, return_exceptions=True)
            results.extend(chunk_results)

            # Small delay between chunks to avoid overwhelming the system
            await asyncio.sleep(0.1)

        # Display results summary
        successful = sum(1 for r in results if not isinstance(r, Exception))
        print(
            f"Successfully processed {successful}/{len(query_batch)} queries"
        )


# Example 5: Real-time Query Processing with Streaming
async def streaming_example():
    """Example showing real-time processing of queries with chat context."""
    print("\n=== Streaming/Real-time Example ===")

    client = AsyncQueryWeaverClient(
        falkordb_url="redis://localhost:6379/0",
        openai_api_key="your-openai-api-key",
    )

    try:
        await client.load_database(
            "realtime", "postgresql://user:pass@host/realtime"
        )

        # Simulate a conversation with building context
        conversation = [
            "Show me sales data for this year",
            "Filter that by region = 'North America'",
            "Now group by month",
            "Add percentage change from previous month",
            "Highlight months with growth > 10%",
        ]

        chat_history = []

        for i, query in enumerate(conversation):
            print(f"\nStep {i+1}: {query}")

            # Process with accumulated context
            result = await client.query(
                database_name="realtime",
                query=query,
                chat_history=chat_history.copy(),
                execute_sql=False,
            )

            print(f"Generated SQL: {result['sql_query']}")

            if result["analysis"]:
                print(f"AI Analysis: {result['analysis']['explanation']}")

            # Add to conversation history
            chat_history.append(query)

            # Simulate some processing time
            await asyncio.sleep(0.5)

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error in streaming example: {e}")
    finally:
        await client.close()


# Example 6: Error Handling and Resilience
async def error_handling_example():
    """Example showing proper error handling in async context."""
    print("\n=== Error Handling Example ===")

    try:
        async with AsyncQueryWeaverClient(
            falkordb_url="redis://localhost:6379/0",
            openai_api_key="your-openai-api-key",
        ) as client:

            # Try multiple operations with proper error handling
            operations = [
                (
                    "load_valid",
                    lambda: client.load_database(
                        "test", "postgresql://user:pass@host/test"
                    ),
                ),
                ("load_invalid", lambda: client.load_database("", "invalid://url")),
                ("query_unloaded", lambda: client.text_to_sql("nonexistent", "show data")),
                ("query_empty", lambda: client.text_to_sql("test", "")),
            ]

            for name, operation in operations:
                try:
                    result = await operation()
                    print(f"✓ {name}: Success - {result}")
                except ValueError as e:
                    print(f"✗ {name}: ValueError - {e}")
                except RuntimeError as e:
                    print(f"✗ {name}: RuntimeError - {e}")
                except Exception as e:  # pylint: disable=broad-exception-caught
                    print(f"✗ {name}: Unexpected error - {e}")

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Client initialization error: {e}")


# Example 7: Performance Monitoring
async def performance_monitoring_example():
    """Example showing performance monitoring of async operations."""
    print("\n=== Performance Monitoring Example ===")

    async with AsyncQueryWeaverClient(
        falkordb_url="redis://localhost:6379/0",
        openai_api_key="your-openai-api-key",
    ) as client:

        # Time database loading
        start_time = time.time()
        await client.load_database("perf_test", "postgresql://user:pass@host/test")
        load_time = time.time() - start_time
        print(f"Database load time: {load_time:.2f}s")

        # Time SQL generation
        queries = [
            "Show customer statistics",
            "Calculate monthly growth rates",
            "Find top products by revenue",
        ]

        start_time = time.time()
        sql_tasks = [client.text_to_sql("perf_test", q) for q in queries]
        await asyncio.gather(*sql_tasks)
        generation_time = time.time() - start_time
        print(f"SQL generation time (3 queries): {generation_time:.2f}s")
        print(f"Average per query: {generation_time/len(queries):.2f}s")


# Main async function to run all examples
async def main():
    """Run all async examples."""
    print("QueryWeaver Async Library Examples")
    print("==================================")
    print("Note: Update database URLs and API keys before running!")
    print()

    # Uncomment the examples you want to run:

    # await basic_async_example()
    # await concurrent_queries_example()
    # await context_manager_example()
    # await batch_processing_example()
    # await streaming_example()
    # await error_handling_example()
    # await performance_monitoring_example()

    print("To run examples, uncomment the function calls in main() and")
    print("update the database URLs and API keys with your actual values.")


if __name__ == "__main__":
    # Run the async examples
    asyncio.run(main())
