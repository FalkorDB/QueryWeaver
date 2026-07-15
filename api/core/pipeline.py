"""Shared logic for text2sql streaming and SDK (sync) paths.

This module contains pure functions and constants extracted from
``text2sql.py`` (canonical source) so that both the streaming API and the
SDK non-streaming path stay in sync.
"""

import asyncio
import contextvars
import logging
import os
import re
from typing import Any, Optional, Type

import sqlglot

from api.agents import ResponseFormatterAgent
from api.config import Config
from api.core.db_resolver import resolve_db
from api.core.errors import InvalidArgumentError
from api.loaders.postgres_loader import PostgresLoader
from api.loaders.mysql_loader import MySQLLoader
from api.loaders.base_loader import BaseLoader
from api.sql_utils import SQLIdentifierQuoter, DatabaseSpecificQuoter

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Delimiter used by the streaming route to frame JSON messages on the wire.
# Kept here so any caller that composes streaming payloads pulls the single
# source of truth rather than redefining it.
MESSAGE_DELIMITER = "|||FALKORDB_MESSAGE_BOUNDARY|||"

GENERAL_PREFIX = os.getenv("GENERAL_PREFIX")

# Verb → user-facing description for destructive operations. Used by the
# confirmation-message builder and exposed as ``DESTRUCTIVE_OPS`` (the set of
# named destructive verbs). Detection itself is AST-based (see
# ``detect_destructive_operation``), so this map only needs the verbs we want a
# friendly description for; any other mutation still triggers confirmation with
# a generic description.
_DESTRUCTIVE_VERBS = {
    'INSERT': 'Add new data to the database',
    'REPLACE': 'Replace data in the database (deletes conflicting rows, then inserts)',
    'UPDATE': 'Modify existing data in the database',
    'DELETE': '**PERMANENTLY DELETE** data from the database',
    'DROP': '**PERMANENTLY DELETE** entire tables or database objects',
    'CREATE': 'Create new tables or database objects',
    'ALTER': 'Modify the structure of existing tables',
    'TRUNCATE': '**PERMANENTLY DELETE ALL DATA** from specified tables',
    'MERGE': 'Insert, update, or delete rows in the database',
    'GRANT': 'Change database access privileges',
    'REVOKE': 'Change database access privileges',
    'COPY': 'Bulk-load data into the database',
}

DESTRUCTIVE_OPS = frozenset(_DESTRUCTIVE_VERBS)

# Contextvar-scoped task sink. SDK code sets this for the duration of a
# query/execute call so ``save_memory_background`` (fire-and-forget) can
# be awaited at ``QueryWeaver.close()`` time. Unset in server contexts,
# where the event loop outlives the query and tasks drain naturally.
background_tasks_var: contextvars.ContextVar[Optional[set]] = (
    contextvars.ContextVar("queryweaver_background_tasks", default=None)
)

# ---------------------------------------------------------------------------
# Graph helpers
# ---------------------------------------------------------------------------


def graph_name(user_id: str, graph_id: str) -> str:
    """Return the namespaced graph name.

    Applies validation identical to the original ``_graph_name`` in
    ``text2sql.py``: strip, truncate to 200 chars, reject empty, bypass
    prefix for general/demo graphs.

    Raises:
        InvalidArgumentError: If *graph_id* is empty after stripping.
    """
    graph_id = graph_id.strip()[:200]
    if not graph_id:
        # Bad input is a 400, not a 404 — several callers map
        # InvalidArgumentError → 400 in the HTTP layer.
        raise InvalidArgumentError(
            "Invalid graph_id, must be a non-empty string up to 200 characters."
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
    *,
    sdk_only: bool = False,
) -> tuple[Optional[str], Optional[Type[BaseLoader]]]:
    """Determine database type from *db_url* and return the loader class.

    Performs null/empty check, case-insensitive matching and defaults to
    PostgreSQL for backward compatibility on the server path.

    When ``sdk_only`` is True, raises ``InvalidArgumentError`` for vendors
    that need the ``[server]`` extra (snowflake) or for unknown URL schemes,
    so SDK callers get a clean error instead of a deferred ``ImportError``.
    """
    if not db_url or db_url == "No URL available for this database.":
        return None, None

    db_url_lower = db_url.lower()

    if db_url_lower.startswith('postgresql://') or db_url_lower.startswith('postgres://'):
        return 'postgresql', PostgresLoader
    if db_url_lower.startswith('mysql://'):
        return 'mysql', MySQLLoader
    if db_url_lower.startswith('snowflake://'):
        if sdk_only:
            raise InvalidArgumentError(
                "Snowflake requires the [server] extra: "
                "pip install queryweaver[server]"
            )
        # Lazy-import: snowflake-connector-python is in the [server] extra,
        # not in the core SDK install.
        # pylint: disable=import-outside-toplevel
        from api.loaders.snowflake_loader import SnowflakeLoader
        return 'snowflake', SnowflakeLoader

    if sdk_only:
        raise InvalidArgumentError(
            "Invalid database URL format. Must be PostgreSQL or MySQL."
        )
    # Server path keeps the historical default-to-PostgreSQL fallback.
    return 'postgresql', PostgresLoader


def validate_custom_model(custom_model: Optional[str]) -> None:
    """Validate the ``vendor/model`` format and supported vendor list.

    Raises:
        InvalidArgumentError: If the format is wrong or the vendor is unsupported.
    """
    if not custom_model:
        return
    # Lazy-import: SUPPORTED_VENDORS lives in api.config which pulls server-only
    # symbols. Keeping the import here means the SDK doesn't need it at import time.
    # pylint: disable=import-outside-toplevel
    from api.config import SUPPORTED_VENDORS
    parts = custom_model.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise InvalidArgumentError(
            "Invalid model format. Expected 'vendor/model' (e.g. 'openai/gpt-4.1')"
        )
    if parts[0] not in SUPPORTED_VENDORS:
        raise InvalidArgumentError(
            f"Unsupported vendor '{parts[0]}'. Supported: {', '.join(SUPPORTED_VENDORS)}"
        )


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


# Internal db_type → sqlglot dialect. Unknown/None types parse dialect-agnostic.
_DIALECT_BY_DB_TYPE = {
    "postgresql": "postgres",
    "postgres": "postgres",
    "mysql": "mysql",
    "snowflake": "snowflake",
}

# sqlglot expression class names that represent a write, DDL, privilege change,
# bulk load, or ``SELECT ... INTO``. Any of these anywhere in the parse tree
# (including inside CTEs and subqueries) makes the whole statement destructive.
_DESTRUCTIVE_EXP_NAMES = frozenset({
    "Insert", "Update", "Delete", "Merge", "Drop", "Create", "Alter",
    "AlterTable", "TruncateTable", "Truncate", "Copy", "Grant", "Revoke",
    "Into",
})

# sqlglot expression class name → short verb for the confirmation message.
_EXP_NAME_TO_VERB = {
    "Insert": "INSERT", "Update": "UPDATE", "Delete": "DELETE", "Merge": "MERGE",
    "Drop": "DROP", "Create": "CREATE", "Alter": "ALTER", "AlterTable": "ALTER",
    "TruncateTable": "TRUNCATE", "Truncate": "TRUNCATE", "Copy": "COPY",
    "Grant": "GRANT", "Revoke": "REVOKE", "Into": "SELECT ... INTO",
}

# Reported as ``sql_type`` when a statement cannot be parsed and is therefore
# treated as destructive out of caution.
_UNKNOWN_DESTRUCTIVE_TYPE = "UNKNOWN"

# sqlglot logs a WARNING whenever it falls back to a generic Command for syntax
# it does not model (e.g. REPLACE INTO, CALL). That fallback is expected and
# handled by detect_destructive_operation, so quiet those warnings.
logging.getLogger("sqlglot").setLevel(logging.ERROR)


# Opening marker of a MySQL/MariaDB "executable comment" (``/*! ...``,
# ``/*!50110 ...``, ``/*M! ...``): the server RUNS the payload, so we must not
# let it be discarded as an ordinary comment before parsing.
_EXECUTABLE_COMMENT_OPEN = re.compile(r"/\*(?:!|M!)\d*")


def _unwrap_executable_comments(sql: str) -> str:
    """Inline the payload of MySQL/MariaDB executable comments.

    sqlglot treats ``/*! ... */`` as an ordinary comment and drops its
    contents, but MySQL/MariaDB execute that payload. Rewriting the markers to
    whitespace exposes the payload (e.g. ``/*! DROP TABLE users */`` →
    `` DROP TABLE users ``) so the destructive statement is actually parsed.
    """
    result = []
    pos = 0
    while True:
        match = _EXECUTABLE_COMMENT_OPEN.search(sql, pos)
        if match is None:
            result.append(sql[pos:])
            break
        close = sql.find("*/", match.end())
        if close == -1:
            result.append(sql[pos:])
            break
        result.append(sql[pos:match.start()])
        result.append(" ")
        result.append(sql[match.end():close])
        result.append(" ")
        pos = close + 2
    return "".join(result)


def _sqlglot_dialect(db_type: Optional[str]) -> Optional[str]:
    """Map an internal ``db_type`` to a sqlglot dialect name (or None)."""
    if not db_type:
        return None
    return _DIALECT_BY_DB_TYPE.get(db_type.strip().lower())


def detect_destructive_operation(
    sql_query: str, db_type: Optional[str] = None
) -> tuple[str, bool]:
    """Return ``(sql_type, is_destructive)`` for a SQL statement.

    Parses *sql_query* with sqlglot (dialect-aware when *db_type* is given) and
    inspects the full AST, so classification is not fooled by anything that
    hides a write behind the first token:

    - data-modifying CTEs — ``WITH t AS (...) DELETE FROM users ...`` and
      ``WITH t AS (DELETE FROM users ...) SELECT * FROM t``
    - stacked statements — ``SELECT 1; DROP TABLE users``
    - MySQL/MariaDB executable comments — ``/*! DROP TABLE users */``
    - dialect-specific string/comment escapes (backslash escapes, dollar
      quoting, ``#`` comments) that a hand-rolled scanner mis-tokenises

    Any write (INSERT/UPDATE/DELETE/MERGE/REPLACE), DDL (CREATE/DROP/ALTER/
    TRUNCATE/RENAME), privilege change (GRANT/REVOKE), bulk load (COPY/LOAD),
    ``SELECT ... INTO``, or generically-parsed command marks the statement
    destructive so it cannot bypass the confirmation prompt or the demo-graph
    read-only guard. The reported ``sql_type`` names the operation for the
    confirmation message.

    The check is conservative: a statement sqlglot cannot parse is treated as
    destructive rather than executed unconfirmed.
    """
    if not sql_query or not sql_query.strip():
        return "", False
    prepared = _unwrap_executable_comments(sql_query)
    try:
        statements = [
            stmt
            for stmt in sqlglot.parse(prepared, read=_sqlglot_dialect(db_type))
            if stmt is not None
        ]
    except Exception:  # pylint: disable=broad-exception-caught
        # Unparseable → we cannot prove it is read-only → require confirmation.
        return _UNKNOWN_DESTRUCTIVE_TYPE, True
    if not statements:
        return "", False
    for statement in statements:
        for node in statement.walk():
            node = node[0] if isinstance(node, tuple) else node
            name = type(node).__name__
            if name in _DESTRUCTIVE_EXP_NAMES:
                return _EXP_NAME_TO_VERB.get(name, name.upper()), True
            # A statement sqlglot cannot model structurally falls back to a
            # generic Command (REPLACE INTO, CALL, RENAME, DO, LOAD, VACUUM,
            # EXPLAIN ANALYZE ...). We cannot prove these are read-only, so treat
            # them as destructive, named by their leading keyword.
            if name == "Command":
                keyword = str(node.this).strip().upper() if node.this else ""
                return keyword or "COMMAND", True
    return type(statements[0]).__name__.upper(), False


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


# ---------------------------------------------------------------------------
# Pipeline helpers used by run_query / run_confirmed
# ---------------------------------------------------------------------------


async def quote_identifiers_from_graph(
    sql_query: str,
    graph_id: str,
    db_type: Optional[str],
    db=None,
    known_tables: Optional[set] = None,
) -> tuple[str, bool]:
    """Auto-quote SQL identifiers using the Table list stored in FalkorDB.

    If *known_tables* is supplied, uses it directly; otherwise queries the
    graph for the current Table names. Returns ``(sql, was_modified)``.
    """
    if known_tables is None:
        graph = resolve_db(db).select_graph(graph_id)
        try:
            tables_res = (
                await graph.query("MATCH (t:Table) RETURN t.name")
            ).result_set
            known_tables = (
                {row[0] for row in tables_res} if tables_res else set()
            )
        except Exception:  # pylint: disable=broad-exception-caught
            known_tables = set()

    return auto_quote_sql_identifiers(sql_query, known_tables, db_type)


def format_ai_response(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    queries_history: list,
    result_history: Optional[list],
    sql_query: str,
    query_results: list,
    db_description: str,
    custom_api_key: Optional[str] = None,
    custom_model: Optional[str] = None,
) -> str:
    """Build a human-readable AI response for *query_results*."""
    agent = ResponseFormatterAgent(
        queries_history, result_history, custom_api_key, custom_model,
    )
    return agent.format_response(
        user_query=queries_history[-1] if queries_history else "",
        sql_query=sql_query,
        query_results=query_results,
        db_description=db_description,
    )


def build_destructive_confirmation_message(sql_type: str, sql_query: str) -> str:
    """Return the rich confirmation prompt shown for destructive operations.

    Used by both the streaming confirmation event and the sync ``QueryResult``
    so users see the same warning wording regardless of transport.
    """
    description = _DESTRUCTIVE_VERBS.get(sql_type, "Modify the database")
    return (
        "⚠️ DESTRUCTIVE OPERATION DETECTED ⚠️\n\n"
        f"The generated SQL query will perform a **{sql_type}** operation:\n\n"
        f"SQL:\n{sql_query}\n\n"
        f"What this will do:\n• {description}\n\n"
        "⚠️ WARNING: This operation will make changes to your database and "
        "may be irreversible."
    )


def save_memory_background(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    memory_tool: Any,
    question: str,
    sql_query: str,
    success: bool,
    error: str,
    full_response: Optional[dict] = None,
    chat_histories: Optional[list] = None,
    task_sink: Optional[set] = None,
) -> None:
    """Schedule fire-and-forget memory persistence for the given query.

    Returns immediately; tasks run in the background with their own
    error-logging callbacks so a failure to save never blocks the response.

    When ``task_sink`` is given, each scheduled task is added to it and
    auto-removed on completion. The SDK uses this so ``QueryWeaver.close()``
    can await in-flight memory writes before disconnecting the pool.
    """

    sink = task_sink if task_sink is not None else background_tasks_var.get()

    def _track(task):
        if sink is None:
            return
        sink.add(task)
        task.add_done_callback(sink.discard)

    def _log_done(label: str):
        # Done-callbacks must not call ``t.exception()`` on a cancelled task —
        # it raises CancelledError and surfaces as a noisy "exception in callback"
        # log line, which is misleading at shutdown.
        def _cb(task):
            if task.cancelled():
                return
            exc = task.exception()
            if exc is not None:
                logging.error("%s failed: %s", label, exc)  # nosemgrep
            else:
                logging.info("%s completed successfully", label)
        return _cb

    save_query_task = asyncio.create_task(
        memory_tool.save_query_memory(
            query=question,
            sql_query=sql_query,
            success=success,
            error=error,
        )
    )
    _track(save_query_task)
    save_query_task.add_done_callback(_log_done("Query memory save"))

    if full_response is not None and chat_histories is not None:
        save_task = asyncio.create_task(
            memory_tool.add_new_memory(full_response, chat_histories)
        )
        _track(save_task)
        save_task.add_done_callback(_log_done("Memory save"))

    clean_task = asyncio.create_task(memory_tool.clean_memory())
    _track(clean_task)
    clean_task.add_done_callback(_log_done("Memory cleanup"))
