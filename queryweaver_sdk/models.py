"""Data models for QueryWeaver SDK results."""

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class QueryResult:
    """Result from a text-to-SQL query execution."""

    sql_query: str
    """The generated SQL query."""

    results: list[dict[str, Any]]
    """Query execution results as list of row dictionaries."""

    ai_response: str
    """Human-readable AI-generated response summarizing the results."""

    confidence: float
    """Confidence score (0-1) for the generated SQL query."""

    is_destructive: bool = False
    """Whether the query is a destructive operation (INSERT/UPDATE/DELETE/DROP)."""

    requires_confirmation: bool = False
    """Whether the operation requires user confirmation before execution."""

    execution_time: float = 0.0
    """Total execution time in seconds."""

    is_valid: bool = True
    """Whether the query was successfully translated to valid SQL."""

    missing_information: str = ""
    """Any information that was missing to fully answer the query."""

    ambiguities: str = ""
    """Any ambiguities detected in the user's question."""

    explanation: str = ""
    """Explanation of the SQL query logic."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class SchemaResult:
    """Database schema representation."""

    nodes: list[dict[str, Any]]
    """Tables in the schema, each with id, name, and columns."""

    links: list[dict[str, str]]
    """Foreign key relationships between tables."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class DatabaseConnection:
    """Result from connecting to a database."""

    database_id: str
    """The identifier for the connected database."""

    success: bool
    """Whether the connection and schema loading succeeded."""

    tables_loaded: int = 0
    """Number of tables loaded into the schema graph."""

    message: str = ""
    """Status message or error description."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class RefreshResult:
    """Result from refreshing a database schema."""

    success: bool
    """Whether the schema refresh succeeded."""

    message: str = ""
    """Status message or error description."""

    tables_updated: int = 0
    """Number of tables updated during refresh."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class ChatMessage:
    """A message in the conversation history."""

    question: str
    """The user's question."""

    sql_query: str = ""
    """The generated SQL query (if any)."""

    result: str = ""
    """The result or response."""


@dataclass
class QueryRequest:
    """Request parameters for a query operation."""

    question: str
    """The natural language question to convert to SQL."""

    chat_history: list[str] = field(default_factory=list)
    """Previous questions in the conversation for context."""

    result_history: list[str] = field(default_factory=list)
    """Previous results for context."""

    instructions: str | None = None
    """Additional instructions for query generation."""

    use_user_rules: bool = True
    """Whether to apply user-defined rules from the database."""

    use_memory: bool = False
    """Whether to use long-term memory for context."""
