"""
QueryWeaver Library Usage Examples

This file demonstrates how to use the QueryWeaver Python library for Text2SQL operations.
"""

import os
from queryweaver import QueryWeaverClient, create_client

# Example 1: Basic Usage
def basic_example():
    """Basic usage example with PostgreSQL database."""
    print("=== Basic Usage Example ===")
    
    # Initialize the client
    client = QueryWeaverClient(
        falkordb_url="redis://localhost:6379/0",
        openai_api_key="your-openai-api-key"  # or use environment variable
    )
    
    # Load a database schema
    try:
        success = client.load_database(
            database_name="ecommerce",
            database_url="postgresql://user:password@localhost:5432/ecommerce_db"
        )
        print(f"Database loaded successfully: {success}")
    except Exception as e:
        print(f"Error loading database: {e}")
        return
    
    # Generate SQL from natural language
    try:
        sql = client.text_to_sql(
            database_name="ecommerce",
            query="Show all customers from California"
        )
        print(f"Generated SQL: {sql}")
    except Exception as e:
        print(f"Error generating SQL: {e}")
    
    # Execute query and get results
    try:
        result = client.query(
            database_name="ecommerce", 
            query="How many orders were placed last month?",
            execute_sql=True
        )
        print(f"SQL: {result['sql_query']}")
        print(f"Results: {result['results']}")
        if result['analysis']:
            print(f"Explanation: {result['analysis']['explanation']}")
    except Exception as e:
        print(f"Error executing query: {e}")


# Example 2: Using Environment Variables and Convenience Function
def environment_example():
    """Example using environment variables and convenience function."""
    print("\n=== Environment Variables Example ===")
    
    # Set environment variables (you can also set these in your shell)
    os.environ["OPENAI_API_KEY"] = "your-openai-api-key"
    os.environ["FALKORDB_URL"] = "redis://localhost:6379/0"
    
    # Create client using convenience function
    client = create_client(
        falkordb_url=os.environ["FALKORDB_URL"],
        openai_api_key=os.environ["OPENAI_API_KEY"]
    )
    
    # Load multiple databases
    databases = [
        ("sales", "postgresql://user:pass@localhost:5432/sales"),
        ("inventory", "mysql://user:pass@localhost:3306/inventory")
    ]
    
    for db_name, db_url in databases:
        try:
            client.load_database(db_name, db_url)
            print(f"Loaded database: {db_name}")
        except Exception as e:
            print(f"Failed to load {db_name}: {e}")
    
    # List loaded databases
    loaded_dbs = client.list_loaded_databases()
    print(f"Loaded databases: {loaded_dbs}")


# Example 3: Advanced Usage with Chat History
def advanced_example():
    """Advanced usage with chat history and instructions."""
    print("\n=== Advanced Usage Example ===")
    
    client = QueryWeaverClient(
        falkordb_url="redis://localhost:6379/0",
        openai_api_key="your-openai-api-key"
    )
    
    # Load database
    client.load_database(
        "analytics", 
        "postgresql://user:pass@localhost:5432/analytics"
    )
    
    # Use chat history for context
    chat_history = [
        "Show me sales data for 2023",
        "Filter that by region = 'North America'", 
    ]
    
    # Add follow-up query with context
    result = client.query(
        database_name="analytics",
        query="Now group by month and show totals",
        chat_history=chat_history,
        instructions="Use proper date formatting and include percentage calculations",
        execute_sql=False  # Just generate SQL, don't execute
    )
    
    print(f"Context-aware SQL: {result['sql_query']}")
    if result['analysis']:
        print(f"Assumptions: {result['analysis']['assumptions']}")
        print(f"Ambiguities: {result['analysis']['ambiguities']}")


# Example 4: Error Handling and Schema Inspection
def error_handling_example():
    """Example showing error handling and schema inspection."""
    print("\n=== Error Handling Example ===")
    
    try:
        client = QueryWeaverClient(
            falkordb_url="redis://localhost:6379/0",
            openai_api_key="your-openai-api-key"
        )
        
        # Try to query without loading database first
        try:
            client.text_to_sql("nonexistent", "show data")
        except ValueError as e:
            print(f"Expected error - database not loaded: {e}")
        
        # Load a database and inspect schema
        client.load_database("test_db", "postgresql://user:pass@localhost/test")
        
        try:
            schema = client.get_database_schema("test_db")
            print(f"Database schema keys: {list(schema.keys())}")
        except Exception as e:
            print(f"Error getting schema: {e}")
            
    except ConnectionError as e:
        print(f"Connection error: {e}")
    except ValueError as e:
        print(f"Configuration error: {e}")


# Example 5: Azure OpenAI Usage
def azure_example():
    """Example using Azure OpenAI instead of OpenAI."""
    print("\n=== Azure OpenAI Example ===")
    
    client = QueryWeaverClient(
        falkordb_url="redis://localhost:6379/0",
        azure_api_key="your-azure-api-key",
        completion_model="azure/gpt-4",
        embedding_model="azure/text-embedding-ada-002"
    )
    
    # Use the client normally
    client.load_database("azure_db", "postgresql://user:pass@host/db")
    
    sql = client.text_to_sql(
        "azure_db", 
        "Find customers with high lifetime value"
    )
    print(f"Generated with Azure models: {sql}")


# Example 6: Batch Processing
def batch_processing_example():
    """Example showing how to process multiple queries efficiently."""
    print("\n=== Batch Processing Example ===")
    
    client = QueryWeaverClient(
        falkordb_url="redis://localhost:6379/0",
        openai_api_key="your-openai-api-key"
    )
    
    client.load_database("reporting", "postgresql://user:pass@host/reporting")
    
    # Process multiple related queries
    queries = [
        "What is the total revenue this year?",
        "How does that compare to last year?", 
        "Which product category performed best?",
        "Show monthly breakdown for the top category"
    ]
    
    chat_history = []
    for i, query in enumerate(queries):
        print(f"\nQuery {i+1}: {query}")
        
        try:
            result = client.query(
                database_name="reporting",
                query=query,
                chat_history=chat_history.copy(),
                execute_sql=False
            )
            
            print(f"SQL: {result['sql_query']}")
            
            # Add to history for context in next queries
            chat_history.append(query)
            
        except Exception as e:
            print(f"Error processing query {i+1}: {e}")


if __name__ == "__main__":
    """Run all examples. Adjust database URLs and API keys as needed."""
    
    print("QueryWeaver Library Examples")
    print("============================")
    print("Note: Update database URLs and API keys before running!")
    print()
    
    # Uncomment the examples you want to run:
    
    # basic_example()
    # environment_example() 
    # advanced_example()
    # error_handling_example()
    # azure_example()
    # batch_processing_example()
    
    print("\nTo run examples, uncomment the function calls at the bottom of this file")
    print("and update the database URLs and API keys with your actual values.")