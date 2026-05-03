"""SDK integration tests for QueryWeaver.

Most integration tests create QueryWeaver instances via ``async with`` so
the connection pool is closed before the test function returns. This
prevents stale Redis futures from leaking into subsequent tests and
surfacing as spurious "Event loop is closed" errors. The ``TestModels``
class is pure-unit (no FalkorDB/Postgres/LLM) and runs without fixtures.
"""

import pytest

from api.core.errors import InvalidArgumentError
from queryweaver_sdk import QueryWeaver
from queryweaver_sdk.models import (
    DatabaseConnection,
    QueryMetadata,
    QueryRequest,
    QueryResult,
    SchemaResult,
)


class TestQueryWeaverInit:
    """Construction and lifecycle."""

    def test_init_defaults(self, falkordb_url):
        qw = QueryWeaver(falkordb_url=falkordb_url)
        assert qw.user_id == "default"

    def test_init_with_custom_user_id(self, falkordb_url):
        qw = QueryWeaver(falkordb_url=falkordb_url, user_id="custom_user")
        assert qw.user_id == "custom_user"

    @pytest.mark.asyncio
    async def test_context_manager(self, falkordb_url):
        async with QueryWeaver(falkordb_url=falkordb_url) as qw:
            assert qw.user_id == "default"

    @pytest.mark.asyncio
    async def test_two_instances_isolated(self, falkordb_url):
        """Two SDK instances must not share state (no global mutation).

        This is the regression test for the ``api.extensions.db`` global
        that older SDK versions mutated on every __init__.
        """
        async with QueryWeaver(falkordb_url=falkordb_url, user_id="a") as qw1:
            async with QueryWeaver(falkordb_url=falkordb_url, user_id="b") as qw2:
                assert qw1._db is not qw2._db  # pylint: disable=protected-access
                assert qw1.user_id == "a"
                assert qw2.user_id == "b"


class TestListDatabases:
    """Database listing."""

    @pytest.mark.asyncio
    async def test_list_databases_returns_list(self, queryweaver):
        databases = await queryweaver.list_databases()
        assert isinstance(databases, list)


class TestConnectDatabase:
    """Database connection and schema loading."""

    @pytest.mark.asyncio
    @pytest.mark.requires_postgres
    async def test_connect_postgres(self, falkordb_url, postgres_url, has_llm_key):
        # connect_database loads embeddings via the LLM, so it actually requires
        # an LLM key — without one the load fails before the schema is persisted.
        async with QueryWeaver(falkordb_url=falkordb_url, user_id="test_connect_pg") as qw:
            result = await qw.connect_database(postgres_url)
            try:
                assert result.success is True
                assert result.database_id == "testdb"
                assert "successfully" in result.message.lower()
            finally:
                # Only clean up if the connect actually persisted a graph;
                # otherwise database_id is empty and delete_database rejects it.
                if result.success and result.database_id:
                    await qw.delete_database(result.database_id)

    @pytest.mark.asyncio
    @pytest.mark.requires_mysql
    async def test_connect_mysql(self, falkordb_url, mysql_url, has_llm_key):
        async with QueryWeaver(falkordb_url=falkordb_url, user_id="test_connect_mysql") as qw:
            result = await qw.connect_database(mysql_url)
            try:
                assert result.success is True
                assert result.database_id == "testdb"
                assert "successfully" in result.message.lower()
            finally:
                if result.success and result.database_id:
                    await qw.delete_database(result.database_id)

    @pytest.mark.asyncio
    async def test_connect_invalid_url(self, queryweaver):
        with pytest.raises(InvalidArgumentError):
            await queryweaver.connect_database("invalid://url")


class TestGetSchema:
    """Schema retrieval after connect."""

    @pytest.mark.asyncio
    @pytest.mark.requires_postgres
    async def test_get_schema(self, falkordb_url, postgres_url, has_llm_key):
        async with QueryWeaver(falkordb_url=falkordb_url, user_id="test_schema_user") as qw:
            conn_result = await qw.connect_database(postgres_url)
            try:
                assert conn_result.success

                schema = await qw.get_schema(conn_result.database_id)

                assert isinstance(schema.nodes, list)
                assert len(schema.nodes) >= 2

                table_names = [n.get("name", "").lower() for n in schema.nodes]
                assert "customers" in table_names
                assert "orders" in table_names
                assert isinstance(schema.links, list)
            finally:
                await qw.delete_database(conn_result.database_id)


class TestQuery:
    """End-to-end query paths."""

    @pytest.mark.asyncio
    async def test_query_empty_question_raises(self, queryweaver):
        with pytest.raises(ValueError, match="cannot be empty"):
            await queryweaver.query("testdb", "")

    @pytest.mark.asyncio
    async def test_query_whitespace_question_raises(self, queryweaver):
        with pytest.raises(ValueError, match="cannot be empty"):
            await queryweaver.query("testdb", "   ")

    @pytest.mark.asyncio
    @pytest.mark.requires_postgres
    async def test_query_select_all_customers(self, falkordb_url, postgres_url, has_llm_key):
        async with QueryWeaver(falkordb_url=falkordb_url, user_id="test_query_all") as qw:
            conn_result = await qw.connect_database(postgres_url)
            try:
                assert conn_result.success

                result = await qw.query(conn_result.database_id, "Show me all customers")

                sql_lower = (result.sql_query or "").lower()
                assert "select" in sql_lower
                assert "customers" in sql_lower
                assert len(result.results) == 3

                names = {r.get("name") for r in result.results}
                assert {"Alice Smith", "Bob Jones", "Carol White"} <= names
                assert result.ai_response
            finally:
                await qw.delete_database(conn_result.database_id)

    @pytest.mark.asyncio
    @pytest.mark.requires_postgres
    async def test_query_filter_by_city(self, falkordb_url, postgres_url, has_llm_key):
        async with QueryWeaver(falkordb_url=falkordb_url, user_id="test_query_filter") as qw:
            conn_result = await qw.connect_database(postgres_url)
            try:
                assert conn_result.success

                result = await qw.query(
                    conn_result.database_id, "Show me customers from New York",
                )

                sql_lower = (result.sql_query or "").lower()
                assert "select" in sql_lower
                assert "customers" in sql_lower
                assert "new york" in sql_lower or "where" in sql_lower

                assert len(result.results) == 2
                names = {r.get("name") for r in result.results}
                assert {"Alice Smith", "Carol White"} == names
                assert "Bob Jones" not in names
            finally:
                await qw.delete_database(conn_result.database_id)

    @pytest.mark.asyncio
    @pytest.mark.requires_postgres
    async def test_query_count_aggregation(self, falkordb_url, postgres_url, has_llm_key):
        async with QueryWeaver(falkordb_url=falkordb_url, user_id="test_query_count") as qw:
            conn_result = await qw.connect_database(postgres_url)
            try:
                assert conn_result.success

                result = await qw.query(
                    conn_result.database_id, "How many customers are there?",
                )

                sql_lower = (result.sql_query or "").lower()
                assert "select" in sql_lower
                assert len(result.results) >= 1

                first = result.results[0]
                count_value = next(
                    (v for v in first.values() if isinstance(v, int)), None,
                )
                if count_value is not None:
                    assert count_value == 3
                else:
                    assert len(result.results) == 3
            finally:
                await qw.delete_database(conn_result.database_id)

    @pytest.mark.asyncio
    @pytest.mark.requires_postgres
    async def test_query_join_orders(self, falkordb_url, postgres_url, has_llm_key):
        async with QueryWeaver(falkordb_url=falkordb_url, user_id="test_query_join") as qw:
            conn_result = await qw.connect_database(postgres_url)
            try:
                assert conn_result.success

                result = await qw.query(
                    conn_result.database_id, "Show me all orders with customer names",
                )

                sql_lower = (result.sql_query or "").lower()
                assert "select" in sql_lower
                assert "order" in sql_lower
                assert len(result.results) == 3

                first = result.results[0]
                assert any(
                    k.lower() in {"product", "amount", "order_date", "order_id", "id"}
                    for k in first.keys()
                )
            finally:
                await qw.delete_database(conn_result.database_id)

    @pytest.mark.asyncio
    @pytest.mark.requires_postgres
    async def test_query_with_history(self, falkordb_url, postgres_url, has_llm_key):
        """Chat history threads through via QueryRequest."""
        async with QueryWeaver(falkordb_url=falkordb_url, user_id="test_query_history") as qw:
            conn_result = await qw.connect_database(postgres_url)
            try:
                assert conn_result.success

                first = await qw.query(conn_result.database_id, "Show me all customers")
                assert first.sql_query

                follow_up = QueryRequest(
                    question="How many are from New York?",
                    chat_history=["Show me all customers"],
                    result_history=[first.ai_response or ""],
                )
                second = await qw.query(conn_result.database_id, follow_up)
                assert second is not None
                assert isinstance(second.results, list)
            finally:
                await qw.delete_database(conn_result.database_id)


class TestDeleteDatabase:
    """Database deletion."""

    @pytest.mark.asyncio
    @pytest.mark.requires_postgres
    async def test_delete_database(self, falkordb_url, postgres_url, has_llm_key):
        async with QueryWeaver(falkordb_url=falkordb_url, user_id="test_delete_user") as qw:
            conn_result = await qw.connect_database(postgres_url)
            assert conn_result.success
            assert conn_result.database_id == "testdb"

            deleted = await qw.delete_database(conn_result.database_id)
            assert deleted is True

            databases = await qw.list_databases()
            assert conn_result.database_id not in databases


@pytest.mark.unit
class TestModels:
    """Dataclass serialization / defaults — pure unit, no external services."""

    def test_query_result_to_dict(self):
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
        result = SchemaResult(
            nodes=[{"id": "customers", "name": "customers"}],
            links=[{"source": "orders", "target": "customers"}],
        )

        d = result.to_dict()
        assert d["nodes"][0]["name"] == "customers"
        assert d["links"][0]["source"] == "orders"
        assert d["links"][0]["target"] == "customers"

    def test_database_connection_to_dict(self):
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
        result = QueryResult(
            sql_query="SELECT 1",
            results=[],
            ai_response="Test",
            metadata=QueryMetadata(confidence=0.8),
        )

        assert result.is_destructive is False
        assert result.requires_confirmation is False
        assert result.execution_time == 0.0
        assert result.is_valid is True
        assert result.missing_information == ""
        assert result.ambiguities == ""
        assert result.explanation == ""

    def test_database_connection_failure(self):
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

    def test_query_request_custom_model_fields(self):
        """custom_api_key/custom_model are threaded through to agents."""
        req = QueryRequest(
            question="test",
            custom_api_key="sk-test-123",
            custom_model="openai/gpt-4.1",
        )
        assert req.custom_api_key == "sk-test-123"
        assert req.custom_model == "openai/gpt-4.1"
