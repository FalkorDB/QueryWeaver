"""Shared logic for text2sql streaming and SDK (sync) paths.

This module contains pure functions and constants extracted from
``text2sql.py`` (canonical source) so that both the streaming API and the
SDK non-streaming path stay in sync.
"""

import asyncio
import contextvars
import logging
import os
from typing import Any, Awaitable, Callable, Optional, Type

from api.agents import ResponseFormatterAgent
from api.agents.healer_agent import HealerAgent
from api.config import Config
from api.core.db_resolver import resolve_db
from api.core.errors import GraphNotFoundError, InvalidArgumentError
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

DESTRUCTIVE_OPS = frozenset([
    'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'TRUNCATE',
])

# Emit callback signature: helpers that both the streaming and sync paths
# call invoke ``emit(event)`` when they have a progress message. Streaming
# passes a function that serializes+yields; sync passes ``None``.
EmitFn = Optional[Callable[[dict], Awaitable[None]]]

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
    if db_url_lower.startswith('snowflake://'):
        # Lazy-import: snowflake-connector-python is in the [server] extra,
        # not in the core SDK install.
        # pylint: disable=import-outside-toplevel
        from api.loaders.snowflake_loader import SnowflakeLoader
        return 'snowflake', SnowflakeLoader

    # Default to PostgresLoader for backward compatibility
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


def _strip_sql_comments_and_whitespace(sql_query: str) -> str:
    """Strip leading SQL comments (-- line and /* block */) and whitespace.

    A naive ``strip().split()[0]`` lets ``-- evil\\nDROP TABLE x`` masquerade
    as a non-destructive statement, bypassing confirmation.
    """
    text = sql_query.lstrip()
    while text:
        if text.startswith("--"):
            newline = text.find("\n")
            if newline == -1:
                return ""
            text = text[newline + 1:].lstrip()
        elif text.startswith("/*"):
            end = text.find("*/")
            if end == -1:
                return ""
            text = text[end + 2:].lstrip()
        else:
            break
    return text


def detect_destructive_operation(sql_query: str) -> tuple[str, bool]:
    """Return ``(sql_type, is_destructive)`` for a SQL statement.

    Strips leading SQL comments before classifying so attackers cannot
    bypass destructive-op confirmation by prefixing a comment.
    """
    if not sql_query:
        return "", False
    cleaned = _strip_sql_comments_and_whitespace(sql_query)
    sql_type = cleaned.split()[0].upper() if cleaned else ""
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


# ---------------------------------------------------------------------------
# Orchestration helpers shared by streaming and sync text2sql paths
# ---------------------------------------------------------------------------


async def _maybe_emit(emit: EmitFn, event: dict) -> None:
    """Call ``emit(event)`` when it's provided; no-op otherwise."""
    if emit is not None:
        await emit(event)


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


async def execute_with_healing(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    sql_query: str,
    loader_class: Type[BaseLoader],
    db_url: str,
    db_description: str,
    question: str,
    db_type: Optional[str],
    emit: EmitFn = None,
) -> tuple[str, list]:
    """Execute ``sql_query`` and, on failure, run the healer loop.

    Emits progress events for each healing attempt (streaming callers see
    them; sync callers don't pass an emitter). Raises the original driver
    exception if healing cannot recover.
    """
    try:
        results = loader_class.execute_sql_query(sql_query, db_url)
        return sql_query, results
    except Exception as exec_error:  # pylint: disable=broad-exception-caught
        await _maybe_emit(emit, {
            "type": "healing_start",
            "message": "SQL execution failed, attempting to heal query...",
            "error": str(exec_error),
        })

        healer = HealerAgent(max_healing_attempts=3)

        def _run_sql(sql: str):
            return loader_class.execute_sql_query(sql, db_url)

        healing_result = healer.heal_and_execute(
            initial_sql=sql_query,
            initial_error=str(exec_error),
            execute_sql_func=_run_sql,
            db_description=db_description,
            question=question,
            database_type=db_type,
        )

        if not healing_result.get("success"):
            await _maybe_emit(emit, {
                "type": "healing_failed",
                "message": (
                    f"Failed to heal query after "
                    f"{healing_result.get('attempts', 0)} attempt(s)"
                ),
                "final_error": healing_result.get("final_error", str(exec_error)),
                "healing_log": healing_result.get("healing_log", []),
            })
            raise

        # Surface per-attempt progress when emitting.
        for log_entry in healing_result.get("healing_log", []):
            if log_entry.get("status") == "healed":
                await _maybe_emit(emit, {
                    "type": "healing_attempt",
                    "attempt": log_entry.get("attempt"),
                    "changes": log_entry.get("changes_made", []),
                    "confidence": log_entry.get("confidence", 0),
                })

        await _maybe_emit(emit, {
            "type": "healing_success",
            "healed_sql": healing_result["sql_query"],
            "attempts": healing_result.get("attempts", 0) + 1,
        })
        return healing_result["sql_query"], healing_result["query_results"]


async def refresh_schema_if_modified(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    sql_query: str,
    loader_class: Type[BaseLoader],
    graph_id: str,
    db_url: str,
    db=None,
    emit: EmitFn = None,
) -> tuple[bool, str, str]:
    """Check whether *sql_query* is schema-modifying and refresh if so.

    Returns ``(was_modifying, operation_type, status)`` where ``status`` is
    ``"ok"``, ``"failed"``, or ``"skipped"``. Emits events when provided.
    """
    is_modifying, operation_type = check_schema_modification(sql_query, loader_class)
    if not is_modifying:
        return False, "", "skipped"

    logging.info(
        "Schema modification detected (%s). Refreshing graph schema.",
        operation_type,
    )

    try:
        success, message = await loader_class.refresh_graph_schema(
            graph_id, db_url, db=db,
        )
    except Exception as refresh_err:  # pylint: disable=broad-exception-caught
        logging.error("Error refreshing schema: %s", str(refresh_err))
        await _maybe_emit(emit, {
            "type": "schema_refresh",
            "refresh_status": "failed",
            "message": f"Schema refresh raised: {refresh_err}",
            "operation_type": operation_type,
        })
        return True, operation_type, "failed"

    if success:
        await _maybe_emit(emit, {
            "type": "schema_refresh",
            "refresh_status": "success",
            "message": (
                f"Schema change detected ({operation_type} operation). "
                "Graph schema refreshed with the latest database structure."
            ),
            "operation_type": operation_type,
        })
        return True, operation_type, "ok"

    logging.warning(
        "Schema refresh failed after %s: %s", operation_type, message,
    )
    await _maybe_emit(emit, {
        "type": "schema_refresh",
        "refresh_status": "failed",
        "message": f"Schema was modified but graph refresh failed: {message}",
        "operation_type": operation_type,
    })
    return True, operation_type, "failed"


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


_DESTRUCTIVE_VERBS = {
    'INSERT': 'Add new data to the database',
    'UPDATE': 'Modify existing data in the database',
    'DELETE': '**PERMANENTLY DELETE** data from the database',
    'DROP': '**PERMANENTLY DELETE** entire tables or database objects',
    'CREATE': 'Create new tables or database objects',
    'ALTER': 'Modify the structure of existing tables',
    'TRUNCATE': '**PERMANENTLY DELETE ALL DATA** from specified tables',
}


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
