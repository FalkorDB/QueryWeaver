"""QueryWeaver SDK - Python client for Text2SQL functionality.

This module provides the main QueryWeaver class for converting natural
language questions to SQL queries without requiring a web server.

Note: This module uses lazy imports (import-outside-toplevel) intentionally.
The api.* modules require FalkorDB connection at import time, so we defer
importing them until methods are called. This allows:
- `from queryweaver_sdk import QueryWeaver` to succeed without FalkorDB
- Type hints to work via TYPE_CHECKING block
- Runtime imports only when SDK methods are actually used

Example usage:
    ```python
    from queryweaver_sdk import QueryWeaver

    async def main():
        qw = QueryWeaver(falkordb_url="redis://localhost:6379")
        await qw.connect_database("postgresql://user:pass@host/mydb")

        result = await qw.query("mydb", "Show me all customers from NYC")
        print(result.sql_query)
        print(result.results)
    ```
"""
# pylint: disable=import-outside-toplevel
# Lazy imports are required - see module docstring for explanation

import os
from typing import Optional, Union

from queryweaver_sdk.connection import FalkorDBConnection
from queryweaver_sdk.models import (
    QueryResult,
    SchemaResult,
    DatabaseConnection,
    RefreshResult,
    QueryRequest,
)


class QueryWeaver:
    """Python SDK for Text2SQL functionality.

    This class provides a programmatic interface to QueryWeaver's text-to-SQL
    capabilities without requiring a running web server.

    Attributes:
        user_id: Identifier for namespacing databases (default: "default").
    """

    def __init__(
        self,
        falkordb_url: Optional[str] = None,
        user_id: str = "default",
    ):
        """Initialize QueryWeaver SDK.

        Args:
            falkordb_url: Redis URL for FalkorDB connection.
                         Falls back to FALKORDB_URL environment variable.
            user_id: User identifier for database namespacing.
                    Defaults to "default" for single-user scenarios.

        Raises:
            ConnectionError: If FalkorDB connection cannot be established.
        """
        self._user_id = user_id
        self._connection = FalkorDBConnection(url=falkordb_url)
        self._general_prefix = os.getenv("GENERAL_PREFIX")

        # Inject our connection into the api.extensions module
        # This allows the existing core functions to use our connection
        self._setup_connection()

    def _setup_connection(self) -> None:
        """Set up the connection for use by core modules.
        
        Note: api.extensions is imported lazily to allow SDK import
        without requiring FalkorDB connection at module load time.
        """
        import api.extensions
        api.extensions.db = self._connection.db

    @property
    def user_id(self) -> str:
        """Get the user ID used for database namespacing."""
        return self._user_id

    def _graph_name(self, graph_id: str) -> str:
        """Get the namespaced graph name.

        Args:
            graph_id: The user-facing graph/database identifier.

        Returns:
            The namespaced graph name for internal use.
        """
        graph_id = graph_id.strip()[:200]
        if not graph_id:
            raise ValueError("Invalid graph_id, must be non-empty and less than 200 characters.")

        if self._general_prefix and graph_id.startswith(self._general_prefix):
            return graph_id

        return f"{self._user_id}_{graph_id}"

    async def connect_database(self, db_url: str) -> DatabaseConnection:
        """Connect to a SQL database and load its schema.

        This method connects to the specified database, introspects its schema,
        and loads it into FalkorDB for query processing.

        Args:
            db_url: Database connection URL. Supported formats:
                   - PostgreSQL: "postgresql://user:pass@host:port/dbname"
                   - MySQL: "mysql://user:pass@host:port/dbname"

        Returns:
            DatabaseConnection with connection status and details.

        Raises:
            ValueError: If the database URL format is invalid.
        """
        from api.core.schema_loader import load_database_sync
        return await load_database_sync(db_url, self._user_id)

    async def query(
        self,
        database: str,
        question: Union[str, QueryRequest],
    ) -> QueryResult:
        """Convert natural language to SQL and execute.

        Can be called with a simple question string or a QueryRequest for advanced options.

        Args:
            database: The database identifier to query.
            question: Either a natural language question string, or a QueryRequest
                     object with full conversation context and options.

        Returns:
            QueryResult with SQL query, results, and AI response.

        Raises:
            ValueError: If the question is empty or database not found.

        Examples:
            Simple usage:
                result = await qw.query("mydb", "Show all customers")

            Advanced usage with context:
                request = QueryRequest(
                    question="Show their orders",
                    chat_history=["Show all customers"],
                    result_history=["Found 10 customers"],
                    instructions="Use customer_id for joins",
                )
                result = await qw.query("mydb", request)
        """
        from api.core.text2sql_sync import query_database_sync
        from api.core.text2sql import ChatRequest

        # Handle both string and QueryRequest inputs
        if isinstance(question, str):
            if not question or not question.strip():
                raise ValueError("Question cannot be empty")
            request = QueryRequest(question=question)
        else:
            request = question
            if not request.question or not request.question.strip():
                raise ValueError("Question cannot be empty")

        # Build chat history with current question
        history = list(request.chat_history or [])
        history.append(request.question)

        chat_data = ChatRequest(
            chat=history,
            result=request.result_history,
            instructions=request.instructions,
            use_user_rules=request.use_user_rules,
            use_memory=request.use_memory,
        )

        return await query_database_sync(self._user_id, database, chat_data)

    async def get_schema(self, database: str) -> SchemaResult:
        """Get the schema for a connected database.

        Args:
            database: The database identifier.

        Returns:
            SchemaResult with tables (nodes) and relationships (links).

        Raises:
            ValueError: If the database is not found.
        """
        from api.core.text2sql import get_schema as _get_schema
        schema = await _get_schema(self._user_id, database)
        return SchemaResult(
            nodes=schema.get("nodes", []),
            links=schema.get("links", []),
        )

    async def list_databases(self) -> list[str]:
        """List all available databases for this user.

        Returns:
            List of database identifiers.
        """
        from api.core.schema_loader import list_databases as _list_databases
        return await _list_databases(self._user_id, self._general_prefix)

    async def delete_database(self, database: str) -> bool:
        """Delete a connected database.

        This removes the database schema from FalkorDB. It does not
        affect the actual SQL database.

        Args:
            database: The database identifier to delete.

        Returns:
            True if deletion was successful.

        Raises:
            ValueError: If the database is not found or cannot be deleted.
        """
        from api.core.text2sql import delete_database as _delete_database
        result = await _delete_database(self._user_id, database)
        return result.get("success", False)

    async def refresh_schema(self, database: str) -> RefreshResult:
        """Refresh the schema for a connected database.

        Re-introspects the source database and updates the schema graph.
        Useful after schema changes in the source database.

        Args:
            database: The database identifier to refresh.

        Returns:
            RefreshResult with refresh status.

        Raises:
            ValueError: If the database is not found.
        """
        from api.core.text2sql_sync import refresh_database_schema_sync
        return await refresh_database_schema_sync(self._user_id, database)

    async def execute_confirmed(
        self,
        database: str,
        sql_query: str,
        chat_history: Optional[list[str]] = None,
    ) -> QueryResult:
        """Execute a confirmed destructive SQL operation.

        Use this method to execute INSERT, UPDATE, DELETE, or other
        destructive operations that were flagged for confirmation.

        Args:
            database: The database identifier.
            sql_query: The SQL query to execute.
            chat_history: Conversation context.

        Returns:
            QueryResult with execution results.
        """
        from api.core.text2sql_sync import execute_destructive_operation_sync
        from api.core.text2sql import ConfirmRequest

        confirm_data = ConfirmRequest(
            sql_query=sql_query,
            confirmation="CONFIRM",
            chat=chat_history or [],
        )

        return await execute_destructive_operation_sync(
            self._user_id, database, confirm_data
        )

    async def close(self) -> None:
        """Close the SDK connection and release resources."""
        await self._connection.close()

    async def __aenter__(self) -> "QueryWeaver":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
