"""Best-effort error reporting to the organization analytics graph."""

import asyncio
import logging

from fastapi import Request

from api.config import ORGANIZATIONS_GRAPH
from api.extensions import db
from api.helpers.redaction import redact_sensitive_text

LOGGER = logging.getLogger(__name__)


def _safe_message(exc: Exception) -> str:
    """Redact common credential forms before persisting an exception message."""
    return redact_sensitive_text(str(exc))


async def report_error(request: Request, exc: Exception) -> bool:
    """Record an unhandled QueryWeaver error without affecting the response."""
    try:
        graph = db.select_graph(ORGANIZATIONS_GRAPH)
        user_email = getattr(request.state, "user_email", None)
        await asyncio.wait_for(
            graph.query(
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
            ),
            timeout=2,
        )
        return True
    except Exception as analytics_error:  # pylint: disable=broad-exception-caught
        LOGGER.error(
            "Failed to report QueryWeaver error to analytics: %s",
            analytics_error,
            exc_info=True,
        )
        return False
