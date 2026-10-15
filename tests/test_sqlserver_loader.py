"""Tests for the SQL Server loader.

These exercise the real introspection code paths against a fake pymssql
cursor rather than mocking the methods under test, so regressions such as
indexing a ``as_dict=True`` row positionally are actually caught.
"""
# pylint: disable=protected-access

import datetime
import decimal
import importlib
import re
import uuid
from unittest.mock import AsyncMock, patch, MagicMock

import pymssql
import pytest

# ``api.core`` must be initialised before any loader module is imported.
# ``api.core.__init__`` eagerly pulls in the pipeline, which imports the
# loaders, so importing a loader first leaves ``graph_loader`` half-built.
# Done through ``importlib`` so the side effect reads as deliberate rather than
# as an unused import that a linter should strip.
importlib.import_module("api.core")

from api.config import Config  # noqa: E402  pylint: disable=wrong-import-position
from api.core.errors import InvalidArgumentError  # noqa: E402  pylint: disable=wrong-import-position
from api.core.pipeline import get_database_type_and_loader  # noqa: E402  pylint: disable=wrong-import-position
from api.loaders.sqlserver_loader import (  # noqa: E402  pylint: disable=wrong-import-position
    SQLServerLoader,
    SQLServerQueryError,
    _build_column_description,
    entity_name,
    quote_ident,
    validate_catalog_ident,
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


class TestValidateCatalogIdent:
    """The one rule for any name bracket-quoted into a statement."""

    @pytest.mark.parametrize("name", [
        "Kunden_Ä", "לקוחות", "顧客", "Verkäufe", "销售", "my]table",
        "tbl'; DROP TABLE t --", "a.b", "sales-data",
    ])
    def test_accepts_names_the_server_accepts(self, name):
        """Non-ASCII names are ordinary; bracket-quoting is what makes them safe."""
        assert validate_catalog_ident(name) == name

    @pytest.mark.parametrize("name", ["tbl\nDROP", "tbl\x00", "tbl\x7f"])
    def test_rejects_control_characters(self, name):
        """Control characters have no business in an object name."""
        with pytest.raises(ValueError):
            validate_catalog_ident(name)

    def test_rejects_empty_and_over_long(self):
        """SQL Server object names are 1-128 characters."""
        with pytest.raises(ValueError):
            validate_catalog_ident("")
        with pytest.raises(ValueError):
            validate_catalog_ident("a" * 129)

    def test_error_names_the_identifier_type(self):
        """The message says which kind of identifier was rejected."""
        with pytest.raises(ValueError, match="schema name"):
            validate_catalog_ident("bad\nname", "schema name")


class TestEntityName:
    """How a table is named in the graph."""

    @pytest.mark.parametrize("schema", ["dbo", "DBO"])
    def test_dbo_tables_keep_their_bare_name(self, schema):
        assert entity_name(schema, "Orders") == "Orders"

    def test_other_schemas_are_qualified(self):
        """Unqualified SQL would resolve against the login's default schema."""
        assert entity_name("sales", "Orders") == "sales.Orders"

    @pytest.mark.parametrize("schema,table,expected", [
        ("sales.eu", "Orders", "[sales.eu].Orders"),
        ("sales", "weird.name", "sales.[weird.name]"),
        ("dbo", "weird.name", "[weird.name]"),
        ("a]b.c", "T", "[a]]b.c].T"),
    ])
    def test_a_dotted_part_is_bracketed(self, schema, table, expected):
        """``sales.eu.Orders`` would be read as database.schema.table."""
        assert entity_name(schema, table) == expected


class TestSampleQueryValidation:
    """The sample query contains hostile identifiers rather than trusting them."""

    @pytest.mark.parametrize("schema,table,column,quoted", [
        ("dbo", "x] FROM t --", "c", "[dbo].[x]] FROM t --]"),
        ("dbo", "T", "c] FROM sys.tables --", "[c]] FROM sys.tables --]"),
        ("bad;schema", "T", "c", "[bad;schema].[T]"),
    ])
    def test_hostile_identifier_stays_quoted(self, schema, table, column, quoted):
        """A catalog name is bracket-quoted with ``]`` doubled, never rejected.

        SQL Server permits these names, so refusing them would fail the whole
        schema load; quoting is what keeps them inert.
        """
        cursor = FakeCursor([[]])
        SQLServerLoader._execute_sample_query(cursor, table, column, schema=schema)
        query, _ = cursor.executed[0]
        assert quoted in query

    @pytest.mark.parametrize("size", [0, -1, "5"])
    def test_invalid_sample_size_rejected(self, size):
        """``sample_size`` must be a positive integer."""
        cursor = FakeCursor([[]])
        with pytest.raises(ValueError):
            SQLServerLoader._execute_sample_query(cursor, "T", "c", sample_size=size)
        assert cursor.executed == []

    @pytest.mark.parametrize("schema,table,expected", [
        ("sales.eu", "Orders", "FROM [sales.eu].[Orders]"),
        ("dbo", "weird.name", "FROM [dbo].[weird.name]"),
    ])
    def test_a_dot_in_either_name_is_sampled_not_refused(self, schema, table, expected):
        """Schema and table arrive separately, so no dot has to be split on."""
        cursor = FakeCursor([[]])
        SQLServerLoader._execute_sample_query(cursor, table, "c", schema=schema)
        assert expected in cursor.executed[0][0]


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
        "sqlserver://sa:pw@localhost/testdb/",
        "sqlserver://sa:pw@localhost/testdb/extra",
    ])
    def test_only_the_first_path_segment_names_the_database(self, url):
        """A trailing slash or extra segment does not leak into the name."""
        assert SQLServerLoader._parse_sqlserver_url(url)["database"] == "testdb"

    def test_explicit_port_zero_is_rejected(self):
        """Port 0 is an error, not a silent switch to 1433."""
        with pytest.raises(ValueError, match="port"):
            SQLServerLoader._parse_sqlserver_url("sqlserver://sa:pw@localhost:0/testdb")

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

    def test_schema_is_decoded_once(self):
        """``%2520`` is a literal ``%20``, not a space decoded twice."""
        assert SQLServerLoader.parse_schema_from_url(
            "sqlserver://sa:pw@localhost/testdb?schema=sa%2520les") == "sa%20les"

    @pytest.mark.parametrize("encoded,expected", [
        ("Verk%C3%A4ufe", "Verkäufe"),
        ("%E9%94%80%E5%94%AE", "销售"),
    ])
    def test_non_ascii_schema_is_accepted(self, encoded, expected):
        """The URL schema is only ever bound, so non-ASCII names are fine."""
        assert SQLServerLoader.parse_schema_from_url(
            f"sqlserver://sa:pw@localhost/testdb?schema={encoded}") == expected

    def test_control_character_in_schema_is_rejected(self):
        with pytest.raises(ValueError):
            SQLServerLoader.parse_schema_from_url(
                "sqlserver://sa:pw@localhost/testdb?schema=a%0Ab")


class TestSampleQuery:
    """Sample-value extraction — the dict-cursor contract."""

    def test_reads_rows_by_column_name(self):
        """Rows are keyed by column name, never by position.

        Regression test: pymssql's ``as_dict=True`` cursor strips positional
        keys, so ``row[0]`` raised KeyError for every non-empty column.
        """
        cursor = FakeCursor([[{"status": "active"}, {"status": "closed"}]])
        values = SQLServerLoader._execute_sample_query(cursor, "Orders", "status")
        assert values == ["active", "closed"]

    def test_nulls_filtered_out(self):
        """NULL samples are dropped."""
        cursor = FakeCursor([[{"status": "active"}, {"status": None}]])
        assert SQLServerLoader._execute_sample_query(
            cursor, "Orders", "status") == ["active"]

    def test_query_is_schema_qualified_and_quoted(self):
        """Both schema and table are bracket-quoted separately."""
        cursor = FakeCursor([[]])
        SQLServerLoader._execute_sample_query(cursor, "Orders", "status", schema="sales")
        query, _ = cursor.executed[0]
        assert "FROM [sales].[Orders]" in query

    def test_distinct_is_isolated_in_a_derived_table(self):
        """SQL Server rejects ``SELECT DISTINCT … ORDER BY NEWID()`` outright.

        Regression test for error 145, "ORDER BY items must appear in the select
        list if SELECT DISTINCT is specified", which failed every schema load on
        the first table with a column.
        """
        cursor = FakeCursor([[]])
        SQLServerLoader._execute_sample_query(cursor, "Orders", "status")
        query, _ = cursor.executed[0]
        assert re.search(r"SELECT\s+DISTINCT\s+TOP", query) is None
        assert ") AS sampled" in query
        assert query.index("AS sampled") < query.index("ORDER BY NEWID()")
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
        SQLServerLoader._execute_sample_query(cursor, "T", "c", sample_size=5)
        query, _ = cursor.executed[0]
        assert "TOP 5" in query

    def test_extract_sample_values_stringifies(self):
        """The public wrapper converts values to strings."""
        cursor = FakeCursor([[{"n": 1}, {"n": 2}]])
        assert SQLServerLoader.extract_sample_values_for_column(
            cursor, "T", "n") == ["1", "2"]

    def test_driver_objects_are_serialized_before_the_base_filter(self):
        """The base wrapper keeps a sample only if it is a str/int/float.

        Regression test: pymssql hands back ``uuid.UUID`` for
        ``uniqueidentifier``, so every GUID column described itself with no
        sample values at all. Caught by the integration suite, not by a fake
        cursor that had only ever been fed strings.
        """
        cursor = FakeCursor([[
            {"v": uuid.UUID("3f2504e0-4f89-11d3-9a0c-0305e82c3301")},
        ]])
        assert SQLServerLoader.extract_sample_values_for_column(
            cursor, "T", "v") == ["3f2504e0-4f89-11d3-9a0c-0305e82c3301"]

    @pytest.mark.parametrize("error", [
        pymssql.Error("DISTINCT is not defined for xml"),
        ValueError("Invalid table name"),
    ])
    def test_a_failed_sample_costs_only_that_column(self, error):
        """One non-comparable type or odd name must not fail the whole load."""
        cursor = FakeCursor([[]])
        cursor.execute = MagicMock(side_effect=error)
        assert SQLServerLoader.extract_sample_values_for_column(
            cursor, "T", "payload") == []


def _column_row(table="Orders", name="id", key="PRIMARY KEY", **overrides):
    """One row of the schema-wide column catalog query."""
    row = {
        "table_name": table,
        "column_name": name,
        "data_type": "int",
        "max_length": 4,
        "precision": 10,
        "scale": 0,
        "is_nullable": False,
        "column_default": None,
        "column_key": key,
        "column_comment": "",
    }
    row.update(overrides)
    return row


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

    def test_columns_are_fetched_once_for_the_whole_schema(self):
        """One column query per schema, not one per table."""
        cursor = FakeCursor([
            [{"table_name": t, "schema_name": "dbo", "table_comment": ""}
             for t in ("A", "B", "C")],
            [],
        ])
        SQLServerLoader.extract_tables_info(cursor, "dbo")
        column_queries = [q for q, _ in cursor.executed if "FROM sys.columns c" in q]
        assert len(column_queries) == 1
        assert cursor.executed[1][1] == ("dbo",)

    def test_columns_info_mapping(self):
        """Catalog rows map onto the loader's column dict, grouped by table."""
        cursor = FakeCursor([[_column_row(), _column_row(table="Lines", name="qty", key="NONE")]])
        info = SQLServerLoader.extract_columns_info(cursor, "dbo")
        assert list(info) == ["Orders", "Lines"]
        assert info["Orders"]["id"]["type"] == "int"
        assert info["Orders"]["id"]["null"] == "NO"
        assert info["Orders"]["id"]["key"] == "PRIMARY KEY"
        assert info["Orders"]["id"]["sample_values"] == []
        assert "(NOT NULL)" in info["Orders"]["id"]["description"]

    @pytest.mark.parametrize("overrides,expected", [
        ({"data_type": "nvarchar", "max_length": 100}, "nvarchar(50)"),
        ({"data_type": "nvarchar", "max_length": -1}, "nvarchar(max)"),
        ({"data_type": "varchar", "max_length": 25}, "varchar(25)"),
        ({"data_type": "decimal", "precision": 19, "scale": 4}, "decimal(19,4)"),
        ({"data_type": "datetime2", "scale": 7}, "datetime2(7)"),
        ({"data_type": "bit", "max_length": 1}, "bit"),
    ])
    def test_types_are_rendered_as_declared(self, overrides, expected):
        """Length, precision and scale are part of the type the LLM sees."""
        cursor = FakeCursor([[_column_row(**overrides)]])
        info = SQLServerLoader.extract_columns_info(cursor, "dbo")
        assert info["Orders"]["id"]["type"] == expected

    def test_alias_types_resolve_to_their_base_type(self):
        """``dbo.Name`` is reported as nvarchar, not as ``Name``."""
        cursor = FakeCursor([[]])
        SQLServerLoader.extract_columns_info(cursor, "dbo")
        query = cursor.executed[0][0]
        assert "tp.is_user_defined = 1 AND tp.is_assembly_type = 0" in query
        assert "bt.user_type_id = tp.system_type_id" in query

    def test_foreign_keys_mapping(self):
        """Foreign key rows map onto the loader's FK dicts."""
        cursor = FakeCursor([[{
            "schema_name": "dbo",
            "table_name": "Orders",
            "constraint_name": "FK_Orders_Customers",
            "column_name": "customer_id",
            "referenced_table_name": "Customers",
            "referenced_column_name": "id",
        }]])
        fks = SQLServerLoader.extract_foreign_keys(cursor, "dbo")
        assert SQLServerLoader.group_foreign_keys(fks) == {"Orders": [{
            "constraint_name": "FK_Orders_Customers",
            "column": "customer_id",
            "referenced_table": "Customers",
            "referenced_column": "id",
        }]}

    def test_foreign_keys_outside_dbo_use_qualified_names(self):
        """Both sides of a key match the qualified entity names."""
        cursor = FakeCursor([[{
            "schema_name": "sales",
            "table_name": "Orders",
            "constraint_name": "FK",
            "column_name": "customer_id",
            "referenced_table_name": "Customers",
            "referenced_column_name": "id",
        }]])
        fk = SQLServerLoader.extract_foreign_keys(cursor, "sales")[0]
        assert (fk["table"], fk["referenced_table"]) == ("sales.Orders", "sales.Customers")

    def test_foreign_keys_are_fetched_once_for_the_whole_schema(self):
        """One query for every key, with both sides pinned to the loaded schema."""
        cursor = FakeCursor([[]])
        SQLServerLoader.extract_foreign_keys(cursor, "sales")
        query, params = cursor.executed[0]
        assert len(cursor.executed) == 1
        assert params == ("sales", "sales")
        assert "ps.name = %s AND rs.name = %s" in query

    def test_relationships_grouped_by_constraint(self):
        """Composite keys are grouped under one constraint name."""
        rels = SQLServerLoader.build_relationships([
            {
                "table": "Orders",
                "constraint_name": "FK_A",
                "column": "c1",
                "referenced_table": "Customers",
                "referenced_column": "id1",
            },
            {
                "table": "Orders",
                "constraint_name": "FK_A",
                "column": "c2",
                "referenced_table": "Customers",
                "referenced_column": "id2",
            },
        ])
        assert list(rels) == ["FK_A"]
        assert len(rels["FK_A"]) == 2
        assert rels["FK_A"][0]["from"] == "Orders"
        assert rels["FK_A"][0]["to"] == "Customers"

    def test_entities_and_relationships_share_one_fk_query(self):
        """The per-table list and the relationship map come from the same rows."""
        fks = [{
            "table": "Orders",
            "constraint_name": "FK_A",
            "column": "customer_id",
            "referenced_table": "Customers",
            "referenced_column": "id",
        }]
        cursor = FakeCursor([
            [{"table_name": "Orders", "schema_name": "dbo", "table_comment": ""}],
            [],  # columns
        ])
        entities = SQLServerLoader.extract_tables_info(
            cursor, "dbo", SQLServerLoader.group_foreign_keys(fks)
        )
        assert entities["Orders"]["foreign_keys"][0]["referenced_table"] == "Customers"
        assert list(SQLServerLoader.build_relationships(fks)) == ["FK_A"]

    def test_tables_info_builds_entities(self):
        """A full table walk produces the expected entity structure."""
        cursor = FakeCursor([
            [{"table_name": "Orders", "schema_name": "dbo", "table_comment": "All orders"}],
            [_column_row()],
            [{"id": 7}],
        ])
        entities = SQLServerLoader.extract_tables_info(cursor, "dbo")
        assert list(entities) == ["Orders"]
        assert entities["Orders"]["description"] == "All orders"
        assert list(entities["Orders"]["columns"]) == ["id"]
        assert entities["Orders"]["columns"]["id"]["sample_values"] == ["7"]
        assert entities["Orders"]["foreign_keys"] == []

    def test_tables_outside_dbo_are_keyed_by_qualified_name(self):
        """So generated SQL names ``sales.Orders``, not whatever the login defaults to."""
        cursor = FakeCursor([
            [{"table_name": "Orders", "schema_name": "sales", "table_comment": ""}],
            [_column_row()],
            [],
        ])
        entities = SQLServerLoader.extract_tables_info(cursor, "sales")
        assert list(entities) == ["sales.Orders"]
        assert entities["sales.Orders"]["description"] == "Table: sales.Orders"

    def test_sample_query_uses_catalog_schema_not_url_schema(self):
        """Sample queries qualify with the schema echoed back by ``sys.schemas``.

        The catalog value comes from the server, so the connection URL string
        is never interpolated into a statement.
        """
        cursor = FakeCursor([
            [{"table_name": "Orders", "schema_name": "Sales", "table_comment": ""}],
            [_column_row()],
            [{"id": 7}],
        ])
        SQLServerLoader.extract_tables_info(cursor, "sales")
        sample_query = cursor.executed[2][0]
        assert "FROM [Sales].[Orders]" in sample_query

    def test_every_catalog_query_runs_before_any_sample(self):
        """Sampling cannot leave a catalog query to a connection it killed."""
        cursor = FakeCursor([
            [{"table_name": t, "schema_name": "dbo", "table_comment": ""} for t in ("A", "B")],
            [_column_row(table="A"), _column_row(table="B")],
            [], [],
        ])
        SQLServerLoader.extract_tables_info(cursor, "dbo")
        kinds = ["sample" if "NEWID()" in q else "catalog" for q, _ in cursor.executed]
        assert kinds == ["catalog", "catalog", "sample", "sample"]


class TestSamplingBudget:
    """Sampling is bounded as a whole, and stops on a dead connection."""

    @staticmethod
    def _cursor(tables=("A", "B")):
        return FakeCursor([
            [{"table_name": t, "schema_name": "dbo", "table_comment": ""} for t in tables],
            [_column_row(table=t) for t in tables],
        ])

    def test_a_passed_deadline_skips_the_remaining_samples(self):
        """The schema still loads; only the samples are dropped."""
        cursor = self._cursor()
        entities = SQLServerLoader.extract_tables_info(cursor, "dbo", deadline=0.0)
        assert not any("NEWID()" in q for q, _ in cursor.executed)
        assert set(entities) == {"A", "B"}

    def test_sampling_stops_mid_schema_when_the_deadline_passes(self):
        cursor = self._cursor()
        with patch("api.loaders.sqlserver_loader.time.monotonic", side_effect=[0.0, 99.0]):
            SQLServerLoader.extract_tables_info(cursor, "dbo", deadline=10.0)
        assert sum("NEWID()" in q for q, _ in cursor.executed) == 1

    def test_load_gives_introspection_a_wall_clock_deadline(self):
        """``_introspect_schema`` bounds the run by DB_SCHEMA_TIMEOUT."""
        cursor = FakeCursor([[], [], []])
        with patch("pymssql.connect", return_value=FakeConnection(cursor)), \
                patch.object(SQLServerLoader, "extract_tables_info",
                             wraps=SQLServerLoader.extract_tables_info) as tables, \
                patch("api.loaders.sqlserver_loader.time.monotonic", return_value=100.0):
            SQLServerLoader._introspect_schema(
                SQLServerLoader._parse_sqlserver_url("sqlserver://sa:pw@h/db"), "dbo")
        assert tables.call_args.kwargs["deadline"] == 100.0 + Config.DB_SCHEMA_TIMEOUT

    def test_a_dead_connection_stops_sampling(self):
        """A failed sample followed by a failed probe means the connection is gone."""
        cursor = self._cursor()
        real_execute = cursor.execute

        def execute(query, params=None):
            if "NEWID()" in query or "alive" in query:
                cursor.executed.append((query, params))
                raise pymssql.OperationalError("connection timed out")
            return real_execute(query, params)

        cursor.execute = execute
        entities = SQLServerLoader.extract_tables_info(cursor, "dbo")
        assert sum("NEWID()" in q for q, _ in cursor.executed) == 1
        assert set(entities) == {"A", "B"}

    def test_a_column_error_on_a_live_connection_costs_only_that_column(self):
        """``DISTINCT`` on xml fails, the probe succeeds, and sampling carries on."""
        cursor = self._cursor()
        real_execute = cursor.execute
        samples = []

        def execute(query, params=None):
            if "NEWID()" in query:
                samples.append(query)
                if len(samples) == 1:
                    raise pymssql.OperationalError("DISTINCT is not defined for xml")
            return real_execute(query, params)

        cursor.execute = execute
        SQLServerLoader.extract_tables_info(cursor, "dbo")
        assert len(samples) == 2


class TestSerialization:
    """Value serialization for JSON responses."""

    @pytest.mark.parametrize("value,expected", [
        (datetime.date(2024, 1, 2), "2024-01-02"),
        (datetime.datetime(2024, 1, 2, 3, 4, 5), "2024-01-02T03:04:05"),
        (datetime.time(3, 4, 5), "03:04:05"),
        (decimal.Decimal("1.5"), 1.5),
        (b"\x01\x02", "0102"),
        # pymssql decodes uniqueidentifier to uuid.UUID, which json.dumps rejects.
        (uuid.UUID("3f2504e0-4f89-11d3-9a0c-0305e82c3301"),
         "3f2504e0-4f89-11d3-9a0c-0305e82c3301"),
        (None, None),
        ("plain", "plain"),
    ])
    def test_serialize_value(self, value, expected):
        """Non-JSON-native types are converted."""
        assert SQLServerLoader._serialize_value(value) == expected


class TestColumnDescription:
    """The column description fed to the graph."""

    def test_includes_key_nullability_and_default(self):
        col = {"column_name": "status", "data_type": "varchar",
               "column_comment": None, "column_default": "('new')"}
        assert _build_column_description(col, "PRIMARY KEY", "NO") == (
            "Column status of type varchar (PRIMARY KEY) (NOT NULL) (Default: ('new'))")

    def test_comment_replaces_the_generated_text(self):
        col = {"column_name": "status", "data_type": "varchar",
               "column_comment": "Order status", "column_default": None}
        assert _build_column_description(col, "NONE", "YES") == "Order status"


class TestSchemaModifyingQuery:
    """DDL detection."""

    @pytest.mark.parametrize("query,expected_op", [
        ("CREATE TABLE t (id INT)", "CREATE"),
        ("ALTER TABLE t ADD c INT", "ALTER"),
        ("DROP TABLE t", "DROP"),
        ("TRUNCATE TABLE t", "TRUNCATE"),
        # No specific pattern covers these; the keyword alone still flags them.
        ("CREATE PROCEDURE p AS SELECT 1", "CREATE"),
        ("DROP TRIGGER tr", "DROP"),
        # Renames are a stored procedure call in T-SQL.
        ("EXEC sp_rename 'dbo.t', 't2'", "RENAME"),
        ("execute sys.sp_rename 't.c', 'c2', 'COLUMN'", "RENAME"),
        ("sp_rename 't', 't2'", "RENAME"),
        ("EXEC [dbo].[sp_rename] 't', 't2'", "RENAME"),
    ])
    def test_detects_ddl(self, query, expected_op):
        """DDL statements are reported as schema-modifying."""
        modifying, op = SQLServerLoader.is_schema_modifying_query(query)
        assert modifying is True
        assert op == expected_op

    @pytest.mark.parametrize("query", [
        "EXEC sp_renamed_report",
        "EXEC sp_help 't'",
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
        cursor = FakeCursor([[(1, datetime.date(2024, 1, 2))]])
        cursor.description = [("id",), ("when",)]
        conn = FakeConnection(cursor)
        with patch("pymssql.connect", return_value=conn):
            rows = SQLServerLoader.execute_sql_query(
                "SELECT 1", "sqlserver://sa:pw@localhost/testdb")
        assert rows == [{"id": 1, "when": "2024-01-02"}]
        assert conn.closed and cursor.closed

    def test_unnamed_columns_get_positional_names(self):
        """``SELECT COUNT(*)`` has no column name; as_dict=True used to raise on it."""
        cursor = FakeCursor([[(42, 7)]])
        cursor.description = [("",), (None,)]
        with patch("pymssql.connect", return_value=FakeConnection(cursor)):
            rows = SQLServerLoader.execute_sql_query(
                "SELECT COUNT(*), MAX(id) FROM orders", "sqlserver://sa:pw@localhost/testdb")
        assert rows == [{"column_1": 42, "column_2": 7}]

    def test_duplicate_column_names_keep_every_value(self):
        """``SELECT o.id, c.id`` must not collapse into one key."""
        cursor = FakeCursor([[(1, 2, 3)]])
        cursor.description = [("id",), ("id",), ("id",)]
        with patch("pymssql.connect", return_value=FakeConnection(cursor)):
            rows = SQLServerLoader.execute_sql_query(
                "SELECT o.id, c.id, x.id", "sqlserver://sa:pw@localhost/testdb")
        assert rows == [{"id": 1, "id_2": 2, "id_3": 3}]

    def test_queries_use_a_tuple_cursor(self):
        """``as_dict=True`` is what raises ColumnsWithoutNamesError."""
        conn = FakeConnection(FakeCursor([[]]))
        conn.cursor = MagicMock(return_value=conn._cursor)
        with patch("pymssql.connect", return_value=conn):
            SQLServerLoader.execute_sql_query("SELECT 1", "sqlserver://sa:pw@localhost/testdb")
        assert conn.cursor.call_args.kwargs.get("as_dict", False) is False

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
            [],   # foreign keys
            [{"table_name": "Orders", "schema_name": "dbo", "table_comment": ""}],
            [],   # columns
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
        assert cursor.executed[0][1] == ("sales", "sales")
        assert cursor.executed[1][1] == ("sales",)

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
        assert kwargs["timeout"] == Config.DB_STATEMENT_TIMEOUT

    def test_execute_query_bounds_connect_and_query_time(self):
        """Every connection gets the statement budget: pymssql timeouts are process-wide."""
        cursor = FakeCursor([[]])
        conn = FakeConnection(cursor)
        with patch("pymssql.connect", return_value=conn) as mock_connect:
            SQLServerLoader.execute_sql_query(
                "SELECT 1", "sqlserver://sa:pw@localhost/testdb")

        kwargs = mock_connect.call_args.kwargs
        assert kwargs["login_timeout"] == Config.DB_CONNECT_TIMEOUT
        assert kwargs["timeout"] == Config.DB_STATEMENT_TIMEOUT


class TestLoaderRouting:
    """`sqlserver://` URLs must resolve to this loader, and only with the extra."""

    def test_server_install_gets_the_loader(self):
        db_type, loader = get_database_type_and_loader(
            "sqlserver://sa:pw@localhost/testdb")
        assert (db_type, loader) == ("sqlserver", SQLServerLoader)

    def test_sdk_uses_the_loader_when_the_extra_is_installed(self):
        """With pymssql installed the SDK gets the loader, not an error."""
        db_type, loader = get_database_type_and_loader(
            "sqlserver://sa:pw@localhost/testdb", sdk_only=True)
        assert (db_type, loader) == ("sqlserver", SQLServerLoader)

    def test_sdk_without_the_extra_is_told_which_extra_to_add(self):
        """A clean error beats an ImportError on pymssql."""
        with patch.dict("sys.modules", {"api.loaders.sqlserver_loader": None}):
            with pytest.raises(InvalidArgumentError, match=r"\[server\] extra"):
                get_database_type_and_loader(
                    "sqlserver://sa:pw@localhost/testdb", sdk_only=True)

    def test_server_path_without_the_driver_keeps_the_import_error(self):
        """A server install missing pymssql is a broken deployment, not bad input."""
        with patch.dict("sys.modules", {"api.loaders.sqlserver_loader": None}):
            with pytest.raises(ImportError):
                get_database_type_and_loader("sqlserver://sa:pw@localhost/testdb")


class TestRefreshGraphSchema:
    """Reloading the graph after a DDL statement."""

    URL = "sqlserver://sa:pw@localhost/testdb"

    @staticmethod
    def _graph_and_db():
        graph = MagicMock()
        graph.delete = AsyncMock()
        db = MagicMock()
        db.select_graph.return_value = graph
        return graph, db

    @staticmethod
    def _patched(introspection=None, db=None):
        """Patch introspection, graph loading and the FalkorDB handle."""
        if introspection is None:
            introspection = AsyncMock(return_value=({"Orders": {}}, {}))
        load = AsyncMock()
        patches = [
            patch("api.loaders.sqlserver_loader.run_introspection", introspection),
            patch("api.loaders.sqlserver_loader.load_to_graph", load),
            patch("api.core.db_resolver.resolve_db", return_value=db),
        ]
        return patches, load

    async def _refresh(self, graph_id, url=URL, introspection=None):
        graph, db = self._graph_and_db()
        patches, load = self._patched(introspection, db)
        with patches[0], patches[1], patches[2]:
            result = await SQLServerLoader.refresh_graph_schema(graph_id, url, db=db)
        return result, graph, load

    @pytest.mark.asyncio
    async def test_reload_replaces_the_graph_and_reports_success(self):
        (ok, message), graph, load = await self._refresh("user1_testdb")
        graph.delete.assert_awaited_once()
        assert load.await_args.args[0] == "user1_testdb"
        assert ok is True
        assert "Found 1 tables" in message

    @pytest.mark.asyncio
    async def test_a_failed_introspection_leaves_the_graph_alone(self):
        """A network blip or login throttling must not cost the user their schema."""
        failing = AsyncMock(side_effect=pymssql.OperationalError("login timeout"))
        (ok, message), graph, load = await self._refresh("user1_testdb", introspection=failing)
        assert (ok, message) == (False, "Error refreshing graph schema")
        graph.delete.assert_not_awaited()
        load.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_introspection_runs_before_the_delete(self):
        order = []
        graph, db = self._graph_and_db()
        graph.delete = AsyncMock(side_effect=lambda: order.append("delete"))

        async def introspect(*_args):
            order.append("introspect")
            return {}, {}

        patches, _load = self._patched(introspect, db)
        with patches[0], patches[1], patches[2]:
            await SQLServerLoader.refresh_graph_schema("user1_testdb", self.URL, db=db)
        assert order == ["introspect", "delete"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("graph_id", ["testdb", "user1_otherdb", "_testdb"])
    async def test_a_graph_not_named_after_its_database_is_refused(self, graph_id):
        """Reloading it would replace the graph with one under a different name."""
        (ok, _message), graph, load = await self._refresh(graph_id)
        assert ok is False
        graph.delete.assert_not_awaited()
        load.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_underscored_database_name_keeps_the_whole_graph_id(self):
        """Regression test: splitting on ``_`` wrote ``user1_my_db`` to ``user1_my_my_db``."""
        (ok, _message), _graph, load = await self._refresh(
            "user1_my_db", url="sqlserver://sa:pw@localhost/my_db")
        assert ok is True
        assert load.await_args.args[0] == "user1_my_db"

    @pytest.mark.asyncio
    async def test_a_malformed_url_leaves_the_graph_alone(self):
        (ok, _message), graph, _load = await self._refresh(
            "user1_testdb", url="postgresql://sa:pw@localhost/testdb")
        assert ok is False
        graph.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_unreachable_graph_is_reported_not_raised(self):
        introspection = AsyncMock(return_value=({}, {}))
        with patch("api.loaders.sqlserver_loader.run_introspection", introspection), \
                patch("api.core.db_resolver.resolve_db", side_effect=ConnectionError("down")):
            ok, message = await SQLServerLoader.refresh_graph_schema("user1_testdb", self.URL)

        assert (ok, message) == (False, "Error refreshing graph schema")


class TestConnectionCleanupIsQuiet:
    """Cleanup runs on the error path, so it must not raise a second failure."""

    def test_close_swallows_driver_errors(self):
        cursor = MagicMock()
        cursor.close.side_effect = RuntimeError("already gone")
        conn = MagicMock()
        conn.close.side_effect = RuntimeError("already gone")

        SQLServerLoader._close_quietly(cursor, conn)  # must not raise

    def test_rollback_swallows_driver_errors(self):
        conn = MagicMock()
        conn.rollback.side_effect = RuntimeError("no transaction")

        SQLServerLoader._rollback_quietly(conn)  # must not raise


class TestUrlEdgeCases:
    """Malformed and opt-out variants of the connection URL."""

    @pytest.mark.parametrize("url,message", [
        ("sqlserver://sa:pw@/testdb", "must include a host"),
        ("sqlserver://sa:pw@localhost/", "must include database name"),
        ("sqlserver://localhost/testdb", "must include username"),
        ("mysql://sa:pw@localhost/testdb", "Invalid SQL Server URL format"),
    ])
    def test_malformed_urls_are_rejected(self, url, message):
        with pytest.raises(ValueError, match=message):
            SQLServerLoader._parse_sqlserver_url(url)

    @pytest.mark.parametrize("value,expected", [
        ("true", "require"), ("1", "require"), ("yes", "require"), ("require", "require"),
        ("false", "off"), ("0", "off"), ("no", "off"), ("off", "off"),
    ])
    def test_encryption_is_opt_in_both_ways(self, value, expected):
        params = SQLServerLoader._parse_sqlserver_url(
            f"sqlserver://sa:pw@localhost/testdb?encrypt={value}")
        assert params["encryption"] == expected

    def test_driver_defaults_are_left_alone_when_unspecified(self):
        params = SQLServerLoader._parse_sqlserver_url("sqlserver://sa:pw@localhost/testdb")
        assert "encryption" not in params

    @pytest.mark.parametrize("url", [None, 12345])
    def test_an_unparseable_url_falls_back_to_the_default_schema(self, url):
        # urlparse raises AttributeError/ValueError rather than returning empty.
        assert SQLServerLoader.parse_schema_from_url(url) == "dbo"


class TestDdlResultShape:
    """DDL reports no row count, because there is none to report."""

    def test_ddl_reports_the_operation_only(self):
        cursor = FakeCursor([[]])
        cursor.description = None
        conn = FakeConnection(cursor)

        with patch("pymssql.connect", return_value=conn):
            rows = SQLServerLoader.execute_sql_query(
                "CREATE TABLE t (id INT)", "sqlserver://sa:pw@localhost/testdb")

        assert rows == [{"operation": "CREATE", "status": "success"}]
        assert conn.committed


class TestDriverErrorsDuringLoad:
    """A pymssql failure is reported as a load failure, not raised."""

    @pytest.mark.asyncio
    async def test_driver_error_is_reported(self):
        import pymssql  # pylint: disable=import-outside-toplevel

        results = []
        with patch("pymssql.connect", side_effect=pymssql.OperationalError("refused")):
            async for success, message in SQLServerLoader.load(
                    "user1", "sqlserver://sa:pw@localhost/testdb"):
                results.append((success, message))

        assert results[-1] == (False, "Failed to connect to SQL Server database")

    @pytest.mark.asyncio
    async def test_catalog_query_error_is_not_reported_as_a_connect_failure(self):
        """A connection that succeeds but then fails a catalog query (e.g. no
        permission on ``sys.*``) says the schema could not be read."""
        import pymssql  # pylint: disable=import-outside-toplevel

        cursor = FakeCursor()
        cursor.execute = MagicMock(
            side_effect=pymssql.ProgrammingError("permission denied on sys.tables"))
        conn = FakeConnection(cursor)
        results = []
        with patch("pymssql.connect", return_value=conn):
            async for success, message in SQLServerLoader.load(
                    "user1", "sqlserver://sa:pw@localhost/testdb"):
                results.append((success, message))

        assert results[-1] == (False, "Failed to read SQL Server database schema")
        assert conn.closed and cursor.closed

    @pytest.mark.asyncio
    async def test_driver_error_during_a_query_is_wrapped(self):
        import pymssql  # pylint: disable=import-outside-toplevel

        cursor = FakeCursor()
        cursor.execute = MagicMock(side_effect=pymssql.OperationalError("deadlock"))
        conn = FakeConnection(cursor)

        with patch("pymssql.connect", return_value=conn):
            with pytest.raises(SQLServerQueryError):
                SQLServerLoader.execute_sql_query(
                    "SELECT 1", "sqlserver://sa:pw@localhost/testdb")

        assert conn.rolled_back
