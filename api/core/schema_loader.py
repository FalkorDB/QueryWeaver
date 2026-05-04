"""Database connection routes for the text2sql API."""

import logging
import json
import time
from typing import AsyncGenerator, Optional
from urllib.parse import urlparse

from pydantic import BaseModel
from redis import RedisError

from api.core.db_resolver import resolve_db
from api.core.errors import InvalidArgumentError
from api.core.pipeline import MESSAGE_DELIMITER, get_database_type_and_loader
from api.loaders.base_loader import BaseLoader
from api.core.result_models import DatabaseConnection


class DatabaseConnectionRequest(BaseModel):
    """Database connection request model.

    Args:
        BaseModel (_type_): _description_
    """

    url: str

def _step_start(steps_counter: int) -> dict[str, str]:
    """Yield the starting step message."""
    return {
        "type": "reasoning_step",
        "message": f"Step {steps_counter}: Starting database connection",
    }

_KNOWN_DB_SCHEMES = ("postgresql://", "postgres://", "mysql://", "snowflake://")


def _step_detect_db_type(steps_counter: int, url: str) -> tuple[type[BaseLoader], dict[str, str]]:
    """Yield the database type detection step message.

    Strictly validates the URL scheme — unlike ``get_database_type_and_loader``'s
    server-path default-to-PostgreSQL fallback, schema loading must reject
    ``sqlite://``/``invalid://``/etc. with a clean ``InvalidArgumentError``
    rather than misclassifying them.
    """
    if not url or not any(url.lower().startswith(s) for s in _KNOWN_DB_SCHEMES):
        raise InvalidArgumentError("Invalid database URL format")

    db_type, loader = get_database_type_and_loader(url)
    if loader is None or db_type is None:
        raise InvalidArgumentError("Invalid database URL format")

    return loader, {
        "type": "reasoning_step",
        "message": f"Step {steps_counter}: Detected database type: {db_type}. "
        "Attempting to load schema...",
    }


async def _step_attempt_load(
    steps_counter: int, loader: type[BaseLoader], user_id: str, url: str, db=None,
) -> AsyncGenerator[dict[str, str | bool], None]:
    """Yield the attempt to load schema step message."""
    success, result = [False, ""]
    try:
        load_start = time.perf_counter()
        async for progress in loader.load(user_id, url, db=db):
            success, result = progress
            if success:
                steps_counter += 1
                yield {
                    "type": "reasoning_step",
                    "message": f"Step {steps_counter}: {result}",
                }
            else:
                break

        load_elapsed = time.perf_counter() - load_start
        logging.info("Database load attempt finished in %.2f seconds", load_elapsed)

        if success:
            yield {
                "type": "final_result",
                "success": True,
                "message": "Database connected and schema loaded successfully",
            }
        else:
            # Don't stream the full internal result; give higher-level error
            logging.error("Database loader failed: %s", str(result))  # nosemgrep
            yield {"type": "error", "message": "Failed to load database schema"}
    except Exception as e:  # pylint: disable=broad-exception-caught
        logging.exception("Error while loading database schema: %s", str(e))
        yield {"type": "error", "message": "Error connecting to database"}


def _step_result(result) -> str:
    """Yield the final result message."""
    return json.dumps(result) + MESSAGE_DELIMITER


async def load_database(url: str, user_id: str, db=None):
    """
    Accepts a JSON payload with a database URL and attempts to connect.
    Supports both PostgreSQL and MySQL databases.
    Streams progress steps as a sequence of JSON messages separated by MESSAGE_DELIMITER.
    """

    # Validate URL format
    if len(url.strip()) == 0:
        raise InvalidArgumentError("Invalid URL format")

    async def generate():
        overall_start = time.perf_counter()
        steps_counter = 0
        try:
            # Step 1: Start
            steps_counter += 1
            result = _step_start(steps_counter)
            yield _step_result(result)

            # Step 2: Determine type
            steps_counter += 1
            loader, result = _step_detect_db_type(steps_counter, url)
            yield _step_result(result)

            # Step 3: Attempt to load schema using the loader
            async for progress in _step_attempt_load(
                steps_counter, loader, user_id, url, db=db,
            ):
                yield _step_result(progress)

        except InvalidArgumentError as ia:
            logging.warning("Invalid argument in load_database: %s", str(ia))
            yield _step_result({"type": "error", "message": "Invalid database connection request"})
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.exception("Unexpected error in connect_database stream: %s", str(e))
            yield _step_result({"type": "error", "message": "Internal server error"})
        finally:
            overall_elapsed = time.perf_counter() - overall_start
            logging.info(
                "connect_database processing completed - Total time: %.2f seconds",
                overall_elapsed,
            )

    return generate()


async def list_databases(user_id: str, general_prefix: Optional[str] = None, db=None) -> list[str]:
    """
    This route is used to list all the graphs (databases names) that are available in the database.
    """
    user_graphs = await resolve_db(db).list_graphs()

    # Only include graphs that start with user_id + '_', and strip the prefix
    filtered_graphs = [
        graph[len(f"{user_id}_") :]
        for graph in user_graphs
        if graph.startswith(f"{user_id}_")
    ]

    if general_prefix:
        demo_graphs = [
            graph for graph in user_graphs if graph.startswith(general_prefix)
        ]
        filtered_graphs = filtered_graphs + demo_graphs

    return filtered_graphs


# =============================================================================
# SDK Non-Streaming Functions
# =============================================================================

async def load_database_sync(url: str, user_id: str, db=None):
    """
    Load a database schema and return structured result (non-streaming).

    SDK-friendly version that returns DatabaseConnection instead of streaming.

    Args:
        url: Database connection URL (PostgreSQL or MySQL).
        user_id: User identifier for namespacing.
        db: Optional FalkorDB handle; falls back to the server singleton.

    Returns:
        DatabaseConnection with connection status.
    """
    # Validate URL format
    if not url or len(url.strip()) == 0:
        raise InvalidArgumentError("Invalid URL format")

    # Determine database type and loader. ``sdk_only=True`` rejects snowflake
    # and unknown schemes with a clean InvalidArgumentError instead of letting
    # an ImportError surface when the snowflake extra isn't installed.
    _, loader = get_database_type_and_loader(url, sdk_only=True)
    if loader is None:
        raise InvalidArgumentError("Invalid database URL format. Must be PostgreSQL or MySQL.")

    success = False

    try:
        async for progress_success, _progress_message in loader.load(user_id, url, db=db):
            success = progress_success

        if success:
            # SDK callers pass the un-prefixed database_id back into query/delete/etc.,
            # where graph_name(user_id, db_name) re-applies the user_id prefix.
            # urlparse.path may carry trailing slashes or schema/path separators
            # (e.g. ``/mydb/``), and the query string is already stripped from .path
            # by urlparse — but a malformed URL may yield an empty .path, so we fall
            # back to splitting the raw URL.
            db_name = urlparse(url).path.strip("/").split("/")[0]
            if not db_name:
                db_name = url.rsplit("/", 1)[-1].split("?")[0].split("#")[0]

            return DatabaseConnection(
                database_id=db_name,
                success=True,
                message="Database connected and schema loaded successfully",
            )

        return DatabaseConnection(
            database_id="",
            success=False,
            message="Failed to load database schema",
        )

    except (RedisError, ConnectionError, OSError) as e:
        logging.exception("Error loading database: %s", str(e))
        return DatabaseConnection(
            database_id="",
            success=False,
            message="Error connecting to database",
        )
