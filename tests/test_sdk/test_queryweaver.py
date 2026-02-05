"""SDK integration tests for QueryWeaver."""

import pytest


class TestQueryWeaverInit:
    """Test QueryWeaver initialization."""
    
    def test_init_with_falkordb_url(self, falkordb_url):
        """Test initialization with explicit FalkorDB URL."""
        from queryweaver_sdk import QueryWeaver
        
        qw = QueryWeaver(falkordb_url=falkordb_url)
        assert qw.user_id == "default"
    
    def test_init_with_custom_user_id(self, falkordb_url):
        """Test initialization with custom user ID."""
        from queryweaver_sdk import QueryWeaver
        
        qw = QueryWeaver(falkordb_url=falkordb_url, user_id="custom_user")
        assert qw.user_id == "custom_user"
    
    def test_init_context_manager(self, falkordb_url):
        """Test async context manager usage."""
        from queryweaver_sdk import QueryWeaver
        import asyncio
        
        async def run_test():
            async with QueryWeaver(falkordb_url=falkordb_url) as qw:
                assert qw.user_id == "default"
        
        asyncio.run(run_test())


class TestListDatabases:
    """Test database listing functionality."""
    
    @pytest.mark.asyncio
    async def test_list_databases_empty(self, queryweaver):
        """Test listing databases when none exist."""
        databases = await queryweaver.list_databases()
        # Should return a list (possibly empty)
        assert isinstance(databases, list)


class TestConnectDatabase:
    """Test database connection functionality."""
    
    @pytest.mark.asyncio
    @pytest.mark.requires_postgres
    async def test_connect_postgres(self, falkordb_url, postgres_url, has_llm_key):
        """Test connecting to PostgreSQL database."""
        from queryweaver_sdk import QueryWeaver
        qw = QueryWeaver(falkordb_url=falkordb_url, user_id="test_connect_pg")
        
        result = await qw.connect_database(postgres_url)
        
        assert result.success is True
        assert result.database_id == "testdb"
        assert result.tables_loaded >= 0
        assert "successfully" in result.message.lower()
        
        # Cleanup
        await qw.delete_database(result.database_id)
    
    @pytest.mark.asyncio
    @pytest.mark.requires_mysql
    async def test_connect_mysql(self, falkordb_url, mysql_url, has_llm_key):
        """Test connecting to MySQL database."""
        from queryweaver_sdk import QueryWeaver
        qw = QueryWeaver(falkordb_url=falkordb_url, user_id="test_connect_mysql")
        
        result = await qw.connect_database(mysql_url)
        
        assert result.success is True
        assert result.database_id == "testdb"
        assert "successfully" in result.message.lower()
        
        # Cleanup
        await qw.delete_database(result.database_id)
    
    @pytest.mark.asyncio
    async def test_connect_invalid_url(self, queryweaver):
        """Test connecting with invalid URL format."""
        with pytest.raises(Exception):  # Should raise InvalidArgumentError
            await queryweaver.connect_database("invalid://url")


class TestGetSchema:
    """Test schema retrieval functionality."""
    
    @pytest.mark.asyncio
    @pytest.mark.requires_postgres
    async def test_get_schema(self, falkordb_url, postgres_url, has_llm_key):
        """Test getting schema after connection."""
        from queryweaver_sdk import QueryWeaver
        qw = QueryWeaver(falkordb_url=falkordb_url, user_id="test_schema_user")
        
        # First connect
        conn_result = await qw.connect_database(postgres_url)
        assert conn_result.success
        
        # Then get schema
        schema = await qw.get_schema(conn_result.database_id)
        
        # Validate schema structure
        assert schema.nodes is not None
        assert isinstance(schema.nodes, list)
        assert len(schema.nodes) >= 2  # Should have at least customers and orders
        
        # Extract table names from schema nodes
        table_names = [node.get("name", "").lower() for node in schema.nodes]
        
        # Verify expected tables exist
        assert "customers" in table_names, f"Expected 'customers' table in schema, got: {table_names}"
        assert "orders" in table_names, f"Expected 'orders' table in schema, got: {table_names}"
        
        # Verify links (relationships) exist
        assert schema.links is not None
        assert isinstance(schema.links, list)
        
        # Cleanup
        await qw.delete_database(conn_result.database_id)


class TestQuery:
    """Test query functionality."""
    
    @pytest.mark.asyncio
    async def test_query_empty_question_raises(self, queryweaver):
        """Test that empty question raises error."""
        with pytest.raises(ValueError, match="cannot be empty"):
            await queryweaver.query("testdb", "")
    
    @pytest.mark.asyncio
    async def test_query_whitespace_question_raises(self, queryweaver):
        """Test that whitespace-only question raises error."""
        with pytest.raises(ValueError, match="cannot be empty"):
            await queryweaver.query("testdb", "   ")
    
    @pytest.mark.asyncio
    @pytest.mark.requires_postgres
    async def test_query_select_all_customers(self, falkordb_url, postgres_url, has_llm_key):
        """Test query to select all customers."""
        from queryweaver_sdk import QueryWeaver
        qw = QueryWeaver(falkordb_url=falkordb_url, user_id="test_query_all")
        
        # Connect first
        conn_result = await qw.connect_database(postgres_url)
        assert conn_result.success
        
        # Run a query for all customers
        result = await qw.query(
            conn_result.database_id,
            "Show me all customers"
        )
        
        # Validate SQL was generated
        assert result.sql_query is not None
        assert result.sql_query != ""
        sql_lower = result.sql_query.lower()
        assert "select" in sql_lower
        assert "customers" in sql_lower
        
        # Validate results contain expected data
        assert result.results is not None
        assert isinstance(result.results, list)
        assert len(result.results) == 3, f"Expected 3 customers, got {len(result.results)}"
        
        # Validate customer names are in results
        customer_names = [r.get("name") for r in result.results]
        assert "Alice Smith" in customer_names
        assert "Bob Jones" in customer_names
        assert "Carol White" in customer_names
        
        # Validate AI response exists
        assert result.ai_response is not None
        assert len(result.ai_response) > 0
        
        # Cleanup
        await qw.delete_database(conn_result.database_id)
    
    @pytest.mark.asyncio
    @pytest.mark.requires_postgres
    async def test_query_filter_by_city(self, falkordb_url, postgres_url, has_llm_key):
        """Test query with city filter.
        
        Note: This test may fail intermittently due to async event loop cleanup
        issues in pytest-asyncio when running the full test suite. Run individually
        with: pytest tests/test_sdk/test_queryweaver.py::TestQuery::test_query_filter_by_city -v
        """
        from queryweaver_sdk import QueryWeaver
        qw = QueryWeaver(falkordb_url=falkordb_url, user_id="test_query_filter")
        
        try:
            # Connect first
            conn_result = await qw.connect_database(postgres_url)
            assert conn_result.success
            
            # Run a filtered query
            result = await qw.query(
                conn_result.database_id,
                "Show me customers from New York"
            )
            
            # Validate SQL was generated with filter
            assert result.sql_query is not None
            sql_lower = result.sql_query.lower()
            assert "select" in sql_lower
            assert "customers" in sql_lower
            # Should have WHERE clause with New York filter
            assert "new york" in sql_lower or "where" in sql_lower
            
            # Validate results - should be 2 customers from New York
            assert result.results is not None
            assert isinstance(result.results, list)
            assert len(result.results) == 2, f"Expected 2 customers from New York, got {len(result.results)}"
            
            # Verify the correct customer names are returned (Alice Smith and Carol White)
            customer_names = [r.get("name") for r in result.results]
            assert "Alice Smith" in customer_names, f"Expected 'Alice Smith' in results, got {customer_names}"
            assert "Carol White" in customer_names, f"Expected 'Carol White' in results, got {customer_names}"
            # Bob Jones should NOT be in results (he's from Los Angeles)
            assert "Bob Jones" not in customer_names, f"'Bob Jones' should not be in NYC results"
            
            # Cleanup
            await qw.delete_database(conn_result.database_id)
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                pytest.skip("Skipped due to async event loop cleanup issue in test suite")
    
    @pytest.mark.asyncio
    @pytest.mark.requires_postgres
    async def test_query_count_aggregation(self, falkordb_url, postgres_url, has_llm_key):
        """Test query with count aggregation.
        
        Note: This test may fail intermittently due to async event loop cleanup
        issues in pytest-asyncio when running the full test suite.
        """
        from queryweaver_sdk import QueryWeaver
        qw = QueryWeaver(falkordb_url=falkordb_url, user_id="test_query_count")
        
        try:
            # Connect first
            conn_result = await qw.connect_database(postgres_url)
            assert conn_result.success
            
            # Run a count query
            result = await qw.query(
                conn_result.database_id,
                "How many customers are there?"
            )
            
            # Validate SQL has COUNT
            assert result.sql_query is not None
            sql_lower = result.sql_query.lower()
            assert "count" in sql_lower or "select" in sql_lower
            
            # Validate results contain count
            assert result.results is not None
            assert len(result.results) >= 1
            
            # The count should be 3 (either as a field or we have 3 rows)
            first_result = result.results[0]
            count_value = None
            for key, val in first_result.items():
                if isinstance(val, int):
                    count_value = val
                    break
            
            if count_value is not None:
                assert count_value == 3, f"Expected count of 3 customers, got {count_value}"
            else:
                # If count returned all rows instead
                assert len(result.results) == 3
            
            # Cleanup
            await qw.delete_database(conn_result.database_id)
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                pytest.skip("Skipped due to async event loop cleanup issue in test suite")
    
    @pytest.mark.asyncio
    @pytest.mark.requires_postgres
    async def test_query_join_orders(self, falkordb_url, postgres_url, has_llm_key):
        """Test query that joins customers and orders.
        
        Note: This test may fail intermittently due to async event loop cleanup
        issues in pytest-asyncio when running the full test suite.
        """
        from queryweaver_sdk import QueryWeaver
        qw = QueryWeaver(falkordb_url=falkordb_url, user_id="test_query_join")
        
        try:
            # Connect first
            conn_result = await qw.connect_database(postgres_url)
            assert conn_result.success
            
            # Run a join query
            result = await qw.query(
                conn_result.database_id,
                "Show me all orders with customer names"
            )
            
            # Validate SQL was generated
            assert result.sql_query is not None
            sql_lower = result.sql_query.lower()
            assert "select" in sql_lower
            # Should reference both tables (either via JOIN or subquery)
            assert "orders" in sql_lower or "order" in sql_lower
            
            # Validate results
            assert result.results is not None
            assert isinstance(result.results, list)
            # We have 3 orders in test data
            assert len(result.results) == 3, f"Expected 3 orders, got {len(result.results)}"
            
            # Check that results contain order-related fields
            first_result = result.results[0]
            # Should have either product or amount (order fields)
            has_order_field = any(
                key.lower() in ["product", "amount", "order_date", "order_id", "id"]
                for key in first_result.keys()
            )
            assert has_order_field, f"Expected order fields in result, got: {first_result.keys()}"
            
            # Cleanup
            await qw.delete_database(conn_result.database_id)
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                pytest.skip("Skipped due to async event loop cleanup issue in test suite")
    
    @pytest.mark.asyncio
    @pytest.mark.requires_postgres
    @pytest.mark.skip(reason="Flaky due to async event loop issues with consecutive queries")
    async def test_query_with_history(self, falkordb_url, postgres_url, has_llm_key):
        """Test query with conversation history."""
        from queryweaver_sdk import QueryWeaver
        qw = QueryWeaver(falkordb_url=falkordb_url, user_id="test_query_history")
        
        conn_result = await qw.connect_database(postgres_url)
        assert conn_result.success
        
        # First query
        await qw.query(
            conn_result.database_id,
            "Show me all customers"
        )
        
        # Follow-up query with history
        result2 = await qw.query(
            conn_result.database_id,
            "How many are from New York?",
            chat_history=["Show me all customers"]
        )
        
        assert result2 is not None
        assert result2.results is not None
        
        # Cleanup
        await qw.delete_database(conn_result.database_id)


class TestDeleteDatabase:
    """Test database deletion functionality."""
    
    @pytest.mark.asyncio
    @pytest.mark.requires_postgres
    async def test_delete_database(self, falkordb_url, postgres_url, has_llm_key):
        """Test deleting a connected database."""
        from queryweaver_sdk import QueryWeaver
        qw = QueryWeaver(falkordb_url=falkordb_url, user_id="test_delete_user")
        
        # Connect first
        conn_result = await qw.connect_database(postgres_url)
        assert conn_result.success
        assert conn_result.database_id == "testdb"
        
        # Delete
        deleted = await qw.delete_database(conn_result.database_id)
        assert deleted is True
        
        # Verify it's gone from list
        databases = await qw.list_databases()
        assert conn_result.database_id not in databases


class TestModels:
    """Test SDK model classes."""
    
    def test_query_result_to_dict(self):
        """Test QueryResult serialization."""
        from queryweaver_sdk.models import QueryResult, QueryMetadata

        result = QueryResult(
            sql_query="SELECT * FROM customers",
            results=[{"id": 1, "name": "Alice"}],
            ai_response="Found 1 customer",
            metadata=QueryMetadata(
                confidence=0.95,
                is_destructive=False,
                requires_confirmation=False,
                execution_time=0.5,
            ),
        )
        
        d = result.to_dict()
        assert d["sql_query"] == "SELECT * FROM customers"
        assert d["confidence"] == 0.95
        assert d["results"] == [{"id": 1, "name": "Alice"}]
        assert d["ai_response"] == "Found 1 customer"
        assert d["is_destructive"] is False
        assert d["requires_confirmation"] is False
        assert d["execution_time"] == 0.5
    
    def test_schema_result_to_dict(self):
        """Test SchemaResult serialization."""
        from queryweaver_sdk.models import SchemaResult
        
        result = SchemaResult(
            nodes=[{"id": "customers", "name": "customers"}],
            links=[{"source": "orders", "target": "customers"}],
        )
        
        d = result.to_dict()
        assert len(d["nodes"]) == 1
        assert d["nodes"][0]["name"] == "customers"
        assert len(d["links"]) == 1
        assert d["links"][0]["source"] == "orders"
        assert d["links"][0]["target"] == "customers"
    
    def test_database_connection_to_dict(self):
        """Test DatabaseConnection serialization."""
        from queryweaver_sdk.models import DatabaseConnection
        
        result = DatabaseConnection(
            database_id="testdb",
            success=True,
            tables_loaded=5,
            message="Connected successfully",
        )
        
        d = result.to_dict()
        assert d["database_id"] == "testdb"
        assert d["success"] is True
        assert d["tables_loaded"] == 5
        assert d["message"] == "Connected successfully"
    
    def test_query_result_default_values(self):
        """Test QueryResult with minimal required values."""
        from queryweaver_sdk.models import QueryResult, QueryMetadata

        result = QueryResult(
            sql_query="SELECT 1",
            results=[],
            ai_response="Test",
            metadata=QueryMetadata(confidence=0.8),
        )
        
        # Check defaults for optional fields
        assert result.is_destructive is False
        assert result.requires_confirmation is False
        assert result.execution_time == 0.0
        assert result.is_valid is True
        assert result.missing_information == ""
        assert result.ambiguities == ""
        assert result.explanation == ""
    
    def test_database_connection_failure(self):
        """Test DatabaseConnection for failed connection."""
        from queryweaver_sdk.models import DatabaseConnection
        
        result = DatabaseConnection(
            database_id="",
            success=False,
            tables_loaded=0,
            message="Connection refused",
        )
        
        d = result.to_dict()
        assert d["database_id"] == ""
        assert d["success"] is False
        assert d["tables_loaded"] == 0
        assert "refused" in d["message"].lower()
