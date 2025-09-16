"""
Unit tests for QueryWeaver async library API.
"""

import pytest
import asyncio
import json
from unittest.mock import patch, AsyncMock
from queryweaver import AsyncQueryWeaverClient, create_async_client


class TestAsyncQueryWeaverClientInit:
    """Test AsyncQueryWeaverClient initialization."""

    @patch('falkordb.FalkorDB')
    def test_init_with_openai_key(self, mock_falkordb):
        """Test async client initialization with OpenAI API key."""
        mock_falkordb.return_value.ping.return_value = True
        
        client = AsyncQueryWeaverClient(
            falkordb_url="redis://localhost:6379/0",
            openai_api_key="test-key"
        )
        assert client.falkordb_url == "redis://localhost:6379/0"
        assert client._user_id == "library_user"
        assert len(client._loaded_databases) == 0

    @patch('falkordb.FalkorDB')
    def test_init_with_azure_key(self, mock_falkordb):
        """Test async client initialization with Azure API key."""
        mock_falkordb.return_value.ping.return_value = True
        
        client = AsyncQueryWeaverClient(
            falkordb_url="redis://localhost:6379/0",
            azure_api_key="test-azure-key"
        )
        assert client.falkordb_url == "redis://localhost:6379/0"

    def test_init_no_api_key_raises_error(self):
        """Test that missing API key raises ValueError."""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match="Either openai_api_key or azure_api_key must be provided"):
                AsyncQueryWeaverClient(falkordb_url="redis://localhost:6379/0")

    def test_init_invalid_falkordb_url_raises_error(self):
        """Test that invalid FalkorDB URL raises ValueError."""
        with pytest.raises(ValueError, match="FalkorDB URL must use redis:// or rediss:// scheme"):
            AsyncQueryWeaverClient(
                falkordb_url="http://localhost:6379",
                openai_api_key="test-key"
            )


class TestAsyncContextManager:
    """Test async context manager functionality."""

    @patch('falkordb.FalkorDB')
    @pytest.mark.asyncio
    async def test_context_manager(self, mock_falkordb):
        """Test async context manager functionality."""
        mock_falkordb.return_value.ping.return_value = True
        
        async with AsyncQueryWeaverClient(
            falkordb_url="redis://localhost:6379/0",
            openai_api_key="test-key"
        ) as client:
            assert client is not None
            assert isinstance(client, AsyncQueryWeaverClient)

    @patch('falkordb.FalkorDB')
    @pytest.mark.asyncio
    async def test_manual_close(self, mock_falkordb):
        """Test manual client close."""
        mock_falkordb.return_value.ping.return_value = True
        
        client = AsyncQueryWeaverClient(
            falkordb_url="redis://localhost:6379/0",
            openai_api_key="test-key"
        )
        
        # Should not raise an exception
        await client.close()


class TestAsyncLoadDatabase:
    """Test async database loading functionality."""

    @patch('falkordb.FalkorDB')
    def setUp(self, mock_falkordb):
        """Set up test client."""
        mock_falkordb.return_value.ping.return_value = True
        self.client = AsyncQueryWeaverClient(
            falkordb_url="redis://localhost:6379/0",
            openai_api_key="test-key"
        )

    @pytest.mark.asyncio
    async def test_load_database_empty_name_raises_error(self):
        """Test that empty database name raises ValueError."""
        self.setUp()
        with pytest.raises(ValueError, match="Database name cannot be empty"):
            await self.client.load_database("", "postgresql://user:pass@host/db")

    @pytest.mark.asyncio
    async def test_load_database_empty_url_raises_error(self):
        """Test that empty database URL raises ValueError."""
        self.setUp()
        with pytest.raises(ValueError, match="Database URL cannot be empty"):
            await self.client.load_database("test", "")

    @pytest.mark.asyncio
    async def test_load_database_invalid_url_raises_error(self):
        """Test that invalid database URL raises ValueError."""
        self.setUp()
        with pytest.raises(ValueError, match="Unsupported database URL format"):
            await self.client.load_database("test", "invalid://url")

    @pytest.mark.asyncio
    async def test_load_database_success(self):
        """Test successful async database loading."""
        self.setUp()
        
        # Mock the async loader
        async def mock_loader(user_id, url):
            yield True, "Success"
        
        with patch('queryweaver.get_database_type_and_loader') as mock_get_loader:
            mock_loader_class = AsyncMock()
            mock_loader_class.load = mock_loader
            mock_get_loader.return_value = ('postgresql', mock_loader_class)
            
            result = await self.client.load_database("test", "postgresql://user:pass@host/db")
            assert result is True
            assert "test" in self.client._loaded_databases

    @pytest.mark.asyncio
    async def test_load_database_failure(self):
        """Test async database loading failure."""
        self.setUp()
        
        # Mock the async loader to fail
        async def mock_loader(user_id, url):
            yield False, "Connection failed"
        
        with patch('queryweaver.get_database_type_and_loader') as mock_get_loader:
            mock_loader_class = AsyncMock()
            mock_loader_class.load = mock_loader
            mock_get_loader.return_value = ('postgresql', mock_loader_class)
            
            with pytest.raises(RuntimeError, match="Failed to load database schema"):
                await self.client.load_database("test", "postgresql://user:pass@host/db")


class TestAsyncTextToSQL:
    """Test async SQL generation functionality."""

    @patch('falkordb.FalkorDB')
    def setUp(self, mock_falkordb):
        """Set up test client with loaded database."""
        mock_falkordb.return_value.ping.return_value = True
        self.client = AsyncQueryWeaverClient(
            falkordb_url="redis://localhost:6379/0",
            openai_api_key="test-key"
        )
        self.client._loaded_databases.add("test_db")

    @pytest.mark.asyncio
    async def test_text_to_sql_empty_query_raises_error(self):
        """Test that empty query raises ValueError."""
        self.setUp()
        with pytest.raises(ValueError, match="Query cannot be empty"):
            await self.client.text_to_sql("test_db", "")

    @pytest.mark.asyncio
    async def test_text_to_sql_database_not_loaded_raises_error(self):
        """Test that querying unloaded database raises ValueError."""
        self.setUp()
        with pytest.raises(ValueError, match="Database 'nonexistent' not loaded"):
            await self.client.text_to_sql("nonexistent", "show data")

    @pytest.mark.asyncio
    async def test_text_to_sql_success(self):
        """Test successful async SQL generation."""
        self.setUp()
        
        # Mock the query_database function
        async def mock_generator():
            yield json.dumps({"type": "sql_query", "data": "SELECT * FROM users"})
        
        with patch('api.core.text2sql.query_database') as mock_query_db:
            mock_query_db.return_value = mock_generator()
            
            result = await self.client.text_to_sql("test_db", "show all users")
            assert result == "SELECT * FROM users"

    @pytest.mark.asyncio
    async def test_text_to_sql_with_history_and_instructions(self):
        """Test async SQL generation with chat history and instructions."""
        self.setUp()
        
        async def mock_generator():
            yield json.dumps({"type": "sql_query", "data": "SELECT * FROM users WHERE age > 18"})
        
        with patch('api.core.text2sql.query_database') as mock_query_db:
            mock_query_db.return_value = mock_generator()
            
            result = await self.client.text_to_sql(
                database_name="test_db",
                query="filter by adult users",
                instructions="Use age > 18 for adults",
                chat_history=["show users"]
            )
            assert "SELECT" in result


class TestAsyncQuery:
    """Test async full query functionality."""

    @patch('falkordb.FalkorDB')
    def setUp(self, mock_falkordb):
        """Set up test client with loaded database."""
        mock_falkordb.return_value.ping.return_value = True
        self.client = AsyncQueryWeaverClient(
            falkordb_url="redis://localhost:6379/0",
            openai_api_key="test-key"
        )
        self.client._loaded_databases.add("test_db")

    @pytest.mark.asyncio
    async def test_query_success(self):
        """Test successful async query execution."""
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
            yield json.dumps({"type": "query_results", "results": [{"id": 1, "name": "John"}]})
            yield json.dumps({"type": "final_result"})
        
        with patch('api.core.text2sql.query_database') as mock_query_db:
            mock_query_db.return_value = mock_generator()
            
            result = await self.client.query("test_db", "show all users")
            assert result["sql_query"] == "SELECT * FROM users"
            assert result["analysis"]["explanation"] == "Retrieves all users"
            assert result["results"] == [{"id": 1, "name": "John"}]

    @pytest.mark.asyncio
    async def test_query_sql_only(self):
        """Test async query with execute_sql=False."""
        self.setUp()
        
        async def mock_generator():
            yield json.dumps({"type": "sql_query", "data": "SELECT COUNT(*) FROM orders"})
            yield json.dumps({"type": "final_result"})
        
        with patch('api.core.text2sql.query_database') as mock_query_db:
            mock_query_db.return_value = mock_generator()
            
            result = await self.client.query("test_db", "count orders", execute_sql=False)
            assert result["sql_query"] == "SELECT COUNT(*) FROM orders"
            assert result["results"] is None


class TestAsyncUtilityMethods:
    """Test async utility methods."""

    @patch('falkordb.FalkorDB')
    def setUp(self, mock_falkordb):
        """Set up test client."""
        mock_falkordb.return_value.ping.return_value = True
        self.client = AsyncQueryWeaverClient(
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

    @pytest.mark.asyncio
    async def test_get_database_schema_success(self):
        """Test successful async schema retrieval."""
        self.setUp()
        self.client._loaded_databases.add("test_db")
        
        mock_schema = {"tables": ["users", "orders"], "columns": {}}
        
        with patch('api.core.text2sql.get_schema') as mock_get_schema:
            mock_get_schema.return_value = mock_schema
            
            result = await self.client.get_database_schema("test_db")
            assert result["tables"] == ["users", "orders"]

    @pytest.mark.asyncio
    async def test_get_database_schema_not_loaded_raises_error(self):
        """Test schema retrieval for unloaded database raises ValueError."""
        self.setUp()
        with pytest.raises(ValueError, match="Database 'nonexistent' not loaded"):
            await self.client.get_database_schema("nonexistent")


class TestAsyncConvenienceFunction:
    """Test async convenience functions."""

    @patch('falkordb.FalkorDB')
    def test_create_async_client_function(self, mock_falkordb):
        """Test create_async_client convenience function."""
        mock_falkordb.return_value.ping.return_value = True
        
        client = create_async_client(
            falkordb_url="redis://localhost:6379/0",
            openai_api_key="test-key"
        )
        
        assert isinstance(client, AsyncQueryWeaverClient)
        assert client.falkordb_url == "redis://localhost:6379/0"


class TestAsyncConcurrency:
    """Test async concurrency features."""

    @patch('falkordb.FalkorDB')
    def setUp(self, mock_falkordb):
        """Set up test client."""
        mock_falkordb.return_value.ping.return_value = True
        self.client = AsyncQueryWeaverClient(
            falkordb_url="redis://localhost:6379/0",
            openai_api_key="test-key"
        )
        self.client._loaded_databases.add("test_db")

    @pytest.mark.asyncio
    async def test_concurrent_text_to_sql(self):
        """Test concurrent SQL generation."""
        self.setUp()
        
        # Mock query_database to return different SQL for each call
        call_count = 0
        async def mock_generator():
            nonlocal call_count
            call_count += 1
            yield json.dumps({"type": "sql_query", "data": f"SELECT * FROM table{call_count}"})
        
        with patch('api.core.text2sql.query_database') as mock_query_db:
            mock_query_db.return_value = mock_generator()
            
            # Process multiple queries concurrently
            queries = ["query 1", "query 2", "query 3"]
            tasks = [
                self.client.text_to_sql("test_db", query) 
                for query in queries
            ]
            
            results = await asyncio.gather(*tasks)
            
            # Should have gotten different results for each query
            assert len(results) == 3
            assert all("SELECT" in result for result in results)

    @pytest.mark.asyncio
    async def test_concurrent_database_loading(self):
        """Test concurrent database loading."""
        self.setUp()
        
        # Mock successful loading
        async def mock_loader(user_id, url):
            yield True, "Success"
        
        with patch('queryweaver.get_database_type_and_loader') as mock_get_loader:
            mock_loader_class = AsyncMock()
            mock_loader_class.load = mock_loader
            mock_get_loader.return_value = ('postgresql', mock_loader_class)
            
            # Load multiple databases concurrently
            tasks = [
                self.client.load_database(f"db{i}", f"postgresql://user:pass@host/db{i}")
                for i in range(1, 4)
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # All should succeed
            assert all(result is True for result in results)
            assert len(self.client._loaded_databases) == 4  # test_db + 3 new ones


if __name__ == "__main__":
    pytest.main([__file__])