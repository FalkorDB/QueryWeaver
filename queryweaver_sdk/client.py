"""QueryWeaver SDK - Python client for Text2SQL functionality.

This module provides the main QueryWeaver class for converting natural
language questions to SQL queries without requiring a web server.

Note: This module uses lazy imports (import-outside-toplevel) intentionally.
The api.* modules do not need to be loaded until an SDK method is called,
so deferring their import keeps `from queryweaver_sdk import QueryWeaver`
cheap and side-effect-free.

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

import asyncio
from contextlib import contextmanager
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

        Multiple QueryWeaver instances can coexist in the same process —
        each holds its own FalkorDB connection and passes it explicitly
        into core functions, so there is no shared global state to collide.

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
        # Set of in-flight background tasks (memory writes) so close() can
        # await them. Populated via the ``background_tasks_var`` contextvar
        # in ``api.core.text2sql_common``.
        self._pending_tasks: set = set()

    @property
    def _db(self):
        """The FalkorDB handle for this SDK instance."""
        return self._connection.db

    @contextmanager
    def _bind_task_sink(self):
        """Bind this instance's task sink to the current contextvar scope.

        Use as a context manager around any call that may schedule
        background memory writes; close() then awaits them before the pool
        is disconnected.
        """
        from api.core.text2sql_common import background_tasks_var
        token = background_tasks_var.set(self._pending_tasks)
        try:
            yield
        finally:
            background_tasks_var.reset(token)

    @property
    def user_id(self) -> str:
        """Get the user ID used for database namespacing."""
        return self._user_id

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
        return await load_database_sync(db_url, self._user_id, db=self._db)

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
            custom_api_key=request.custom_api_key,
            custom_model=request.custom_model,
        )

        with self._bind_task_sink():
            return await query_database_sync(
                self._user_id, database, chat_data, db=self._db,
            )

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
        schema = await _get_schema(self._user_id, database, db=self._db)
        return SchemaResult(
            nodes=schema.get("nodes", []),
            links=schema.get("links", []),
        )

    async def list_databases(self) -> list[str]:
        """List all available databases for this user.

        Returns:
            List of database identifiers.
        """
        from api.core.schema_loader import list_databases as _list_databases  # pylint: disable=import-outside-toplevel
        from api.core.text2sql_common import GENERAL_PREFIX  # pylint: disable=import-outside-toplevel
        return await _list_databases(self._user_id, GENERAL_PREFIX, db=self._db)

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
        result = await _delete_database(self._user_id, database, db=self._db)
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
        return await refresh_database_schema_sync(self._user_id, database, db=self._db)

    async def execute_confirmed(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        database: str,
        sql_query: str,
        chat_history: Optional[list[str]] = None,
        custom_api_key: Optional[str] = None,
        custom_model: Optional[str] = None,
    ) -> QueryResult:
        """Execute a confirmed destructive SQL operation.

        Use this method to execute INSERT, UPDATE, DELETE, or other
        destructive operations that were flagged for confirmation.

        Args:
            database: The database identifier.
            sql_query: The SQL query to execute.
            chat_history: Conversation context.
            custom_api_key: Per-request override for the LLM API key.
            custom_model: Per-request override for the LLM model
                (``vendor/model`` format, e.g. ``openai/gpt-4.1``).

        Returns:
            QueryResult with execution results.
        """
        from api.core.text2sql_sync import execute_destructive_operation_sync
        from api.core.text2sql import ConfirmRequest

        confirm_data = ConfirmRequest(
            sql_query=sql_query,
            confirmation="CONFIRM",
            chat=chat_history or [],
            custom_api_key=custom_api_key,
            custom_model=custom_model,
        )

        with self._bind_task_sink():
            return await execute_destructive_operation_sync(
                self._user_id, database, confirm_data, db=self._db,
            )

    async def close(self) -> None:
        """Close the SDK connection and release resources.

        Awaits any in-flight background memory writes so they land before
        the FalkorDB connection pool is released. Drains in a loop because
        ``save_memory_background`` registers ``sink.discard`` as a done
        callback and any awaited task can schedule further tasks via the
        same contextvar sink.
        """
        while self._pending_tasks:
            # Snapshot before awaiting — the live set mutates from done
            # callbacks (sink.discard) and would raise "set changed size
            # during iteration" if unpacked directly into gather().
            tasks = list(self._pending_tasks)
            await asyncio.gather(*tasks, return_exceptions=True)
        await self._connection.close()

    async def __aenter__(self) -> "QueryWeaver":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
