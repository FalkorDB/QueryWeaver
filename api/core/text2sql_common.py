"""Shared logic for text2sql streaming and SDK (sync) paths.

This module contains pure functions and constants extracted from
``text2sql.py`` (canonical source) so that both the streaming API and the
SDK non-streaming path stay in sync.
"""

import os
from typing import Optional, Type

from api.config import Config
from api.core.errors import GraphNotFoundError, InvalidArgumentError
from api.loaders.postgres_loader import PostgresLoader
from api.loaders.mysql_loader import MySQLLoader
from api.loaders.base_loader import BaseLoader
from api.sql_utils import SQLIdentifierQuoter, DatabaseSpecificQuoter

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GENERAL_PREFIX = os.getenv("GENERAL_PREFIX")

DESTRUCTIVE_OPS = frozenset([
    'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'TRUNCATE',
])

# ---------------------------------------------------------------------------
# Graph helpers
# ---------------------------------------------------------------------------


def graph_name(user_id: str, graph_id: str) -> str:
    """Return the namespaced graph name.

    Applies validation identical to the original ``_graph_name`` in
    ``text2sql.py``: strip, truncate to 200 chars, reject empty, bypass
    prefix for general/demo graphs.

    Raises:
        GraphNotFoundError: If *graph_id* is empty after stripping.
    """
    graph_id = graph_id.strip()[:200]
    if not graph_id:
        raise GraphNotFoundError(
            "Invalid graph_id, must be less than 200 characters."
        )

    if GENERAL_PREFIX and graph_id.startswith(GENERAL_PREFIX):
        return graph_id

    return f"{user_id}_{graph_id}"


def is_general_graph(graph_id: str) -> bool:
    """Return ``True`` when *graph_id* belongs to a demo/general graph."""
    return bool(GENERAL_PREFIX and graph_id.startswith(GENERAL_PREFIX))


# ---------------------------------------------------------------------------
# Database type detection
# ---------------------------------------------------------------------------


def get_database_type_and_loader(
    db_url: str,
) -> tuple[Optional[str], Optional[Type[BaseLoader]]]:
    """Determine database type from *db_url* and return the loader class.

    Performs null/empty check, case-insensitive matching and defaults to
    PostgreSQL for backward compatibility (matching ``text2sql.py``).
    """
    if not db_url or db_url == "No URL available for this database.":
        return None, None

    db_url_lower = db_url.lower()

    if db_url_lower.startswith('postgresql://') or db_url_lower.startswith('postgres://'):
        return 'postgresql', PostgresLoader
    if db_url_lower.startswith('mysql://'):
        return 'mysql', MySQLLoader

    # Default to PostgresLoader for backward compatibility
    return 'postgresql', PostgresLoader


# ---------------------------------------------------------------------------
# Input sanitisation
# ---------------------------------------------------------------------------


def sanitize_query(query: str) -> str:
    """Sanitize *query* for safe usage — strips newlines and truncates to 500 chars."""
    return query.replace('\n', ' ').replace('\r', ' ')[:500]


def sanitize_log_input(value: str) -> str:
    """Sanitize *value* for safe logging — removes newlines, CRs, and tabs."""
    if not isinstance(value, str):
        value = str(value)
    return value.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')


def truncate_for_log(query: str, max_length: int = 200) -> str:
    """Truncate *query* for compact log messages (SDK path)."""
    if len(query) > max_length:
        return query[:max_length] + "..."
    return query


# ---------------------------------------------------------------------------
# SQL analysis helpers
# ---------------------------------------------------------------------------


def detect_destructive_operation(sql_query: str) -> tuple[str, bool]:
    """Return ``(sql_type, is_destructive)`` for a SQL statement."""
    sql_type = sql_query.strip().split()[0].upper() if sql_query else ""
    return sql_type, sql_type in DESTRUCTIVE_OPS


def auto_quote_sql_identifiers(
    sql_query: str,
    known_tables: set,
    db_type: Optional[str],
) -> tuple[str, bool]:
    """Auto-quote table names containing special characters.

    Returns ``(sanitized_sql, was_modified)``.
    """
    quote_char = DatabaseSpecificQuoter.get_quote_char(db_type or 'postgresql')
    return SQLIdentifierQuoter.auto_quote_identifiers(
        sql_query, known_tables, quote_char
    )


def check_schema_modification(
    sql_query: str,
    loader_class: Type[BaseLoader],
) -> tuple[bool, str]:
    """Thin wrapper around ``loader_class.is_schema_modifying_query()``.

    Returns ``(is_schema_modifying, operation_type)``.
    """
    return loader_class.is_schema_modifying_query(sql_query)


# ---------------------------------------------------------------------------
# Chat data validation & truncation
# ---------------------------------------------------------------------------


def validate_and_truncate_chat(
    chat_data,
) -> tuple[list, Optional[list], Optional[str], bool]:
    """Validate *chat_data* and truncate history to ``Config.SHORT_MEMORY_LENGTH``.

    Uses ``getattr`` for safe attribute access (works with both Pydantic
    models and plain objects).

    Returns:
        ``(queries_history, result_history, instructions, use_user_rules)``

    Raises:
        InvalidArgumentError: If chat data is invalid or empty.
    """
    queries_history = getattr(chat_data, 'chat', None)
    result_history = getattr(chat_data, 'result', None)
    instructions = getattr(chat_data, 'instructions', None)
    use_user_rules = getattr(chat_data, 'use_user_rules', True)

    if not queries_history or not isinstance(queries_history, list):
        raise InvalidArgumentError("Invalid or missing chat history")

    if len(queries_history) == 0:
        raise InvalidArgumentError("Empty chat history")

    # Truncate to configured window
    if len(queries_history) > Config.SHORT_MEMORY_LENGTH:
        queries_history = queries_history[-Config.SHORT_MEMORY_LENGTH:]
        if result_history and len(result_history) > 0:
            max_results = Config.SHORT_MEMORY_LENGTH - 1
            if max_results > 0:
                result_history = result_history[-max_results:]
            else:
                result_history = []

    return queries_history, result_history, instructions, use_user_rules
