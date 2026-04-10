"""Database connection routes for the text2sql API."""

import logging
import json
import time
from typing import AsyncGenerator, Optional

from pydantic import BaseModel

from api.extensions import db

from api.core.errors import InvalidArgumentError
from api.loaders.base_loader import BaseLoader
from api.loaders.postgres_loader import PostgresLoader
from api.loaders.mysql_loader import MySQLLoader
from api.loaders.snowflake_loader import SnowflakeLoader

# Use the same delimiter as in the JavaScript frontend for streaming chunks
MESSAGE_DELIMITER = "|||FALKORDB_MESSAGE_BOUNDARY|||"


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

def _step_detect_db_type(steps_counter: int, url: str) -> tuple[type[BaseLoader], dict[str, str]]:
    """Yield the database type detection step message."""
    db_type = None
    loader: type[BaseLoader] = BaseLoader  # type: ignore
    if url.startswith("postgres://") or url.startswith("postgresql://"):
        db_type = "postgresql"
        loader = PostgresLoader
    elif url.startswith("mysql://"):
        db_type = "mysql"
        loader = MySQLLoader
    elif url.startswith("snowflake://"):
        db_type = "snowflake"
        loader = SnowflakeLoader
    else:
        raise InvalidArgumentError("Invalid database URL format")

    return loader, {
        "type": "reasoning_step",
        "message": f"Step {steps_counter}: Detected database type: {db_type}. "
        "Attempting to load schema...",
    }


async def _step_attempt_load(
    steps_counter: int, loader: type[BaseLoader], user_id: str, url: str
) -> AsyncGenerator[dict[str, str | bool], None]:
    """Yield the attempt to load schema step message."""
    success, result = [False, ""]
    try:
        load_start = time.perf_counter()
        async for progress in loader.load(user_id, url):
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


async def load_database(url: str, user_id: str):
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
                steps_counter, loader, user_id, url
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


async def list_databases(
    user_id: str, general_prefix: Optional[str] = None
) -> list[dict]:
    """
    List all graphs (database names) available for the user.

    Returns a list of dicts with keys ``id`` (the full FalkorDB graph name
    used for API calls), ``name`` (the display name with namespace prefix
    stripped) and ``is_demo`` (whether the graph is a shared demo graph).
    """
    user_graphs = await db.list_graphs()

    result: list[dict] = []

    # User-owned graphs: strip the user_id prefix for display
    for graph in user_graphs:
        if graph.startswith(f"{user_id}_"):
            display_name = graph[len(f"{user_id}_"):]
            result.append({"id": display_name, "name": display_name, "is_demo": False})

    # Demo/shared graphs: strip the general prefix for display
    if general_prefix:
        for graph in user_graphs:
            if graph.startswith(general_prefix):
                display_name = graph[len(general_prefix):]
                result.append({"id": graph, "name": display_name, "is_demo": True})

    return result
