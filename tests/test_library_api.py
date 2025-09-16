"""
Unit tests for QueryWeaver Python library.
"""

import pytest
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

# Add src to Python path for testing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from queryweaver import QueryWeaverClient, create_client


@pytest.fixture
def mock_falkordb():
    """Fixture to mock FalkorDB connection."""
    with patch('falkordb.FalkorDB') as mock_db:
        mock_db.return_value.ping.return_value = True
        yield mock_db.return_value


@pytest.fixture
def sync_client(mock_falkordb):
    """Fixture to create a QueryWeaverClient for testing."""
    return QueryWeaverClient(
        falkordb_url="redis://localhost:6379/0",
        openai_api_key="test-key",
    )


class TestQueryWeaverClientInit:
    """Test QueryWeaverClient initialization."""

    def test_init_with_openai_key(self, mock_falkordb):
        """Test initialization with OpenAI API key."""
        client = QueryWeaverClient(
            falkordb_url="redis://localhost:6379/0",
            openai_api_key="test-key",
        )
        assert client.falkordb_url == "redis://localhost:6379/0"
        assert client._user_id == "library_user"
        assert len(client._loaded_databases) == 0

    def test_init_with_azure_key(self, mock_falkordb):
        """Test initialization with Azure API key."""
        client = QueryWeaverClient(
            falkordb_url="redis://localhost:6379/0",
            azure_api_key="test-azure-key",
        )
        assert client.falkordb_url == "redis://localhost:6379/0"

    def test_init_without_api_key_raises_error(self, mock_falkordb):
        """Test that missing API key raises ValueError."""
        # Clear any existing API keys
        import os
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("AZURE_API_KEY", None)

        with pytest.raises(
            ValueError,
            match=(
                "Either openai_api_key or azure_api_key must be provided"
            ),
        ):
            QueryWeaverClient(falkordb_url="redis://localhost:6379/0")

    def test_init_with_invalid_falkordb_url_raises_error(self, mock_falkordb):
        """Test that invalid FalkorDB URL raises ValueError."""
        with pytest.raises(ValueError, match="FalkorDB URL must use redis:// or rediss:// scheme"):
            QueryWeaverClient(
                falkordb_url="invalid://localhost:6379",
                openai_api_key="test-key",
            )

    @patch('falkordb.FalkorDB')
    def test_init_with_falkordb_connection_error(self, mock_falkordb):
        """Test that FalkorDB connection error raises ConnectionError."""
        mock_falkordb.return_value.ping.side_effect = Exception("Connection failed")

        with pytest.raises(ConnectionError, match="Cannot connect to FalkorDB"):
            QueryWeaverClient(
                falkordb_url="redis://localhost:6379/0",
                openai_api_key="test-key",
            )


class TestLoadDatabase:
    """Test database loading functionality."""

    def test_load_database_empty_name_raises_error(self, sync_client):
        """Test that empty database name raises ValueError."""
        with pytest.raises(ValueError, match="Database name cannot be empty"):
            sync_client.load_database("", "postgresql://user:pass@host/db")

    def test_load_database_empty_url_raises_error(self, sync_client):
        """Test that empty database URL raises ValueError."""
        with pytest.raises(ValueError, match="Database URL cannot be empty"):
            sync_client.load_database("test", "")

    def test_load_database_invalid_url_raises_error(self, sync_client):
        """Test that invalid database URL raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported database URL format"):
            sync_client.load_database("test", "invalid://url")

    @patch('queryweaver.QueryWeaverClient._load_database_async')
    def test_load_database_success(self, mock_load_async, sync_client):
        """Test successful database loading."""
        mock_load_async.return_value = asyncio.Future()
        mock_load_async.return_value.set_result(True)

        with patch('asyncio.run', return_value=True):
            result = sync_client.load_database("test", "postgresql://user:pass@host/db")
            assert result is True
            assert "test" in sync_client._loaded_databases

    @patch('queryweaver.QueryWeaverClient._load_database_async')
    def test_load_database_failure(self, mock_load_async, sync_client):
        """Test database loading failure."""
        mock_load_async.return_value = asyncio.Future()
        mock_load_async.return_value.set_result(False)

        with patch('asyncio.run', return_value=False):
            with pytest.raises(RuntimeError, match="Failed to load database schema"):
                sync_client.load_database("test", "postgresql://user:pass@host/db")


class TestTextToSQL:
    """Test SQL generation functionality."""

    def test_text_to_sql_empty_query_raises_error(self, sync_client):
        """Test that empty query raises ValueError."""
        with pytest.raises(ValueError, match="Query cannot be empty"):
            sync_client.text_to_sql("test", "")

    def test_text_to_sql_database_not_loaded_raises_error(self, sync_client):
        """Test that unloaded database raises ValueError."""
        with pytest.raises(ValueError, match="Database 'test' not loaded"):
            sync_client.text_to_sql("test", "Show me users")

    @patch('queryweaver.QueryWeaverClient._generate_sql_async')
    def test_text_to_sql_success(self, mock_generate_async, sync_client):
        """Test successful SQL generation."""
        # Add database to loaded set
        sync_client._loaded_databases.add("test")

        mock_generate_async.return_value = asyncio.Future()
        mock_generate_async.return_value.set_result("SELECT * FROM users;")

        with patch('asyncio.run', return_value="SELECT * FROM users;"):
            result = sync_client.text_to_sql("test", "Show me all users")
            assert result == "SELECT * FROM users;"

    @patch('queryweaver.QueryWeaverClient._generate_sql_async')
    def test_text_to_sql_with_instructions(self, mock_generate_async, sync_client):
        """Test SQL generation with instructions."""
        sync_client._loaded_databases.add("test")

        mock_generate_async.return_value = asyncio.Future()
        mock_generate_async.return_value.set_result("SELECT * FROM users LIMIT 10;")

        with patch('asyncio.run', return_value="SELECT * FROM users LIMIT 10;"):
            result = sync_client.text_to_sql(
                "test",
                "Show me users",
                instructions="Limit to 10 results",
            )
            assert result == "SELECT * FROM users LIMIT 10;"


class TestQuery:
    """Test full query functionality."""

    def test_query_empty_query_raises_error(self, sync_client):
        """Test that empty query raises ValueError."""
        with pytest.raises(ValueError, match="Query cannot be empty"):
            sync_client.query("test", "")

    def test_query_database_not_loaded_raises_error(self, sync_client):
        """Test that unloaded database raises ValueError."""
        with pytest.raises(ValueError, match="Database 'test' not loaded"):
            sync_client.query("test", "Show me users")

    @patch('queryweaver.QueryWeaverClient._query_async')
    def test_query_success(self, mock_query_async, sync_client):
        """Test successful query execution."""
        sync_client._loaded_databases.add("test")

        expected_result = {
            "sql_query": "SELECT * FROM users;",
            "results": [{"id": 1, "name": "John"}],
            "error": None,
            "analysis": None,
        }

        mock_query_async.return_value = asyncio.Future()
        mock_query_async.return_value.set_result(expected_result)

        with patch('asyncio.run', return_value=expected_result):
            result = sync_client.query("test", "Show me all users")
            assert result["sql_query"] == "SELECT * FROM users;"
            assert len(result["results"]) == 1

    @patch('queryweaver.QueryWeaverClient._query_async')
    def test_query_without_execution(self, mock_query_async, sync_client):
        """Test query without SQL execution."""
        sync_client._loaded_databases.add("test")

        expected_result = {
            "sql_query": "SELECT * FROM users;",
            "results": None,
            "error": None,
            "analysis": None,
        }

        mock_query_async.return_value = asyncio.Future()
        mock_query_async.return_value.set_result(expected_result)

        with patch('asyncio.run', return_value=expected_result):
            result = sync_client.query("test", "Show me all users", execute_sql=False)
            assert result["sql_query"] == "SELECT * FROM users;"
            assert result["results"] is None


class TestUtilityMethods:
    """Test utility methods."""

    def test_list_loaded_databases_empty(self, sync_client):
        """Test listing loaded databases when none are loaded."""
        result = sync_client.list_loaded_databases()
        assert result == []

    def test_list_loaded_databases_with_data(self, sync_client):
        """Test listing loaded databases with data."""
        sync_client._loaded_databases.add("db1")
        sync_client._loaded_databases.add("db2")

        result = sync_client.list_loaded_databases()
        assert len(result) == 2
        assert "db1" in result
        assert "db2" in result

    def test_get_database_schema_not_loaded_raises_error(self, sync_client):
        """Test that schema retrieval for unloaded database raises ValueError."""
        with pytest.raises(ValueError, match="Database 'test' not loaded"):
            sync_client.get_database_schema("test")

    @patch('queryweaver.QueryWeaverClient._get_schema_async')
    def test_get_database_schema_success(self, mock_schema_async, sync_client):
        """Test successful schema retrieval."""
        sync_client._loaded_databases.add("test")

        expected_schema = {"tables": ["users", "orders"]}
        mock_schema_async.return_value = asyncio.Future()
        mock_schema_async.return_value.set_result(expected_schema)

        with patch('asyncio.run', return_value=expected_schema):
            result = sync_client.get_database_schema("test")
            assert result == expected_schema


class TestCreateClient:
    """Test create_client convenience function."""

    def test_create_client_success(self, mock_falkordb):
        """Test successful client creation via convenience function."""
        client = create_client(
            falkordb_url="redis://localhost:6379/0",
            openai_api_key="test-key",
        )
        assert isinstance(client, QueryWeaverClient)
        assert client.falkordb_url == "redis://localhost:6379/0"

    def test_create_client_with_additional_args(self, mock_falkordb):
        """Test client creation with additional arguments."""
        client = create_client(
            falkordb_url="redis://localhost:6379/0",
            openai_api_key="test-key",
            completion_model="custom-model",
        )
        assert isinstance(client, QueryWeaverClient)