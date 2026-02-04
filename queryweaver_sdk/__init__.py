"""QueryWeaver SDK - Text2SQL without a server.

This package provides a Python SDK for QueryWeaver's text-to-SQL
functionality, allowing you to convert natural language questions
to SQL queries directly in your Python applications.

Example:
    ```python
    from queryweaver_sdk import QueryWeaver
    
    async def main():
        qw = QueryWeaver(falkordb_url="redis://localhost:6379")
        await qw.connect_database("postgresql://user:pass@host/mydb")
        
        result = await qw.query("mydb", "Show me all customers from NYC")
        print(result.sql_query)   # SELECT * FROM customers WHERE city = 'NYC'
        print(result.results)      # [{"id": 1, "name": "John", "city": "NYC"}, ...]
        print(result.ai_response)  # "Found 42 customers from New York City..."
    ```

Requirements:
    - FalkorDB instance (local or remote)
    - OpenAI or Azure OpenAI API key
    - Target SQL database (PostgreSQL or MySQL)
"""

from queryweaver_sdk.client import QueryWeaver
from queryweaver_sdk.models import (
    QueryResult,
    SchemaResult,
    DatabaseConnection,
    RefreshResult,
    QueryRequest,
    ChatMessage,
)
from queryweaver_sdk.connection import FalkorDBConnection

__all__ = [
    "QueryWeaver",
    "QueryResult",
    "SchemaResult", 
    "DatabaseConnection",
    "RefreshResult",
    "QueryRequest",
    "ChatMessage",
    "FalkorDBConnection",
]

__version__ = "0.1.0"
