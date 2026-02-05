"""Data models for QueryWeaver SDK results."""

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class QueryMetadata:
    """Metadata about query execution."""

    confidence: float = 0.0
    """Confidence score (0-1) for the generated SQL query."""

    execution_time: float = 0.0
    """Total execution time in seconds."""

    is_valid: bool = True
    """Whether the query was successfully translated to valid SQL."""

    is_destructive: bool = False
    """Whether the query is a destructive operation (INSERT/UPDATE/DELETE/DROP)."""

    requires_confirmation: bool = False
    """Whether the operation requires user confirmation before execution."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class QueryAnalysis:
    """Analysis information from query processing."""

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
class QueryResult:
    """Result from a text-to-SQL query execution."""

    sql_query: str
    """The generated SQL query."""

    results: list[dict[str, Any]]
    """Query execution results as list of row dictionaries."""

    ai_response: str
    """Human-readable AI-generated response summarizing the results."""

    metadata: QueryMetadata = field(default_factory=QueryMetadata)
    """Query execution metadata (confidence, timing, flags)."""

    analysis: QueryAnalysis = field(default_factory=QueryAnalysis)
    """Query analysis information (missing info, ambiguities, explanation)."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with flattened structure for compatibility."""
        result = {
            "sql_query": self.sql_query,
            "results": self.results,
            "ai_response": self.ai_response,
        }
        result.update(self.metadata.to_dict())
        result.update(self.analysis.to_dict())
        return result

    # Compatibility properties for existing code
    @property
    def confidence(self) -> float:
        """Confidence score (0-1) for the generated SQL query."""
        return self.metadata.confidence

    @property
    def execution_time(self) -> float:
        """Total execution time in seconds."""
        return self.metadata.execution_time

    @property
    def is_valid(self) -> bool:
        """Whether the query was successfully translated to valid SQL."""
        return self.metadata.is_valid

    @property
    def is_destructive(self) -> bool:
        """Whether the query is a destructive operation."""
        return self.metadata.is_destructive

    @property
    def requires_confirmation(self) -> bool:
        """Whether the operation requires user confirmation."""
        return self.metadata.requires_confirmation

    @property
    def missing_information(self) -> str:
        """Any information that was missing to fully answer the query."""
        return self.analysis.missing_information

    @property
    def ambiguities(self) -> str:
        """Any ambiguities detected in the user's question."""
        return self.analysis.ambiguities

    @property
    def explanation(self) -> str:
        """Explanation of the SQL query logic."""
        return self.analysis.explanation


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
