"""
Base class for QueryWeaver clients containing shared functionality.
"""

import os
import logging
from typing import Optional, Set, Dict, Any, List
from urllib.parse import urlparse

import falkordb


class BaseQueryWeaverClient:
    """
    Base class for QueryWeaver clients containing common initialization and validation logic.
    
    This class should not be instantiated directly. Use QueryWeaverClient or AsyncQueryWeaverClient.
    """

    def __init__(
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
        # Import config and configure logging
        from api.config import Config, configure_litellm_logging
        configure_litellm_logging()

        # Override model configurations if provided
        if completion_model:
            # Modify the config directly since it's a class-level attribute
            if hasattr(Config, 'COMPLETION_MODEL'):
                object.__setattr__(Config, 'COMPLETION_MODEL', completion_model)
        if embedding_model:
            if hasattr(Config, 'EMBEDDING_MODEL_NAME'):
                object.__setattr__(Config, 'EMBEDDING_MODEL_NAME', embedding_model)
            from api.config import EmbeddingsModel
            if hasattr(Config, 'EMBEDDING_MODEL'):
                object.__setattr__(Config, 'EMBEDDING_MODEL', EmbeddingsModel(model_name=embedding_model))

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
            self._test_connection = falkordb.FalkorDB(
                host=parsed_url.hostname or "localhost",
                port=parsed_url.port or 6379,
                password=parsed_url.password,
                db=int(parsed_url.path.lstrip("/")) if parsed_url.path and parsed_url.path != "/" else 0
            )
            # Test the connection
            self._test_connection.ping()
            # Close the test connection to avoid resource leaks
            self._test_connection.close()

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

    def _prepare_chat_data(self, query: str, instructions: Optional[str], chat_history: Optional[List[str]]):
        """Prepare chat data for API calls."""
        from .core.text2sql import ChatRequest
        
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