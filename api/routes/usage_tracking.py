"""Always-on, provider-agnostic per-query usage tracking.

This is deliberately independent of the optional LLM conversational-memory
feature (``api/memory/graphiti_tool.py``). Memory writes are opt-in
(``use_memory``), gated to OpenAI/Azure providers, and lazily created — so
they cannot be used to measure adoption. This module records *every* query,
regardless of provider or the ``use_memory`` flag, onto the central
``Organizations`` graph (which already holds ``User``/``Identity``/``Token``).

For each query we maintain, fire-and-forget:

* Denormalized counters + activity timestamps on the ``User`` node
  (``query_count``/``success_count``/``error_count``/``last_active``/
  ``first_query_at``) for cheap reads.
* A per-query ``(:UsageEvent)`` node linked ``(User)-[:PERFORMED]->`` carrying
  ``graph_id``/``is_demo``/``success``/``timestamp`` for time-series, per-DB
  and success-rate analytics.

Writes never block or fail a request: they run as background tasks whose
exceptions are logged and swallowed, mirroring
``api.core.pipeline.save_memory_background``.
"""

import asyncio
import base64
import binascii
import hashlib
import logging
import uuid
from typing import Optional

from api.config import ORGANIZATIONS_GRAPH
from api.core.db_resolver import resolve_db
from api.core.pipeline import background_tasks_var, is_general_graph

# Single round-trip: bump the User counters/timestamps and append a UsageEvent.
# Uses MATCH (not MERGE) on User so an unknown email is a silent no-op rather
# than creating a phantom user from the query path. ``timestamp()`` is FalkorDB
# epoch-millis, matching every other timestamp in the Organizations graph.
_RECORD_USAGE_CYPHER = """
MATCH (u:User {email: $email})
SET u.query_count    = coalesce(u.query_count, 0) + 1,
    u.success_count  = coalesce(u.success_count, 0) + (CASE WHEN $success THEN 1 ELSE 0 END),
    u.error_count    = coalesce(u.error_count, 0) + (CASE WHEN $success THEN 0 ELSE 1 END),
    u.last_active    = timestamp(),
    u.first_query_at = coalesce(u.first_query_at, timestamp())
CREATE (u)-[:PERFORMED]->(e:UsageEvent {
    query_id: $query_id,
    graph_id: $graph_id,
    is_demo: $is_demo,
    success: $success,
    question: $question,
    error: $error,
    timestamp: timestamp()
})
FOREACH (_ IN CASE WHEN $success THEN [] ELSE [1] END |
    CREATE (error:Error {
        source: 'queryweaver',
        type: 'QueryError',
        message: CASE WHEN $error = '' THEN 'Query could not be completed' ELSE $error END,
        endpoint: $endpoint,
        method: 'POST',
        timestamp: timestamp()
    })
    CREATE (u)-[:ENCOUNTERED]->(error)
    CREATE (e)-[:FAILED_WITH]->(error)
)
"""


def _decode_email(user_id: str) -> Optional[str]:
    """Recover the user's email from the base64 ``user_id``.

    Inverse of ``base64.b64encode(email.encode())`` in
    ``api/auth/user_management.py``. Returns ``None`` on malformed input so the
    caller can skip tracking instead of raising.
    """
    if not user_id:
        return None
    try:
        email = base64.b64decode(user_id, validate=True).decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        logging.warning("Usage tracking: could not decode user_id to email")
        return None
    # b64decode is lenient about padding/length; require an email-shaped result
    # so a malformed id can't trigger a phantom DB write (matches the docstring).
    if "@" not in email:
        logging.warning("Usage tracking: decoded user_id is not a valid email")
        return None
    return email


async def _write_usage(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    email: str,
    query_id: str,
    graph_id: str,
    is_demo: bool,
    success: bool,
    question: str,
    error: str,
    endpoint: str,
    db,
) -> None:
    """Perform the single Cypher write against the Organizations graph."""
    organizations_graph = resolve_db(db).select_graph(ORGANIZATIONS_GRAPH)
    await organizations_graph.query(
        _RECORD_USAGE_CYPHER,
        {
            "email": email,
            "query_id": query_id,
            "graph_id": graph_id,
            "is_demo": is_demo,
            "success": success,
            "question": question,
            "error": error,
            "endpoint": endpoint,
        },
    )
    # Structured-ish log line so usage is visible to log aggregators even
    # before any read API exists. graph_id is the namespaced name
    # ({base64(email)}_{db}) and base64 email is reversible, so log a short
    # stable hash instead of the raw value — this keeps user identity out of
    # logs and also neutralizes the CodeQL log-injection vector.
    graph_ref = hashlib.sha256(graph_id.encode()).hexdigest()[:12]
    logging.info(
        "usage_event graph=%s is_demo=%s success=%s",
        graph_ref, is_demo, success,
    )


def record_query_usage_background(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    user_id: str,
    namespaced: str,
    success: bool,
    question: str,
    error: str = "",
    query_id: Optional[str] = None,
    endpoint: str = "",
    *,
    db=None,
    task_sink: Optional[set] = None,
) -> None:
    """Schedule fire-and-forget usage tracking for one query.

    Returns immediately. The write runs as a background task whose failure is
    logged but never propagated, so tracking can never break or delay a query
    response. Called unconditionally at pipeline completion — independent of
    ``use_memory`` and the LLM provider.

    Args:
        user_id: Base64-encoded email (the namespacing id used by the routes).
        namespaced: The fully-namespaced graph name the query ran against;
            already demo-aware, so it doubles as the recorded ``graph_id``.
        success: Whether SQL execution succeeded (no execution error).
        question: The natural-language question associated with the attempt.
        error: The pipeline or execution error for failed attempts.
        query_id: Request-scoped identifier attached to the UsageEvent for correlation.
        endpoint: Route path that handled the query.
        db: Optional FalkorDB handle; resolves to the server singleton when None.
        task_sink: Optional set the scheduled task is added to (and auto-removed
            from on completion) so callers can await any in-flight tracking
            writes before shutdown.
    """
    email = _decode_email(user_id)
    if email is None:
        return

    is_demo = is_general_graph(namespaced)
    sink = task_sink if task_sink is not None else background_tasks_var.get()

    task = asyncio.create_task(
        _write_usage(
            email,
            query_id or str(uuid.uuid4()),
            namespaced,
            is_demo,
            success,
            question[:4000],
            error[:4000],
            endpoint,
            db,
        )
    )

    if sink is not None:
        sink.add(task)
        task.add_done_callback(sink.discard)

    def _log_done(t: "asyncio.Task") -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logging.error("Usage tracking save failed: %s", exc)  # nosemgrep

    task.add_done_callback(_log_done)
