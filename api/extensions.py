"""Extensions for the text2sql library"""

import os

from falkordb.asyncio import FalkorDB
from redis.asyncio import BlockingConnectionPool

# Connect to FalkorDB
url = os.getenv("FALKORDB_URL", None)
if url is None:
    try:
        db = FalkorDB(host="localhost", port=6379)
    except Exception as e:  # pylint: disable=broad-exception-caught
        raise ConnectionError(f"Failed to connect to FalkorDB: {e}") from e
else:
    # Ensure the URL is properly encoded as string and handle potential encoding issues
    try:
        # Create connection pool with explicit encoding settings
        pool = BlockingConnectionPool.from_url(
            url,
            decode_responses=True
        )
        db = FalkorDB(connection_pool=pool)
    except Exception as e:  # pylint: disable=broad-exception-caught
        raise ConnectionError(f"Failed to connect to FalkorDB with URL: {e}") from e
