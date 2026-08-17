"""Best-effort error reporting to the organization analytics graph."""

import asyncio
import logging
from typing import Optional

from fastapi import Request

from api.config import ORGANIZATIONS_GRAPH
from api.helpers.redaction import redact_sensitive_text

LOGGER = logging.getLogger(__name__)
_DB_OVERRIDE = None


def _safe_message(exc: Exception) -> str:
    """Redact common credential forms before persisting an exception message."""
    return redact_sensitive_text(str(exc))


async def _write_error(request: Request, exc: Exception) -> None:
    """Write one error to the organization graph."""
    if _DB_OVERRIDE is None:
        # pylint: disable=import-outside-toplevel
        from api.core.db_resolver import resolve_db

        database = resolve_db()
    else:
        database = _DB_OVERRIDE
    graph = database.select_graph(ORGANIZATIONS_GRAPH)
    user_email = getattr(request.state, "user_email", None)
    await graph.query(
        """
        CREATE (e:Error {
            source: 'queryweaver',
            type: $type,
            message: $message,
            endpoint: $endpoint,
            method: $method,
            timestamp: timestamp()
        })
        WITH e
        OPTIONAL MATCH (u:User {email: $user_email})
        FOREACH (_ IN CASE WHEN u IS NULL THEN [] ELSE [1] END |
            CREATE (u)-[:ENCOUNTERED]->(e)
        )
        """,
        {
            "type": type(exc).__name__,
            "message": _safe_message(exc),
            "endpoint": request.url.path,
            "method": request.method,
            "user_email": user_email,
        },
    )


def report_error(
    request: Request,
    exc: Exception,
    task_sink: Optional[set] = None,
) -> None:
    """Schedule an unhandled-error write without delaying the response."""
    task = asyncio.create_task(_write_error(request, exc))
    sink = task_sink
    if sink is None:
        try:
            # pylint: disable=import-outside-toplevel
            from api.core.pipeline import background_tasks_var

            sink = background_tasks_var.get()
        except ImportError:
            sink = None
    if sink is not None:
        sink.add(task)
        task.add_done_callback(sink.discard)

    def _log_done(done: "asyncio.Task") -> None:
        if done.cancelled():
            return
        analytics_error = done.exception()
        if analytics_error is not None:
            LOGGER.error(
                "Failed to report QueryWeaver error to analytics: %s",
                analytics_error,
                exc_info=(
                    type(analytics_error),
                    analytics_error,
                    analytics_error.__traceback__,
                ),
            )

    task.add_done_callback(_log_done)
