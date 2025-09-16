"""
Unit tests for QueryWeaver Python library.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock
from queryweaver import QueryWeaverClient, create_client


class TestQueryWeaverClientInit:
    """Test QueryWeaverClient initialization."""

    def test_init_with_openai_key(self):
        """Test initialization with OpenAI API key."""
        client = QueryWeaverClient(
            falkordb_url="redis://localhost:6379/0",
            openai_api_key="test-key"
        )
        assert client.falkordb_url == "redis://localhost:6379/0"
        assert client._user_id == "library_user"
        assert len(client._loaded_databases) == 0

    def test_init_with_azure_key(self):
        """Test initialization with Azure API key.""" 
        client = QueryWeaverClient(
            falkordb_url="redis://localhost:6379/0",
            azure_api_key="test-azure-key"
        )
        assert client.falkordb_url == "redis://localhost:6379/0"

    def test_init_no_api_key_raises_error(self):
        """Test that missing API key raises ValueError."""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match="Either openai_api_key or azure_api_key must be provided"):
                QueryWeaverClient(falkordb_url="redis://localhost:6379/0")

    def test_init_invalid_falkordb_url_raises_error(self):
        """Test that invalid FalkorDB URL raises ValueError."""
        with pytest.raises(ValueError, match="FalkorDB URL must use redis:// or rediss:// scheme"):
            QueryWeaverClient(
                falkordb_url="http://localhost:6379",
                openai_api_key="test-key"
            )

    @patch('falkordb.FalkorDB')
    def test_init_falkordb_connection_failure_raises_error(self, mock_falkordb):
        """Test that FalkorDB connection failure raises ConnectionError."""
        mock_falkordb.return_value.ping.side_effect = Exception("Connection failed")
        
        with pytest.raises(ConnectionError, match="Cannot connect to FalkorDB"):
            QueryWeaverClient(
                falkordb_url="redis://localhost:6379/0",
                openai_api_key="test-key"
            )

    @patch('falkordb.FalkorDB')
    def test_init_with_custom_models(self, mock_falkordb):
        """Test initialization with custom model configurations."""
        mock_falkordb.return_value.ping.return_value = True
        
        client = QueryWeaverClient(
            falkordb_url="redis://localhost:6379/0",
            openai_api_key="test-key",
            completion_model="gpt-4-turbo",
            embedding_model="text-embedding-3-large"
        )
        assert client.falkordb_url == "redis://localhost:6379/0"


class TestLoadDatabase:
    """Test database loading functionality."""

    @patch('falkordb.FalkorDB')
    def setUp(self, mock_falkordb):
        """Set up test client.""" 
        mock_falkordb.return_value.ping.return_value = True
        self.client = QueryWeaverClient(
            falkordb_url="redis://localhost:6379/0",
            openai_api_key="test-key"
        )

    def test_load_database_empty_name_raises_error(self):
        """Test that empty database name raises ValueError."""
        self.setUp()
        with pytest.raises(ValueError, match="Database name cannot be empty"):
            self.client.load_database("", "postgresql://user:pass@host/db")

    def test_load_database_empty_url_raises_error(self):
        """Test that empty database URL raises ValueError."""
        self.setUp()
        with pytest.raises(ValueError, match="Database URL cannot be empty"):
            self.client.load_database("test", "")

    def test_load_database_invalid_url_raises_error(self):
        """Test that invalid database URL raises ValueError."""
        self.setUp()
        with pytest.raises(ValueError, match="Unsupported database URL format"):
            self.client.load_database("test", "invalid://url")

    @patch('queryweaver.QueryWeaverClient._load_database_async')
    def test_load_database_success(self, mock_load_async):
        """Test successful database loading."""
        self.setUp()
        mock_load_async.return_value = asyncio.Future()
        mock_load_async.return_value.set_result(True)
        
        with patch('asyncio.run', return_value=True):
            result = self.client.load_database("test", "postgresql://user:pass@host/db")
            assert result is True
            assert "test" in self.client._loaded_databases

    @patch('queryweaver.QueryWeaverClient._load_database_async')
    def test_load_database_failure(self, mock_load_async):
        """Test database loading failure."""
        self.setUp()
        mock_load_async.return_value = asyncio.Future()
        mock_load_async.return_value.set_result(False)
        
        with patch('asyncio.run', return_value=False):
            with pytest.raises(RuntimeError, match="Failed to load database schema"):
                self.client.load_database("test", "postgresql://user:pass@host/db")


class TestTextToSQL:
    """Test SQL generation functionality."""

    @patch('falkordb.FalkorDB')
    def setUp(self, mock_falkordb):
        """Set up test client with loaded database."""
        mock_falkordb.return_value.ping.return_value = True
        self.client = QueryWeaverClient(
            falkordb_url="redis://localhost:6379/0", 
            openai_api_key="test-key"
        )
        self.client._loaded_databases.add("test_db")

    def test_text_to_sql_empty_query_raises_error(self):
        """Test that empty query raises ValueError."""
        self.setUp()
        with pytest.raises(ValueError, match="Query cannot be empty"):
            self.client.text_to_sql("test_db", "")

    def test_text_to_sql_database_not_loaded_raises_error(self):
        """Test that querying unloaded database raises ValueError."""
        self.setUp()
        with pytest.raises(ValueError, match="Database 'nonexistent' not loaded"):
            self.client.text_to_sql("nonexistent", "show data")

    @patch('queryweaver.QueryWeaverClient._generate_sql_async')
    def test_text_to_sql_success(self, mock_generate_async):
        """Test successful SQL generation."""
        self.setUp()
        mock_generate_async.return_value = asyncio.Future()
        mock_generate_async.return_value.set_result("SELECT * FROM users")
        
        with patch('asyncio.run', return_value="SELECT * FROM users"):
            result = self.client.text_to_sql("test_db", "show all users")
            assert result == "SELECT * FROM users"

    @patch('queryweaver.QueryWeaverClient._generate_sql_async')
    def test_text_to_sql_with_history_and_instructions(self, mock_generate_async):
        """Test SQL generation with chat history and instructions."""
        self.setUp()
        mock_generate_async.return_value = asyncio.Future()
        mock_generate_async.return_value.set_result("SELECT * FROM users WHERE age > 18")
        
        with patch('asyncio.run', return_value="SELECT * FROM users WHERE age > 18"):
            result = self.client.text_to_sql(
                database_name="test_db",
                query="filter by adult users",
                instructions="Use age > 18 for adults",
                chat_history=["show users"]
            )
            assert "SELECT" in result


class TestQuery:
    """Test full query functionality."""

    @patch('falkordb.FalkorDB') 
    def setUp(self, mock_falkordb):
        """Set up test client with loaded database."""
        mock_falkordb.return_value.ping.return_value = True
        self.client = QueryWeaverClient(
            falkordb_url="redis://localhost:6379/0",
            openai_api_key="test-key"
        )
        self.client._loaded_databases.add("test_db")

    @patch('queryweaver.QueryWeaverClient._query_async')
    def test_query_success(self, mock_query_async):
        """Test successful query execution."""
        self.setUp()
        mock_result = {
            "sql_query": "SELECT * FROM users",
            "results": [{"id": 1, "name": "John"}],
            "error": None,
            "analysis": {"explanation": "Query retrieves all users"}
        }
        mock_query_async.return_value = asyncio.Future()
        mock_query_async.return_value.set_result(mock_result)
        
        with patch('asyncio.run', return_value=mock_result):
            result = self.client.query("test_db", "show all users")
            assert result["sql_query"] == "SELECT * FROM users"
            assert len(result["results"]) == 1
            assert result["analysis"]["explanation"] == "Query retrieves all users"

    @patch('queryweaver.QueryWeaverClient._query_async') 
    def test_query_sql_only(self, mock_query_async):
        """Test query with execute_sql=False."""
        self.setUp()
        mock_result = {
            "sql_query": "SELECT COUNT(*) FROM orders",
            "results": None,
            "error": None,
            "analysis": None
        }
        mock_query_async.return_value = asyncio.Future()
        mock_query_async.return_value.set_result(mock_result)
        
        with patch('asyncio.run', return_value=mock_result):
            result = self.client.query("test_db", "count orders", execute_sql=False)
            assert result["sql_query"] == "SELECT COUNT(*) FROM orders"
            assert result["results"] is None


class TestUtilityMethods:
    """Test utility methods."""

    @patch('falkordb.FalkorDB')
    def setUp(self, mock_falkordb):
        """Set up test client."""
        mock_falkordb.return_value.ping.return_value = True
        self.client = QueryWeaverClient(
            falkordb_url="redis://localhost:6379/0",
            openai_api_key="test-key"
        )

    def test_list_loaded_databases_empty(self):
        """Test listing databases when none are loaded."""
        self.setUp()
        result = self.client.list_loaded_databases()
        assert result == []

    def test_list_loaded_databases_with_data(self):
        """Test listing databases with loaded data."""
        self.setUp()
        self.client._loaded_databases.add("db1")
        self.client._loaded_databases.add("db2")
        
        result = self.client.list_loaded_databases()
        assert len(result) == 2
        assert "db1" in result
        assert "db2" in result

    @patch('queryweaver.QueryWeaverClient._get_schema_async')
    def test_get_database_schema_success(self, mock_get_schema_async):
        """Test successful schema retrieval."""
        self.setUp()
        self.client._loaded_databases.add("test_db")
        
        mock_schema = {"tables": ["users", "orders"], "columns": {}}
        mock_get_schema_async.return_value = asyncio.Future()
        mock_get_schema_async.return_value.set_result(mock_schema)
        
        with patch('asyncio.run', return_value=mock_schema):
            result = self.client.get_database_schema("test_db")
            assert result["tables"] == ["users", "orders"]

    def test_get_database_schema_not_loaded_raises_error(self):
        """Test schema retrieval for unloaded database raises ValueError."""
        self.setUp()
        with pytest.raises(ValueError, match="Database 'nonexistent' not loaded"):
            self.client.get_database_schema("nonexistent")


class TestConvenienceFunction:
    """Test convenience functions."""

    @patch('falkordb.FalkorDB')
    def test_create_client_function(self, mock_falkordb):
        """Test create_client convenience function."""
        mock_falkordb.return_value.ping.return_value = True
        
        client = create_client(
            falkordb_url="redis://localhost:6379/0",
            openai_api_key="test-key"
        )
        
        assert isinstance(client, QueryWeaverClient)
        assert client.falkordb_url == "redis://localhost:6379/0"


class TestAsyncHelpers:
    """Test async helper methods."""

    @patch('falkordb.FalkorDB')
    def setUp(self, mock_falkordb):
        """Set up test client."""
        mock_falkordb.return_value.ping.return_value = True
        self.client = QueryWeaverClient(
            falkordb_url="redis://localhost:6379/0",
            openai_api_key="test-key"
        )

    @pytest.mark.asyncio
    @patch('api.core.text2sql.query_database')
    async def test_generate_sql_async(self, mock_query_database):
        """Test async SQL generation helper."""
        self.setUp()
        
        # Mock the generator returned by query_database
        async def mock_generator():
            yield json.dumps({"type": "sql_query", "data": "SELECT * FROM users"})
        
        mock_query_database.return_value = mock_generator()
        
        from api.core.text2sql import ChatRequest
        chat_data = ChatRequest(chat=["show users"])
        
        result = await self.client._generate_sql_async("test_db", chat_data)
        assert result == "SELECT * FROM users"

    @pytest.mark.asyncio
    @patch('api.core.text2sql.query_database')
    async def test_query_async(self, mock_query_database):
        """Test async full query helper."""
        self.setUp()
        
        # Mock the generator with multiple response types
        async def mock_generator():
            yield json.dumps({"type": "sql_query", "data": "SELECT * FROM users"})
            yield json.dumps({
                "type": "analysis", 
                "exp": "Retrieves all users",
                "amb": "None",
                "miss": "None"
            })
            yield json.dumps({"type": "query_results", "results": [{"id": 1}]})
            yield json.dumps({"type": "final_result"})
        
        mock_query_database.return_value = mock_generator()
        
        from api.core.text2sql import ChatRequest
        chat_data = ChatRequest(chat=["show users"])
        
        result = await self.client._query_async("test_db", chat_data, execute_sql=True)
        
        assert result["sql_query"] == "SELECT * FROM users"
        assert result["analysis"]["explanation"] == "Retrieves all users"
        assert result["results"] == [{"id": 1}]


if __name__ == "__main__":
    pytest.main([__file__])