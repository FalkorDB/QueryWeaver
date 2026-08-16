"""Best-effort error reporting to the organization analytics graph."""

import logging
import os

from fastapi import Request
from falkordb.asyncio import FalkorDB
from redis.asyncio import BlockingConnectionPool

LOGGER = logging.getLogger(__name__)
ANALYTICS_GRAPH = os.getenv("ORGANIZATIONS_GRAPH", "Organizations")


async def report_error(request: Request, exc: Exception) -> bool:
    """Record an unhandled QueryWeaver error without affecting the response."""
    url = os.getenv("FALKORDB_URL")
    if not url:
        LOGGER.error("Cannot report QueryWeaver error: FALKORDB_URL is not configured")
        return False

    pool = None
    try:
        pool = BlockingConnectionPool.from_url(url, decode_responses=True)
        client = FalkorDB(connection_pool=pool)
        graph = client.select_graph(ANALYTICS_GRAPH)
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
                "message": str(exc)[:4000],
                "endpoint": request.url.path,
                "method": request.method,
                "user_email": user_email,
            },
        )
        return True
    except Exception as analytics_error:  # pylint: disable=broad-exception-caught
        LOGGER.error("Failed to report QueryWeaver error to analytics: %s", analytics_error)
        return False
    finally:
        if pool is not None:
            try:
                await pool.aclose()
            except Exception:  # pylint: disable=broad-exception-caught
                LOGGER.debug("Failed to close analytics Redis pool", exc_info=True)
