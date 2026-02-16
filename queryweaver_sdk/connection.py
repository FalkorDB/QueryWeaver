"""FalkorDB connection management for QueryWeaver SDK."""

import os
from typing import Optional

from falkordb.asyncio import FalkorDB
from redis.asyncio import BlockingConnectionPool


class FalkorDBConnection:
    """Manages FalkorDB connection lifecycle for the SDK.

    This class provides explicit connection management, allowing users
    to initialize connections with specific parameters rather than
    relying solely on environment variables.
    """

    def __init__(
        self,
        url: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ):
        """Initialize FalkorDB connection.

        Args:
            url: Redis connection URL (e.g., "redis://localhost:6379").
                 Takes precedence over host/port if provided.
            host: FalkorDB host (default: "localhost").
            port: FalkorDB port (default: 6379).

        Raises:
            ConnectionError: If connection cannot be established.
        """
        self._url = url
        self._host = host
        self._port = port
        self._db: Optional[FalkorDB] = None
        self._pool: Optional[BlockingConnectionPool] = None

    @property
    def db(self) -> FalkorDB:
        """Get the FalkorDB client instance.

        Lazily initializes the connection on first access.

        Returns:
            FalkorDB client instance.

        Raises:
            ConnectionError: If connection cannot be established.
        """
        if self._db is None:
            self._db = self._create_connection()
        return self._db

    def _create_connection(self) -> FalkorDB:
        """Create and return a FalkorDB connection.

        Returns:
            FalkorDB client instance.

        Raises:
            ConnectionError: If connection cannot be established.
        """
        # Priority: explicit URL > explicit host/port > env URL > env host/port > defaults
        url = self._url or os.getenv("FALKORDB_URL")

        if url:
            try:
                self._pool = BlockingConnectionPool.from_url(
                    url,
                    decode_responses=True
                )
                return FalkorDB(connection_pool=self._pool)
            except Exception as e:
                raise ConnectionError(f"Failed to connect to FalkorDB with URL: {e}") from e

        # Fall back to host/port
        host = self._host or os.getenv("FALKORDB_HOST", "localhost")
        port = self._port or int(os.getenv("FALKORDB_PORT", "6379"))

        try:
            return FalkorDB(host=host, port=port)
        except Exception as e:
            raise ConnectionError(f"Failed to connect to FalkorDB at {host}:{port}: {e}") from e

    @classmethod
    def from_env(cls) -> "FalkorDBConnection":
        """Create connection from environment variables.

        Uses FALKORDB_URL if set, otherwise FALKORDB_HOST and FALKORDB_PORT.

        Returns:
            FalkorDBConnection instance.
        """
        return cls()

    @classmethod
    def from_url(cls, url: str) -> "FalkorDBConnection":
        """Create connection from a Redis URL.

        Args:
            url: Redis connection URL (e.g., "redis://localhost:6379").

        Returns:
            FalkorDBConnection instance.
        """
        return cls(url=url)

    async def close(self) -> None:
        """Close the connection and release resources."""
        if self._pool is not None:
            await self._pool.disconnect()
            self._pool = None
        elif self._db is not None:
            # Non-pooled connection (created via host/port) — close directly
            await self._db.connection.aclose()
        self._db = None

    def select_graph(self, graph_id: str):
        """Select a graph by ID.

        Args:
            graph_id: The graph identifier.

        Returns:
            Graph instance for the specified ID.
        """
        return self.db.select_graph(graph_id)

    async def list_graphs(self) -> list[str]:
        """List all available graphs.

        Returns:
            List of graph names.
        """
        return await self.db.list_graphs()
