"""
Base class for QueryWeaver clients containing shared functionality.
"""

import os
from typing import Optional, Set, List
import json
from urllib.parse import urlparse
from typing import Any, Dict, List, Optional, Set

import falkordb

# Try to import API config modules (may not be available in standalone library)
try:
    from api.config import Config, configure_litellm_logging, EmbeddingsModel
except ImportError:
    Config = None
    configure_litellm_logging = None
    EmbeddingsModel = None

# Import core modules
from .core.text2sql import ChatRequest


class BaseQueryWeaverClient:  # pylint: disable=too-few-public-methods
    """
    Base class for QueryWeaver clients containing common initialization and validation logic.

    This class should not be instantiated directly. Use QueryWeaverClient or AsyncQueryWeaverClient.
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        falkordb_url: str,
        openai_api_key: Optional[str] = None,
        azure_api_key: Optional[str] = None,
        completion_model: Optional[str] = None,
        embedding_model: Optional[str] = None
    ):
        """
        Initialize the base QueryWeaver client.

        Args:
            falkordb_url: Redis URL for FalkorDB connection (e.g., "redis://localhost:6379/0")
            openai_api_key: OpenAI API key for LLM operations
            azure_api_key: Azure OpenAI API key (alternative to openai_api_key)
            completion_model: Override default completion model
            embedding_model: Override default embedding model

        Raises:
            ValueError: If required parameters are missing or invalid
            ConnectionError: If cannot connect to FalkorDB
        """
        # Configure API keys
        self._configure_api_keys(openai_api_key, azure_api_key)

        # Configure models if provided
        self._configure_models(completion_model, embedding_model)

        # Configure FalkorDB connection
        self._configure_falkordb(falkordb_url)

        # Initialize client state
        self.falkordb_url = falkordb_url
        self._user_id = "library_user"  # Default user ID for library usage
        self._loaded_databases: Set[str] = set()

    def _configure_api_keys(self, openai_api_key: Optional[str], azure_api_key: Optional[str]):
        """Configure API keys for LLM operations."""
        if openai_api_key:
            os.environ["OPENAI_API_KEY"] = openai_api_key
        elif azure_api_key:
            os.environ["AZURE_API_KEY"] = azure_api_key
        elif not os.getenv("OPENAI_API_KEY") and not os.getenv("AZURE_API_KEY"):
            raise ValueError("Either openai_api_key or azure_api_key must be provided")

    def _configure_models(self, completion_model: Optional[str], embedding_model: Optional[str]):
        """Configure model overrides if provided."""
        # Configure logging if available
        if configure_litellm_logging:
            configure_litellm_logging()

        # Override model configurations if provided and Config is available
        if Config and completion_model:
            # Modify the config directly since it's a class-level attribute
            if hasattr(Config, 'COMPLETION_MODEL'):
                setattr(Config, 'COMPLETION_MODEL', completion_model)
        if Config and embedding_model:
            if hasattr(Config, 'EMBEDDING_MODEL_NAME'):
                setattr(Config, 'EMBEDDING_MODEL_NAME', embedding_model)
            if EmbeddingsModel and hasattr(Config, 'EMBEDDING_MODEL'):
                model = EmbeddingsModel(model_name=embedding_model)
                setattr(Config, 'EMBEDDING_MODEL', model)

    def _configure_falkordb(self, falkordb_url: str):
        """Configure and test FalkorDB connection."""
        # Parse FalkorDB URL and configure connection
        parsed_url = urlparse(falkordb_url)
        if parsed_url.scheme not in ['redis', 'rediss']:
            raise ValueError("FalkorDB URL must use redis:// or rediss:// scheme")

        # Set environment variables for FalkorDB connection
        os.environ["FALKORDB_HOST"] = parsed_url.hostname or "localhost"
        os.environ["FALKORDB_PORT"] = str(parsed_url.port or 6379)
        if parsed_url.password:
            os.environ["FALKORDB_PASSWORD"] = parsed_url.password
        if parsed_url.path and parsed_url.path != "/":
            # Extract database number from path (e.g., "/0" -> "0")
            db_num = parsed_url.path.lstrip("/")
            if db_num.isdigit():
                os.environ["FALKORDB_DB"] = db_num

        # Test FalkorDB connection
        try:
            # Initialize the database connection using the existing extension
            # FalkorDB constructor may accept different kwarg names across
            # versions; try common variants and fall back to positional args.
            db_index = (int(parsed_url.path.lstrip("/"))
                        if parsed_url.path and parsed_url.path != "/"
                        else 0)

            try:
                self._test_connection = falkordb.FalkorDB(  # pylint: disable=unexpected-keyword-arg
                    host=parsed_url.hostname or "localhost",
                    port=parsed_url.port or 6379,
                    password=parsed_url.password,
                    db=db_index
                )
            except TypeError:
                try:
                    # Some versions expect `database` as the kwarg
                    self._test_connection = falkordb.FalkorDB(  # pylint: disable=unexpected-keyword-arg
                        host=parsed_url.hostname or "localhost",
                        port=parsed_url.port or 6379,
                        password=parsed_url.password,
                        database=db_index
                    )
                except TypeError:
                    # Fall back to positional args (host, port, password, db)
                    self._test_connection = falkordb.FalkorDB(
                        parsed_url.hostname or "localhost",
                        parsed_url.port or 6379,
                        parsed_url.password,
                        db_index
                    )
            # Test the connection
            self._test_connection.ping()  # pylint: disable=no-member
            # Close the test connection to avoid resource leaks
            self._test_connection.close()  # pylint: disable=no-member

        except Exception as e:
            raise ConnectionError(f"Cannot connect to FalkorDB at {falkordb_url}: {e}") from e

    def _validate_database_params(self, database_name: str, database_url: str):
        """Validate database loading parameters."""
        if not database_name or not database_name.strip():
            raise ValueError("Database name cannot be empty")

        if not database_url or not database_url.strip():
            raise ValueError("Database URL cannot be empty")

        return database_name.strip()

    def _validate_query_params(self, database_name: str, query: str):
        """Validate query parameters."""
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")

        if database_name not in self._loaded_databases:
            raise ValueError(f"Database '{database_name}' not loaded. Call load_database() first.")

    def _prepare_chat_data(
        self,
        query: str,
        instructions: Optional[str],
        chat_history: Optional[List[str]]
    ):
        """Prepare chat data for API calls."""

        # Prepare chat data
        chat_list = chat_history.copy() if chat_history else []
        chat_list.append(query.strip())

        return ChatRequest(
            chat=chat_list,
            instructions=instructions
        )

    def list_loaded_databases(self) -> List[str]:
        """
        Get list of currently loaded databases.

        Returns:
            List[str]: Names of loaded databases
        """
        return list(self._loaded_databases)

    def _extract_sql_from_stream_chunk(self, chunk: Any) -> Optional[str]:
        """
        Extracts SQL query from a stream chunk.

        Args:
            chunk: The chunk to process.

        Returns:
            Optional[str]: The SQL query if found, else None.
        """
        # Accept str, bytes, or already-parsed dict for flexibility
        data = None
        if isinstance(chunk, dict):
            data = chunk
        elif isinstance(chunk, bytes):
            try:
                data = json.loads(chunk.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                return None
        elif isinstance(chunk, str):
            try:
                data = json.loads(chunk)
            except json.JSONDecodeError:
                return None
        else:
            return None

        # If this chunk contains an SQL query payload, return the SQL and metadata
        if data.get("type") == "sql_query":
            sql = data.get("data", "")
            if not sql or not str(sql).strip():
                return None
            return str(sql).strip()

        return None

    def _process_query_stream_chunk(
        self, chunk: Any, result: Dict[str, Any], execute_sql: bool
    ) -> bool:
        """
        Process a single chunk from a streaming query response.

        This method is designed to be called in a loop over stream chunks.

        Args:
            chunk: The chunk to process.
            result: The result dictionary to populate.
            execute_sql: Flag indicating if SQL should be executed.

        Returns:
            bool: True if processing should stop ("final_result" received), False otherwise.
        """
        # Try to extract SQL (and short-circuit) using the helper which accepts
        # str/bytes/dict input. This reduces duplicated parsing logic.
        sql = self._extract_sql_from_stream_chunk(chunk)
        if sql is not None:
            # We still want to populate confidence/analysis if present, so
            # attempt to parse the chunk into data (helper already parsed for
            # some types, but parsing again is inexpensive here).
            try:
                data = json.loads(chunk) if isinstance(chunk, str) else (
                    json.loads(chunk.decode("utf-8", errors="replace"))
                    if isinstance(chunk, bytes)
                    else chunk
                )
            except Exception:
                data = {}

            result["sql_query"] = sql
            result["confidence"] = data.get("conf", 0)
            result["analysis"] = {
                "explanation": data.get("exp", ""),
                "ambiguities": data.get("amb", ""),
                "missing_information": data.get("miss", ""),
            }
            return False

        # Not an SQL chunk — parse and handle other chunk types
        if isinstance(chunk, bytes):
            try:
                data = json.loads(chunk.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                return False
        elif isinstance(chunk, str):
            try:
                data = json.loads(chunk)
            except json.JSONDecodeError:
                return False  # Continue loop
        elif isinstance(chunk, dict):
            data = chunk
        else:
            return False

        chunk_type = data.get("type")

        if chunk_type == "query_results" and execute_sql:
            result["results"] = data.get("results", [])
        elif chunk_type == "error":
            result["error"] = data.get("message", "Unknown error")
        elif chunk_type == "final_result":
            return True  # Break loop

        return False
