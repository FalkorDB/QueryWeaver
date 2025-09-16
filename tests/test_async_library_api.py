"""
Unit tests for QueryWeaver async library API.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch

# Add src to Python path for testing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from queryweaver import AsyncQueryWeaverClient, create_async_client


@pytest.fixture
def mock_falkordb():
    """Fixture to mock FalkorDB connection."""
    with patch('falkordb.FalkorDB') as mock_db1:
        mock_db1.return_value.ping.return_value = True
        with patch('queryweaver.base.falkordb.FalkorDB') as mock_db2:
            mock_db2.return_value.ping.return_value = True
            yield mock_db1.return_value


@pytest.fixture
def async_client(mock_falkordb):
    """Fixture to create an AsyncQueryWeaverClient for testing."""
    return AsyncQueryWeaverClient(
        falkordb_url="redis://localhost:6379/0",
        openai_api_key="test-key"
    )


class TestAsyncQueryWeaverClientInit:
    """Test AsyncQueryWeaverClient initialization."""

    def test_init_with_openai_key(self, mock_falkordb):
        """Test async client initialization with OpenAI API key."""
        client = AsyncQueryWeaverClient(
            falkordb_url="redis://localhost:6379/0",
            openai_api_key="test-key"
        )
        assert client.falkordb_url == "redis://localhost:6379/0"
        assert client._user_id == "library_user"
        assert len(client._loaded_databases) == 0

    def test_init_with_azure_key(self, mock_falkordb):
        """Test async client initialization with Azure API key."""
        client = AsyncQueryWeaverClient(
            falkordb_url="redis://localhost:6379/0",
            azure_api_key="test-azure-key"
        )
        assert client.falkordb_url == "redis://localhost:6379/0"

    def test_init_without_api_key_raises_error(self, mock_falkordb):
        """Test that missing API key raises ValueError."""
        # Clear any existing API keys
        import os
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("AZURE_API_KEY", None)
        
        with pytest.raises(ValueError, match="Either openai_api_key or azure_api_key must be provided"):
            AsyncQueryWeaverClient(falkordb_url="redis://localhost:6379/0")

    def test_init_with_invalid_falkordb_url_raises_error(self, mock_falkordb):
        """Test that invalid FalkorDB URL raises ValueError."""
        with pytest.raises(ValueError, match="FalkorDB URL must use redis:// or rediss:// scheme"):
            AsyncQueryWeaverClient(
                falkordb_url="invalid://localhost:6379",
                openai_api_key="test-key"
            )

    @patch('falkordb.FalkorDB')
    def test_init_with_falkordb_connection_error(self, mock_falkordb):
        """Test that FalkorDB connection error raises ConnectionError."""
        mock_falkordb.return_value.ping.side_effect = Exception("Connection failed")
        
        with pytest.raises(ConnectionError, match="Cannot connect to FalkorDB"):
            AsyncQueryWeaverClient(
                falkordb_url="redis://localhost:6379/0",
                openai_api_key="test-key"
            )


class TestAsyncLoadDatabase:
    """Test async database loading functionality."""

    @pytest.mark.asyncio
    async def test_load_database_empty_name_raises_error(self, async_client):
        """Test that empty database name raises ValueError."""
        with pytest.raises(ValueError, match="Database name cannot be empty"):
            await async_client.load_database("", "postgresql://user:pass@host/db")

    @pytest.mark.asyncio
    async def test_load_database_empty_url_raises_error(self, async_client):
        """Test that empty database URL raises ValueError."""
        with pytest.raises(ValueError, match="Database URL cannot be empty"):
            await async_client.load_database("test", "")

    @pytest.mark.asyncio
    async def test_load_database_invalid_url_raises_error(self, async_client):
        """Test that invalid database URL raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported database URL format"):
            await async_client.load_database("test", "invalid://url")

    @pytest.mark.asyncio
    @patch('queryweaver.AsyncQueryWeaverClient._load_database_async')
    async def test_load_database_success(self, mock_load_async, async_client):
        """Test successful async database loading."""
        mock_load_async.return_value = True
        
        result = await async_client.load_database("test", "postgresql://user:pass@host/db")
        assert result is True
        assert "test" in async_client._loaded_databases

    @pytest.mark.asyncio
    @patch('queryweaver.AsyncQueryWeaverClient._load_database_async')
    async def test_load_database_failure(self, mock_load_async, async_client):
        """Test async database loading failure."""
        mock_load_async.return_value = False
        
        with pytest.raises(RuntimeError, match="Failed to load database schema"):
            await async_client.load_database("test", "postgresql://user:pass@host/db")


class TestAsyncTextToSQL:
    """Test async SQL generation functionality."""

    @pytest.mark.asyncio
    async def test_text_to_sql_empty_query_raises_error(self, async_client):
        """Test that empty query raises ValueError."""
        with pytest.raises(ValueError, match="Query cannot be empty"):
            await async_client.text_to_sql("test", "")

    @pytest.mark.asyncio
    async def test_text_to_sql_database_not_loaded_raises_error(self, async_client):
        """Test that unloaded database raises ValueError."""
        with pytest.raises(ValueError, match="Database 'test' not loaded"):
            await async_client.text_to_sql("test", "Show me users")

    @pytest.mark.asyncio
    @patch('queryweaver.AsyncQueryWeaverClient._generate_sql_async')
    async def test_text_to_sql_success(self, mock_generate_async, async_client):
        """Test successful async SQL generation."""
        # Add database to loaded set
        async_client._loaded_databases.add("test")
        mock_generate_async.return_value = "SELECT * FROM users;"
        
        result = await async_client.text_to_sql("test", "Show me all users")
        assert result == "SELECT * FROM users;"

    @pytest.mark.asyncio
    @patch('queryweaver.AsyncQueryWeaverClient._generate_sql_async')
    async def test_text_to_sql_with_instructions(self, mock_generate_async, async_client):
        """Test async SQL generation with instructions."""
        async_client._loaded_databases.add("test")
        mock_generate_async.return_value = "SELECT * FROM users LIMIT 10;"
        
        result = await async_client.text_to_sql(
            "test", 
            "Show me users", 
            instructions="Limit to 10 results"
        )
        assert result == "SELECT * FROM users LIMIT 10;"


class TestAsyncQuery:
    """Test async full query functionality."""

    @pytest.mark.asyncio
    async def test_query_empty_query_raises_error(self, async_client):
        """Test that empty query raises ValueError."""
        with pytest.raises(ValueError, match="Query cannot be empty"):
            await async_client.query("test", "")

    @pytest.mark.asyncio
    async def test_query_database_not_loaded_raises_error(self, async_client):
        """Test that unloaded database raises ValueError."""
        with pytest.raises(ValueError, match="Database 'test' not loaded"):
            await async_client.query("test", "Show me users")

    @pytest.mark.asyncio
    @patch('queryweaver.AsyncQueryWeaverClient._query_async')
    async def test_query_success(self, mock_query_async, async_client):
        """Test successful async query execution."""
        async_client._loaded_databases.add("test")
        
        expected_result = {
            "sql_query": "SELECT * FROM users;",
            "results": [{"id": 1, "name": "John"}],
            "error": None,
            "analysis": None
        }
        mock_query_async.return_value = expected_result
        
        result = await async_client.query("test", "Show me all users")
        assert result["sql_query"] == "SELECT * FROM users;"
        assert len(result["results"]) == 1

    @pytest.mark.asyncio
    @patch('queryweaver.AsyncQueryWeaverClient._query_async')
    async def test_query_without_execution(self, mock_query_async, async_client):
        """Test async query without SQL execution."""
        async_client._loaded_databases.add("test")
        
        expected_result = {
            "sql_query": "SELECT * FROM users;",
            "results": None,
            "error": None,
            "analysis": None
        }
        mock_query_async.return_value = expected_result
        
        result = await async_client.query("test", "Show me all users", execute_sql=False)
        assert result["sql_query"] == "SELECT * FROM users;"
        assert result["results"] is None


class TestAsyncUtilityMethods:
    """Test async utility methods."""

    def test_list_loaded_databases_empty(self, async_client):
        """Test listing loaded databases when none are loaded."""
        result = async_client.list_loaded_databases()
        assert result == []

    def test_list_loaded_databases_with_data(self, async_client):
        """Test listing loaded databases with data."""
        async_client._loaded_databases.add("db1")
        async_client._loaded_databases.add("db2")
        
        result = async_client.list_loaded_databases()
        assert len(result) == 2
        assert "db1" in result
        assert "db2" in result

    @pytest.mark.asyncio
    async def test_get_database_schema_not_loaded_raises_error(self, async_client):
        """Test that schema retrieval for unloaded database raises ValueError."""
        with pytest.raises(ValueError, match="Database 'test' not loaded"):
            await async_client.get_database_schema("test")

    @pytest.mark.asyncio
    @patch('queryweaver.AsyncQueryWeaverClient._get_schema_async')
    async def test_get_database_schema_success(self, mock_schema_async, async_client):
        """Test successful async schema retrieval."""
        async_client._loaded_databases.add("test")
        
        expected_schema = {"tables": ["users", "orders"]}
        mock_schema_async.return_value = expected_schema
        
        result = await async_client.get_database_schema("test")
        assert result == expected_schema

    @pytest.mark.asyncio
    async def test_close_method(self, async_client):
        """Test async client close method."""
        # Should not raise any errors
        await async_client.close()

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_falkordb):
        """Test async client as context manager."""
        async with AsyncQueryWeaverClient(
            falkordb_url="redis://localhost:6379/0",
            openai_api_key="test-key"
        ) as client:
            assert client is not None
            assert isinstance(client, AsyncQueryWeaverClient)


class TestCreateAsyncClient:
    """Test create_async_client convenience function."""

    def test_create_async_client_success(self, mock_falkordb):
        """Test successful async client creation via convenience function."""
        client = create_async_client(
            falkordb_url="redis://localhost:6379/0",
            openai_api_key="test-key"
        )
        assert isinstance(client, AsyncQueryWeaverClient)
        assert client.falkordb_url == "redis://localhost:6379/0"

    def test_create_async_client_with_additional_args(self, mock_falkordb):
        """Test async client creation with additional arguments."""
        client = create_async_client(
            falkordb_url="redis://localhost:6379/0",
            openai_api_key="test-key",
            completion_model="custom-model"
        )
        assert isinstance(client, AsyncQueryWeaverClient)