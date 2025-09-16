"""
Synchronous QueryWeaver Client

This module provides the synchronous Python API for QueryWeaver functionality,
allowing users to work directly from Python without running as a FastAPI server.

Example usage:
    from queryweaver.sync import QueryWeaverClient
    
    # Initialize client
    client = QueryWeaverClient(
        falkordb_url="redis://localhost:6379/0",
        openai_api_key="your-api-key"
    )
    
    # Load a database
    client.load_database("mydatabase", "postgresql://user:pass@host:port/db")
    
    # Generate SQL
    sql = client.text_to_sql("mydatabase", "Show all customers from California")
    
    # Execute query and get results
    results = client.query("mydatabase", "Show all customers from California")
"""

import asyncio
import json
import logging
from typing import List, Dict, Any, Optional

# Import base class and core modules
from .base import BaseQueryWeaverClient
from .core.text2sql import (
    query_database, 
    get_database_type_and_loader,
    GraphNotFoundError,
    InternalError,
    InvalidArgumentError
)


class QueryWeaverClient(BaseQueryWeaverClient):
    """
    A Python client for QueryWeaver that provides Text2SQL functionality.
    
    This client allows you to:
    1. Connect to FalkorDB for schema storage
    2. Load database schemas from PostgreSQL or MySQL
    3. Generate SQL from natural language queries
    4. Execute queries and return results
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
        Initialize the QueryWeaver client.
        
        Args:
            falkordb_url: URL for FalkorDB connection (e.g., "redis://localhost:6379/0")
            openai_api_key: OpenAI API key for LLM operations
            azure_api_key: Azure OpenAI API key (alternative to openai_api_key)
            completion_model: Override default completion model
            embedding_model: Override default embedding model
            
        Raises:
            ValueError: If neither OpenAI nor Azure API key is provided
            ConnectionError: If cannot connect to FalkorDB
        """
        # Initialize using base class
        super().__init__(
            falkordb_url=falkordb_url,
            openai_api_key=openai_api_key,
            azure_api_key=azure_api_key,
            completion_model=completion_model,
            embedding_model=embedding_model
        )
        
        logging.info("QueryWeaver client initialized successfully")
    
    def load_database(self, database_name: str, database_url: str) -> bool:
        """
        Load a database schema into FalkorDB for querying.
        
        Args:
            database_name: Unique name to identify this database
            database_url: Connection URL for the source database
                         (e.g., "postgresql://user:pass@host:port/db")
        
        Returns:
            bool: True if database was loaded successfully
            
        Raises:
            ValueError: If database URL format is invalid
            ConnectionError: If cannot connect to source database
            RuntimeError: If schema loading fails
        """
        # Use base class validation
        database_name = self._validate_database_params(database_name, database_url)

        # Validate database URL format
        db_type, loader_class = get_database_type_and_loader(database_url)
        if not loader_class:
            raise ValueError(
                "Unsupported database URL format. "
                "Supported formats: postgresql://, postgres://, mysql://"
            )

        logging.info("Loading database '%s' from %s", database_name, db_type)
        
        try:
            # Run the async loader in a sync context
            success = asyncio.run(self._load_database_async(database_name, database_url, loader_class))
            
            if success:
                self._loaded_databases.add(database_name)
                logging.info("Successfully loaded database '%s'", database_name)
                return True
            else:
                raise RuntimeError(f"Failed to load database schema for '{database_name}'")
                
        except ValueError:
            raise
        except Exception as e:
            logging.exception("Error loading database '%s'", database_name)
            raise RuntimeError(f"Failed to load database '{database_name}'") from e
    
    async def _load_database_async(self, database_name: str, database_url: str, loader_class) -> bool:
        """Async helper for loading database schema."""
        try:
            success = False
            async for progress in loader_class.load(self._user_id, database_url):
                success, result = progress
                if not success:
                    logging.error("Database loader error: %s", result)
                    break
            return success
        except ValueError:
            raise
        except Exception:
            logging.exception("Exception during database loading")
            return False
    
    def text_to_sql(
        self, 
        database_name: str, 
        query: str,
        instructions: Optional[str] = None,
        chat_history: Optional[List[str]] = None
    ) -> str:
        """
        Generate SQL from natural language query.
        
        Args:
            database_name: Name of the loaded database to query
            query: Natural language query
            instructions: Optional additional instructions for SQL generation
            chat_history: Optional previous queries for context
        
        Returns:
            str: Generated SQL query
            
        Raises:
            ValueError: If database not loaded or query is empty
            RuntimeError: If SQL generation fails
        """
        # Use base class validation
        self._validate_query_params(database_name, query)
        
        # Use base class helper to prepare chat data
        chat_data = self._prepare_chat_data(query, instructions, chat_history)
        
        try:
            # Run the async query processor and extract just the SQL
            return asyncio.run(self._generate_sql_async(database_name, chat_data))

        except ValueError:
            raise
        except Exception as e:
            logging.exception("Error generating SQL")
            raise RuntimeError("Failed to generate SQL") from e

    async def _generate_sql_async(self, database_name: str, chat_data) -> str:
        """Async helper for SQL generation that processes the streaming response."""
        try:
            # Use the existing query_database function but extract just the SQL
            sql_query = None
            
            # Get the generator from query_database
            generator = await query_database(self._user_id, database_name, chat_data)
            
            async for chunk in generator:
                if isinstance(chunk, str):
                    try:
                        data = json.loads(chunk)
                        if data.get("type") == "sql_query":
                            sql_query = data.get("data", "").strip()
                            break
                    except json.JSONDecodeError:
                        continue
            
            if not sql_query:
                raise RuntimeError("No SQL query generated")
            
            return sql_query
            
        except (GraphNotFoundError, InvalidArgumentError) as e:
            raise ValueError(str(e)) from e
        except InternalError as e:
            raise RuntimeError(str(e)) from e
    
    def query(
        self, 
        database_name: str, 
        query: str,
        instructions: Optional[str] = None,
        chat_history: Optional[List[str]] = None,
        execute_sql: bool = True
    ) -> Dict[str, Any]:
        """
        Generate SQL and optionally execute it, returning results.
        
        Args:
            database_name: Name of the loaded database to query
            query: Natural language query
            instructions: Optional additional instructions for SQL generation
            chat_history: Optional previous queries for context
            execute_sql: Whether to execute the SQL or just return it
        
        Returns:
            dict: Contains 'sql_query' and optionally 'results', 'error' fields
            
        Raises:
            ValueError: If database not loaded or query is empty
            RuntimeError: If processing fails
        """
        # Use base class validation
        self._validate_query_params(database_name, query)
        
        # Use base class helper to prepare chat data
        chat_data = self._prepare_chat_data(query, instructions, chat_history)
        
        try:
            # Run the async query processor
            return asyncio.run(self._query_async(database_name, chat_data, execute_sql))
            
        except ValueError:
            raise
        except Exception as e:
            logging.exception("Error processing query")
            raise RuntimeError("Failed to process query") from e
    
    async def _query_async(self, database_name: str, chat_data, execute_sql: bool) -> Dict[str, Any]:
        """Async helper for full query processing."""
        try:
            result: Dict[str, Any] = {
                "sql_query": None,
                "results": None,
                "error": None,
                "analysis": None
            }
            
            # Get the generator from query_database
            generator = await query_database(self._user_id, database_name, chat_data)
            
            # Process the streaming response from query_database
            async for chunk in generator:
                if isinstance(chunk, str):
                    try:
                        data = json.loads(chunk)
                        
                        if data.get("type") == "sql_query":
                            result["sql_query"] = data.get("data", "").strip()
                            # Extract analysis data from sql_query message
                            result["analysis"] = {
                                "explanation": data.get("exp", ""),
                                "assumptions": data.get("assumptions", ""),
                                "ambiguities": data.get("amb", ""),
                                "missing_information": data.get("miss", "")
                            }
                        
                        elif data.get("type") == "query_results" and execute_sql:
                            result["results"] = data.get("results", [])
                        
                        elif data.get("type") == "error":
                            result["error"] = data.get("message", "Unknown error")
                        
                        elif data.get("type") == "final_result":
                            # This indicates completion of processing
                            break
                            
                    except json.JSONDecodeError:
                        continue
            
            return result
            
        except (GraphNotFoundError, InvalidArgumentError) as e:
            raise ValueError(str(e)) from e
        except InternalError as e:
            raise RuntimeError(str(e)) from e
    
    def get_database_schema(self, database_name: str) -> Dict[str, Any]:
        """
        Get the schema information for a loaded database.
        
        Args:
            database_name: Name of the loaded database
        
        Returns:
            dict: Database schema information
            
        Raises:
            ValueError: If database not loaded
            RuntimeError: If schema retrieval fails
        """
        if database_name not in self._loaded_databases:
            raise ValueError(f"Database '{database_name}' not loaded. Call load_database() first.")
        
        try:
            # Run async schema retrieval
            return asyncio.run(self._get_schema_async(database_name))
            
        except ValueError:
            raise
        except Exception as e:
            logging.exception("Error retrieving schema for '%s'", database_name)
            raise RuntimeError("Failed to retrieve schema") from e
    
    async def _get_schema_async(self, database_name: str) -> Dict[str, Any]:
        """Async helper for schema retrieval."""
        try:
            from .core.text2sql import get_schema
            schema = await get_schema(self._user_id, database_name)
            return schema
        except GraphNotFoundError as e:
            raise ValueError(str(e)) from e
        except InternalError as e:
            raise RuntimeError(str(e)) from e


# Convenience function for quick usage
def create_client(
    falkordb_url: str,
    openai_api_key: Optional[str] = None,
    azure_api_key: Optional[str] = None,
    **kwargs
) -> QueryWeaverClient:
    """
    Convenience function to create a QueryWeaver client.
    
    Args:
        falkordb_url: URL for FalkorDB connection
        openai_api_key: OpenAI API key for LLM operations
        azure_api_key: Azure OpenAI API key (alternative to openai_api_key)
        **kwargs: Additional arguments passed to QueryWeaverClient
    
    Returns:
        QueryWeaverClient: Initialized client instance
    """
    return QueryWeaverClient(
        falkordb_url=falkordb_url,
        openai_api_key=openai_api_key,
        azure_api_key=azure_api_key,
        **kwargs
    )