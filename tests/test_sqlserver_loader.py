"""Tests for the SQL Server loader.

These exercise the real introspection code paths against a fake pymssql
cursor rather than mocking the methods under test, so regressions such as
indexing a ``as_dict=True`` row positionally are actually caught.
"""
# pylint: disable=protected-access

import datetime
import decimal
import importlib
from unittest.mock import patch, MagicMock

import pytest

# ``api.core`` must be initialised before any loader module is imported.
# ``api.core.__init__`` eagerly pulls in the pipeline, which imports the
# loaders, so importing a loader first leaves ``graph_loader`` half-built.
# Done through ``importlib`` so the side effect reads as deliberate rather than
# as an unused import that a linter should strip.
importlib.import_module("api.core")

from api.config import Config  # noqa: E402  pylint: disable=wrong-import-position
from api.loaders.sqlserver_loader import (  # noqa: E402  pylint: disable=wrong-import-position
    SQLServerLoader,
    SQLServerQueryError,
    quote_ident,
    validate_ident,
)

pytestmark = pytest.mark.unit


class FakeCursor:
    """Minimal stand-in for a pymssql ``as_dict=True`` cursor.

    Rows are dicts keyed by column name only — matching pymssql's ``row2dict``,
    which strips the positional keys. Queries are recorded so tests can assert
    on the SQL and the bound parameters.
    """

    def __init__(self, results=None):
        # results: list of row-lists returned in order, one per execute()
        self._results = list(results or [])
        self.executed = []
        self._current = []
        self.description = [("col",)]
        self.rowcount = 0
        self.closed = False

    def execute(self, query, params=None):
        """Record the statement and pop the next canned result set."""
        self.executed.append((query, params))
        self._current = self._results.pop(0) if self._results else []

    def fetchall(self):
        """Return the result set for the most recent execute()."""
        return self._current

    def close(self):
        """Mark the cursor closed."""
        self.closed = True


class FakeConnection:
    """Minimal stand-in for a pymssql connection."""

    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False
        self.committed = False
        self.rolled_back = False

    def cursor(self, as_dict=False):  # pylint: disable=unused-argument
        """Return the pre-built fake cursor."""
        return self._cursor

    def commit(self):
        """Record the commit."""
        self.committed = True

    def rollback(self):
        """Record the rollback."""
        self.rolled_back = True

    def close(self):
        """Mark the connection closed."""
        self.closed = True


class TestQuoteIdent:
    """Bracket-quoting helper."""

    def test_plain_identifier(self):
        """A simple name is wrapped in brackets."""
        assert quote_ident("Orders") == "[Orders]"

    def test_identifier_with_special_chars(self):
        """Dashes and spaces need no escaping, only wrapping."""
        assert quote_ident("my-table name") == "[my-table name]"

    def test_closing_bracket_is_doubled(self):
        """A literal ``]`` must be doubled so it cannot close the delimiter."""
        assert quote_ident("my]table") == "[my]]table]"

    def test_injection_attempt_stays_contained(self):
        """An identifier trying to break out stays inside one delimiter."""
        quoted = quote_ident("x] FROM sys.tables; DROP TABLE users --")
        assert quoted.startswith("[") and quoted.endswith("]")
        # The only unescaped ']' is the final delimiter.
        assert quoted[1:-1].replace("]]", "") .count("]") == 0


class TestValidateIdent:
    """Allow-list validation applied before any identifier interpolation."""

    @pytest.mark.parametrize("name", [
        "Orders", "my-table name", "col_1", "tbl$", "#temp", "a.b", "x@y",
    ])
    def test_accepts_legitimate_names(self, name):
        """Characters that can legally appear in an object name pass through."""
        assert validate_ident(name) == name

    @pytest.mark.parametrize("name", [
        "x] FROM sys.tables; DROP TABLE users --",
        "my]table",
        "tbl'; DROP TABLE t --",
        'tbl"',
        "tbl;",
        "tbl\\x",
        "tbl\nDROP",
    ])
    def test_rejects_breakout_attempts(self, name):
        """Anything able to escape a bracket delimiter is refused."""
        with pytest.raises(ValueError):
            validate_ident(name)

    def test_rejects_empty(self):
        """An empty identifier is not a valid object name."""
        with pytest.raises(ValueError):
            validate_ident("")

    def test_rejects_over_long(self):
        """SQL Server object names cap at 128 characters."""
        with pytest.raises(ValueError):
            validate_ident("a" * 129)

    def test_error_names_the_identifier_type(self):
        """The message says which kind of identifier was rejected."""
        with pytest.raises(ValueError, match="schema name"):
            validate_ident("bad;name", "schema name")


class TestSampleQueryValidation:
    """The sample query refuses hostile identifiers outright."""

    @pytest.mark.parametrize("table,column", [
        ("dbo.x] FROM sys.tables --", "c"),
        ("dbo.T", "c] FROM sys.tables --"),
        ("bad;schema.T", "c"),
    ])
    def test_hostile_identifier_is_rejected(self, table, column):
        """Validation happens before the statement is built or executed."""
        cursor = FakeCursor([[]])
        with pytest.raises(ValueError):
            SQLServerLoader._execute_sample_query(cursor, table, column)
        assert cursor.executed == []

    @pytest.mark.parametrize("size", [0, -1, "5"])
    def test_invalid_sample_size_rejected(self, size):
        """``sample_size`` must be a positive integer."""
        cursor = FakeCursor([[]])
        with pytest.raises(ValueError):
            SQLServerLoader._execute_sample_query(cursor, "dbo.T", "c", sample_size=size)
        assert cursor.executed == []


class TestParseUrl:
    """URL parsing."""

    def test_valid_url(self):
        """Full URL yields all pymssql connection parameters."""
        url = "sqlserver://sa:Passw0rd@localhost:1433/testdb"
        assert SQLServerLoader._parse_sqlserver_url(url) == {
            "server": "localhost",
            "port": 1433,
            "user": "sa",
            "password": "Passw0rd",
            "database": "testdb",
        }

    def test_default_port(self):
        """Port defaults to 1433 when omitted."""
        url = "sqlserver://sa:Passw0rd@localhost/testdb"
        assert SQLServerLoader._parse_sqlserver_url(url)["port"] == 1433

    def test_percent_encoded_password(self):
        """Percent-encoded credentials are decoded."""
        url = "sqlserver://sa:p%40ss%2Fword@localhost/testdb"
        assert SQLServerLoader._parse_sqlserver_url(url)["password"] == "p@ss/word"

    def test_query_string_not_part_of_database(self):
        """Query parameters are not swallowed into the database name."""
        url = "sqlserver://sa:pw@localhost/testdb?schema=sales"
        assert SQLServerLoader._parse_sqlserver_url(url)["database"] == "testdb"

    def test_encrypt_true_requests_tls(self):
        """``?encrypt=true`` asks FreeTDS to require TLS."""
        url = "sqlserver://sa:pw@localhost/testdb?encrypt=true"
        assert SQLServerLoader._parse_sqlserver_url(url)["encryption"] == "require"

    def test_encryption_absent_by_default(self):
        """Driver defaults are preserved when ``encrypt`` is not given."""
        url = "sqlserver://sa:pw@localhost/testdb"
        assert "encryption" not in SQLServerLoader._parse_sqlserver_url(url)

    @pytest.mark.parametrize("url", [
        "mysql://sa:pw@localhost/testdb",
        "sqlserver://localhost/testdb",
        "sqlserver://sa:pw@localhost/",
    ])
    def test_invalid_urls(self, url):
        """Malformed URLs raise ValueError."""
        with pytest.raises(ValueError):
            SQLServerLoader._parse_sqlserver_url(url)

    def test_schema_defaults_to_dbo(self):
        """No schema parameter means ``dbo``."""
        assert SQLServerLoader.parse_schema_from_url(
            "sqlserver://sa:pw@localhost/testdb") == "dbo"

    def test_schema_from_url(self):
        """An explicit schema parameter is honoured."""
        assert SQLServerLoader.parse_schema_from_url(
            "sqlserver://sa:pw@localhost/testdb?schema=sales") == "sales"


class TestSampleQuery:
    """Sample-value extraction — the dict-cursor contract."""

    def test_reads_rows_by_column_name(self):
        """Rows are keyed by column name, never by position.

        Regression test: pymssql's ``as_dict=True`` cursor strips positional
        keys, so ``row[0]`` raised KeyError for every non-empty column.
        """
        cursor = FakeCursor([[{"status": "active"}, {"status": "closed"}]])
        values = SQLServerLoader._execute_sample_query(cursor, "dbo.Orders", "status")
        assert values == ["active", "closed"]

    def test_nulls_filtered_out(self):
        """NULL samples are dropped."""
        cursor = FakeCursor([[{"status": "active"}, {"status": None}]])
        assert SQLServerLoader._execute_sample_query(
            cursor, "dbo.Orders", "status") == ["active"]

    def test_query_is_schema_qualified_and_quoted(self):
        """Both schema and table are bracket-quoted separately."""
        cursor = FakeCursor([[]])
        SQLServerLoader._execute_sample_query(cursor, "sales.Orders", "status")
        query, _ = cursor.executed[0]
        assert "FROM [sales].[Orders]" in query
        assert "[status]" in query

    def test_bare_table_name_still_works(self):
        """An unqualified table name is quoted without a schema prefix."""
        cursor = FakeCursor([[]])
        SQLServerLoader._execute_sample_query(cursor, "Orders", "status")
        query, _ = cursor.executed[0]
        assert "FROM [Orders]" in query

    def test_sample_size_is_coerced_to_int(self):
        """``sample_size`` cannot smuggle SQL into the TOP clause."""
        cursor = FakeCursor([[]])
        SQLServerLoader._execute_sample_query(cursor, "dbo.T", "c", sample_size=5)
        query, _ = cursor.executed[0]
        assert "TOP 5" in query

    def test_extract_sample_values_stringifies(self):
        """The public wrapper converts values to strings."""
        cursor = FakeCursor([[{"n": 1}, {"n": 2}]])
        assert SQLServerLoader.extract_sample_values_for_column(
            cursor, "dbo.T", "n") == ["1", "2"]


class TestIntrospection:
    """Catalog introspection queries."""

    def test_tables_query_is_schema_scoped(self):
        """Table discovery binds the schema as a parameter."""
        cursor = FakeCursor([[]])
        SQLServerLoader.extract_tables_info(cursor, "sales")
        query, params = cursor.executed[0]
        assert params == ("sales",)
        assert "s.name = %s" in query
        assert "JOIN sys.schemas s" in query

    def test_columns_query_binds_schema_and_table(self):
        """Column introspection is scoped by schema *and* table."""
        cursor = FakeCursor([[]])
        SQLServerLoader.extract_columns_info(cursor, "sales", "Orders", "Sales")
        query, params = cursor.executed[0]
        assert params == ("sales", "Orders")
        assert "s.name = %s AND t.name = %s" in query

    def test_columns_info_mapping(self):
        """Catalog rows map onto the loader's column dict."""
        cursor = FakeCursor([
            [{
                "column_name": "id",
                "data_type": "int",
                "is_nullable": False,
                "column_default": None,
                "column_key": "PRI",
                "column_comment": "",
            }],
            [{"id": 1}],  # sample values query
        ])
        info = SQLServerLoader.extract_columns_info(cursor, "dbo", "Orders", "dbo")
        assert info["id"]["type"] == "int"
        assert info["id"]["null"] == "NO"
        assert info["id"]["key"] == "PRIMARY KEY"
        assert info["id"]["sample_values"] == ["1"]
        assert "(NOT NULL)" in info["id"]["description"]

    def test_columns_sample_query_is_schema_qualified(self):
        """Sample values are fetched from the correct schema."""
        cursor = FakeCursor([
            [{
                "column_name": "id",
                "data_type": "int",
                "is_nullable": True,
                "column_default": None,
                "column_key": "",
                "column_comment": "",
            }],
            [],
        ])
        SQLServerLoader.extract_columns_info(cursor, "sales", "Orders", "Sales")
        # The column query binds the URL schema; the sample query interpolates
        # the catalog-returned one.
        assert cursor.executed[0][1] == ("sales", "Orders")
        sample_query, _ = cursor.executed[1]
        assert "FROM [Sales].[Orders]" in sample_query

    def test_foreign_keys_mapping(self):
        """Foreign key rows map onto the loader's FK dicts."""
        cursor = FakeCursor([[{
            "constraint_name": "FK_Orders_Customers",
            "column_name": "customer_id",
            "referenced_table_name": "Customers",
            "referenced_schema_name": "dbo",
            "referenced_column_name": "id",
        }]])
        fks = SQLServerLoader.extract_foreign_keys(cursor, "dbo", "Orders")
        assert fks == [{
            "constraint_name": "FK_Orders_Customers",
            "column": "customer_id",
            "referenced_table": "Customers",
            "referenced_column": "id",
        }]
        _, params = cursor.executed[0]
        assert params == ("dbo", "Orders")

    def test_relationships_grouped_by_constraint(self):
        """Composite keys are grouped under one constraint name."""
        cursor = FakeCursor([[
            {
                "table_name": "Orders",
                "constraint_name": "FK_A",
                "column_name": "c1",
                "referenced_table_name": "Customers",
                "referenced_column_name": "id1",
            },
            {
                "table_name": "Orders",
                "constraint_name": "FK_A",
                "column_name": "c2",
                "referenced_table_name": "Customers",
                "referenced_column_name": "id2",
            },
        ]])
        rels = SQLServerLoader.extract_relationships(cursor, "dbo")
        assert list(rels) == ["FK_A"]
        assert len(rels["FK_A"]) == 2
        assert rels["FK_A"][0]["from"] == "Orders"
        assert rels["FK_A"][0]["to"] == "Customers"

    def test_relationships_restricted_to_schema(self):
        """Both sides of the FK are constrained to the loaded schema."""
        cursor = FakeCursor([[]])
        SQLServerLoader.extract_relationships(cursor, "sales")
        query, params = cursor.executed[0]
        assert params == ("sales", "sales")
        assert "ps.name = %s AND rs.name = %s" in query

    def test_tables_info_builds_entities(self):
        """A full table walk produces the expected entity structure."""
        cursor = FakeCursor([
            [{"table_name": "Orders", "schema_name": "dbo", "table_comment": "All orders"}],
            [{
                "column_name": "id",
                "data_type": "int",
                "is_nullable": False,
                "column_default": None,
                "column_key": "PRI",
                "column_comment": "",
            }],
            [{"id": 7}],
            [],  # foreign keys
        ])
        entities = SQLServerLoader.extract_tables_info(cursor, "dbo")
        assert list(entities) == ["Orders"]
        assert entities["Orders"]["description"] == "All orders"
        assert list(entities["Orders"]["columns"]) == ["id"]
        assert entities["Orders"]["foreign_keys"] == []

    def test_sample_query_uses_catalog_schema_not_url_schema(self):
        """Sample queries qualify with the schema echoed back by ``sys.schemas``.

        The catalog value comes from the server, so the connection URL string
        is never interpolated into a statement.
        """
        cursor = FakeCursor([
            [{"table_name": "Orders", "schema_name": "Sales", "table_comment": ""}],
            [{
                "column_name": "id",
                "data_type": "int",
                "is_nullable": False,
                "column_default": None,
                "column_key": "PRI",
                "column_comment": "",
            }],
            [{"id": 7}],
            [],  # foreign keys
        ])
        SQLServerLoader.extract_tables_info(cursor, "sales")
        sample_query = cursor.executed[2][0]
        assert "FROM [Sales].[Orders]" in sample_query


class TestSerialization:
    """Value serialization for JSON responses."""

    @pytest.mark.parametrize("value,expected", [
        (datetime.date(2024, 1, 2), "2024-01-02"),
        (datetime.datetime(2024, 1, 2, 3, 4, 5), "2024-01-02T03:04:05"),
        (datetime.time(3, 4, 5), "03:04:05"),
        (decimal.Decimal("1.5"), 1.5),
        (b"\x01\x02", "0102"),
        (None, None),
        ("plain", "plain"),
    ])
    def test_serialize_value(self, value, expected):
        """Non-JSON-native types are converted."""
        assert SQLServerLoader._serialize_value(value) == expected


class TestSchemaModifyingQuery:
    """DDL detection."""

    @pytest.mark.parametrize("query,expected_op", [
        ("CREATE TABLE t (id INT)", "CREATE"),
        ("ALTER TABLE t ADD c INT", "ALTER"),
        ("DROP TABLE t", "DROP"),
        ("TRUNCATE TABLE t", "TRUNCATE"),
    ])
    def test_detects_ddl(self, query, expected_op):
        """DDL statements are reported as schema-modifying."""
        modifying, op = SQLServerLoader.is_schema_modifying_query(query)
        assert modifying is True
        assert op == expected_op

    @pytest.mark.parametrize("query", [
        "SELECT * FROM t",
        "INSERT INTO t VALUES (1)",
        "",
        "   ",
    ])
    def test_ignores_non_ddl(self, query):
        """Reads and DML are not schema-modifying."""
        modifying, _ = SQLServerLoader.is_schema_modifying_query(query)
        assert modifying is False


class TestExecuteSqlQuery:
    """Query execution."""

    def test_select_returns_serialized_rows(self):
        """SELECT results are serialized for JSON transport."""
        cursor = FakeCursor([[{"id": 1, "when": datetime.date(2024, 1, 2)}]])
        conn = FakeConnection(cursor)
        with patch("pymssql.connect", return_value=conn):
            rows = SQLServerLoader.execute_sql_query(
                "SELECT 1", "sqlserver://sa:pw@localhost/testdb")
        assert rows == [{"id": 1, "when": "2024-01-02"}]
        assert conn.closed and cursor.closed

    def test_non_select_reports_affected_rows(self):
        """Write statements report the affected row count."""
        cursor = FakeCursor([[]])
        cursor.description = None
        cursor.rowcount = 3
        conn = FakeConnection(cursor)
        with patch("pymssql.connect", return_value=conn):
            rows = SQLServerLoader.execute_sql_query(
                "UPDATE t SET c = 1", "sqlserver://sa:pw@localhost/testdb")
        assert rows == [{"operation": "UPDATE", "affected_rows": 3, "status": "success"}]

    def test_error_rolls_back_and_closes(self):
        """A failing query rolls back and still releases the connection."""
        cursor = FakeCursor()
        cursor.execute = MagicMock(side_effect=ValueError("boom"))
        conn = FakeConnection(cursor)
        with patch("pymssql.connect", return_value=conn):
            with pytest.raises(SQLServerQueryError):
                SQLServerLoader.execute_sql_query(
                    "SELECT 1", "sqlserver://sa:pw@localhost/testdb")
        assert conn.rolled_back
        assert conn.closed and cursor.closed

    def test_connect_failure_does_not_raise_name_error(self):
        """Failing before connect() must not blow up in the error handler."""
        with patch("pymssql.connect", side_effect=ValueError("no route")):
            with pytest.raises(SQLServerQueryError):
                SQLServerLoader.execute_sql_query(
                    "SELECT 1", "sqlserver://sa:pw@localhost/testdb")


class TestLoad:
    """End-to-end load flow."""

    @pytest.mark.asyncio
    async def test_load_success_closes_connection(self):
        """A successful load reports table count and releases resources."""
        cursor = FakeCursor([
            [{"table_name": "Orders", "schema_name": "dbo", "table_comment": ""}],
            [],   # columns
            [],   # foreign keys
            [],   # relationships
        ])
        conn = FakeConnection(cursor)
        messages = []
        with patch("pymssql.connect", return_value=conn), \
             patch("api.loaders.sqlserver_loader.load_to_graph") as mock_load:
            async def _noop(*args, **kwargs):
                return None
            mock_load.side_effect = _noop
            async for success, message in SQLServerLoader.load(
                    "user1", "sqlserver://sa:pw@localhost/testdb"):
                messages.append((success, message))

        assert messages[-1][0] is True
        assert "Found 1 tables" in messages[-1][1]
        assert conn.closed and cursor.closed
        # graph name is prefix + database name
        assert mock_load.call_args[0][0] == "user1_testdb"

    @pytest.mark.asyncio
    async def test_load_uses_schema_from_url(self):
        """The schema parameter reaches the catalog queries."""
        cursor = FakeCursor([[], []])
        conn = FakeConnection(cursor)
        with patch("pymssql.connect", return_value=conn), \
             patch("api.loaders.sqlserver_loader.load_to_graph") as mock_load:
            async def _noop(*args, **kwargs):
                return None
            mock_load.side_effect = _noop
            async for _ in SQLServerLoader.load(
                    "user1", "sqlserver://sa:pw@localhost/testdb?schema=sales"):
                pass
        assert cursor.executed[0][1] == ("sales",)

    @pytest.mark.asyncio
    async def test_load_failure_closes_connection(self):
        """A mid-load failure still releases the connection."""
        cursor = FakeCursor()
        cursor.execute = MagicMock(side_effect=ValueError("boom"))
        conn = FakeConnection(cursor)
        results = []
        with patch("pymssql.connect", return_value=conn):
            async for success, message in SQLServerLoader.load(
                    "user1", "sqlserver://sa:pw@localhost/testdb"):
                results.append((success, message))

        assert results[-1][0] is False
        assert conn.closed and cursor.closed

    @pytest.mark.asyncio
    async def test_load_invalid_url_reports_failure(self):
        """A bad URL is reported, not raised."""
        results = []
        async for success, message in SQLServerLoader.load("user1", "mysql://x/y"):
            results.append((success, message))
        assert results == [(False, "Failed to load SQL Server database schema")]

    @pytest.mark.asyncio
    async def test_load_bounds_connect_and_query_time(self):
        """Schema loading caps how long a stalled server can pin a worker."""
        cursor = FakeCursor([[], []])
        conn = FakeConnection(cursor)
        with patch("pymssql.connect", return_value=conn) as mock_connect, \
             patch("api.loaders.sqlserver_loader.load_to_graph") as mock_load:
            async def _noop(*args, **kwargs):
                return None
            mock_load.side_effect = _noop
            async for _ in SQLServerLoader.load(
                    "user1", "sqlserver://sa:pw@localhost/testdb"):
                pass

        kwargs = mock_connect.call_args.kwargs
        assert kwargs["login_timeout"] == Config.DB_CONNECT_TIMEOUT
        assert kwargs["timeout"] == max(Config.DB_SCHEMA_TIMEOUT, Config.DB_STATEMENT_TIMEOUT)

    def test_execute_query_bounds_connect_and_query_time(self):
        """Query execution uses the same budget: pymssql timeouts are process-wide."""
        cursor = FakeCursor([[]])
        conn = FakeConnection(cursor)
        with patch("pymssql.connect", return_value=conn) as mock_connect:
            SQLServerLoader.execute_sql_query(
                "SELECT 1", "sqlserver://sa:pw@localhost/testdb")

        kwargs = mock_connect.call_args.kwargs
        assert kwargs["login_timeout"] == Config.DB_CONNECT_TIMEOUT
        assert kwargs["timeout"] == max(Config.DB_SCHEMA_TIMEOUT, Config.DB_STATEMENT_TIMEOUT)
