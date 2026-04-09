"""Tests for Snowflake loader functionality."""
# pylint: disable=protected-access

import asyncio
import datetime
import decimal
from unittest.mock import patch, MagicMock

import pytest

from api.loaders.snowflake_loader import SnowflakeLoader


async def _consume_loader(loader_gen):
    """Consume an async generator loader and return the final result."""
    last_success, last_message = False, ""
    async for success, message in loader_gen:
        last_success, last_message = success, message
    return last_success, last_message


class TestSnowflakeLoader:
    """Test cases for SnowflakeLoader class."""

    def test_parse_snowflake_url_valid(self):
        """Test parsing a valid Snowflake URL."""
        url = (
            "snowflake://testuser:testpass@myaccount/testdb/testschema"
            "?warehouse=COMPUTE_WH"
        )
        result = SnowflakeLoader._parse_snowflake_url(url)
        expected = {
            'user': 'testuser',
            'password': 'testpass',
            'account': 'myaccount',
            'database': 'testdb',
            'schema': 'testschema',
            'warehouse': 'COMPUTE_WH',
            'login_timeout': 30,
            'network_timeout': 60,
        }
        assert result == expected

    def test_parse_snowflake_url_default_schema(self):
        """Test parsing Snowflake URL without schema (should default to PUBLIC)."""
        url = (
            "snowflake://testuser:testpass@myaccount/testdb"
            "?warehouse=COMPUTE_WH"
        )
        result = SnowflakeLoader._parse_snowflake_url(url)
        assert result['schema'] == 'PUBLIC'
        assert result['database'] == 'testdb'

    def test_parse_snowflake_url_default_warehouse(self):
        """Test parsing Snowflake URL without warehouse (default: COMPUTE_WH)."""
        url = (
            "snowflake://testuser:testpass@myaccount/testdb/testschema"
        )
        result = SnowflakeLoader._parse_snowflake_url(url)
        assert result['warehouse'] == 'COMPUTE_WH'

    def test_parse_snowflake_url_no_password(self):
        """Test parsing Snowflake URL without password."""
        url = (
            "snowflake://testuser@myaccount/testdb/testschema"
            "?warehouse=COMPUTE_WH"
        )
        result = SnowflakeLoader._parse_snowflake_url(url)
        assert result['password'] == ""
        assert result['user'] == 'testuser'

    def test_parse_snowflake_url_invalid_format(self):
        """Test parsing invalid Snowflake URL format."""
        with pytest.raises(ValueError, match="Invalid Snowflake URL format"):
            SnowflakeLoader._parse_snowflake_url("postgresql://user@host/db")

    def test_parse_snowflake_url_missing_username(self):
        """Test parsing Snowflake URL without username."""
        with pytest.raises(
            ValueError, match="Snowflake URL must include username"
        ):
            SnowflakeLoader._parse_snowflake_url(
                "snowflake://@myaccount/testdb"
            )

    def test_parse_snowflake_url_missing_account(self):
        """Test parsing Snowflake URL without account."""
        with pytest.raises(
            ValueError, match="Snowflake URL must include account"
        ):
            SnowflakeLoader._parse_snowflake_url(
                "snowflake://user:pass@/testdb"
            )

    def test_parse_snowflake_url_missing_database(self):
        """Test parsing Snowflake URL without database."""
        with pytest.raises(
            ValueError, match="Snowflake URL must include database name"
        ):
            SnowflakeLoader._parse_snowflake_url(
                "snowflake://user@myaccount"
            )

    def test_serialize_value(self):
        """Test value serialization for JSON compatibility."""
        # Test datetime
        dt = datetime.datetime(2023, 1, 1, 12, 0, 0)
        assert SnowflakeLoader._serialize_value(dt) == "2023-01-01T12:00:00"

        # Test date
        d = datetime.date(2023, 1, 1)
        assert SnowflakeLoader._serialize_value(d) == "2023-01-01"

        # Test time
        t = datetime.time(12, 0, 0)
        assert SnowflakeLoader._serialize_value(t) == "12:00:00"

        # Test decimal
        dec = decimal.Decimal("123.45")
        assert SnowflakeLoader._serialize_value(dec) == 123.45

        # Test None
        assert SnowflakeLoader._serialize_value(None) is None

        # Test regular value
        assert SnowflakeLoader._serialize_value("test") == "test"

    def test_is_schema_modifying_query(self):
        """Test detection of schema-modifying queries."""
        # Schema-modifying queries
        assert SnowflakeLoader.is_schema_modifying_query(
            "CREATE TABLE test (id INT)"
        )[0] is True
        assert SnowflakeLoader.is_schema_modifying_query(
            "ALTER TABLE test ADD COLUMN name VARCHAR"
        )[0] is True
        assert SnowflakeLoader.is_schema_modifying_query(
            "DROP TABLE test"
        )[0] is True
        assert SnowflakeLoader.is_schema_modifying_query(
            "CREATE INDEX idx ON test(id)"
        )[0] is True
        assert SnowflakeLoader.is_schema_modifying_query(
            "TRUNCATE TABLE test"
        )[0] is True
        assert SnowflakeLoader.is_schema_modifying_query(
            "CREATE VIEW v AS SELECT * FROM test"
        )[0] is True
        assert SnowflakeLoader.is_schema_modifying_query(
            "DROP VIEW v"
        )[0] is True

        # Non-schema-modifying queries
        assert SnowflakeLoader.is_schema_modifying_query(
            "SELECT * FROM test"
        )[0] is False
        assert SnowflakeLoader.is_schema_modifying_query(
            "INSERT INTO test VALUES (1, 'test')"
        )[0] is False
        assert SnowflakeLoader.is_schema_modifying_query(
            "UPDATE test SET name = 'new'"
        )[0] is False
        assert SnowflakeLoader.is_schema_modifying_query(
            "DELETE FROM test WHERE id = 1"
        )[0] is False

        # Empty query
        assert SnowflakeLoader.is_schema_modifying_query("")[0] is False
        assert SnowflakeLoader.is_schema_modifying_query("   ")[0] is False

    @patch('api.loaders.snowflake_loader.snowflake.connector.connect')
    @patch('api.loaders.snowflake_loader.load_to_graph')
    def test_load_success(self, mock_load_to_graph, mock_connect):
        """Test successful loading of Snowflake schema."""
        # Mock connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Mock table fetch — matches the new SHOW PRIMARY KEYS / SHOW IMPORTED KEYS flow:
        # extract_tables_info: tables query
        # extract_columns_info: columns query, SHOW PRIMARY KEYS, SHOW IMPORTED KEYS (cols),
        #                       sample values
        # extract_foreign_keys: SHOW IMPORTED KEYS (fks)
        # extract_relationships: tables query, SHOW IMPORTED KEYS (per table)
        mock_cursor.fetchall.side_effect = [
            # Tables (extract_tables_info)
            [{'TABLE_NAME': 'users', 'COMMENT': 'Users table'}],
            # Columns (extract_columns_info)
            [
                {
                    'COLUMN_NAME': 'id',
                    'DATA_TYPE': 'NUMBER',
                    'IS_NULLABLE': 'NO',
                    'COLUMN_DEFAULT': None,
                    'COMMENT': 'User ID'
                }
            ],
            # SHOW PRIMARY KEYS
            [{'column_name': 'id'}],
            # SHOW IMPORTED KEYS (for foreign key columns)
            [],
            # Sample values
            [{'id': 1}, {'id': 2}, {'id': 3}],
            # SHOW IMPORTED KEYS (extract_foreign_keys)
            [],
            # Tables list (extract_relationships)
            [{'TABLE_NAME': 'users'}],
            # SHOW IMPORTED KEYS (relationships for 'users')
            []
        ]

        # Mock load_to_graph to be async
        async def mock_load(*_args, **_kwargs):
            pass
        mock_load_to_graph.side_effect = mock_load

        # Run the loader
        url = "snowflake://user:pass@account/testdb/PUBLIC?warehouse=COMPUTE_WH"
        loader_gen = SnowflakeLoader.load("test_prefix", url)
        success, message = asyncio.run(_consume_loader(loader_gen))

        # Verify success
        assert success is True
        assert "Snowflake schema loaded successfully" in message
        assert "Found 1 tables" in message

    @patch('api.loaders.snowflake_loader.snowflake.connector.connect')
    def test_load_connection_error(self, mock_connect):
        """Test handling of connection errors."""
        # Mock connection error
        # pylint: disable=import-outside-toplevel
        import snowflake.connector
        mock_connect.side_effect = snowflake.connector.Error("Connection failed")

        # Run the loader
        url = "snowflake://user:pass@account/testdb/PUBLIC?warehouse=COMPUTE_WH"
        loader_gen = SnowflakeLoader.load("test_prefix", url)
        success, message = asyncio.run(_consume_loader(loader_gen))

        # Verify failure
        assert success is False
        assert "Snowflake error: Connection failed" in message

    @patch('api.loaders.snowflake_loader.snowflake.connector.connect')
    def test_execute_sql_query_select(self, mock_connect):
        """Test execution of SELECT query."""
        # Mock connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Mock SELECT query result
        mock_cursor.description = [('id',), ('name',)]
        mock_cursor.fetchall.return_value = [
            {'id': 1, 'name': 'test1'},
            {'id': 2, 'name': 'test2'}
        ]

        # Execute query
        url = "snowflake://user:pass@account/testdb/PUBLIC?warehouse=COMPUTE_WH"
        result = SnowflakeLoader.execute_sql_query("SELECT * FROM users", url)

        # Verify result
        assert len(result) == 2
        assert result[0]['id'] == 1
        assert result[0]['name'] == 'test1'

    @patch('api.loaders.snowflake_loader.snowflake.connector.connect')
    def test_execute_sql_query_insert(self, mock_connect):
        """Test execution of INSERT query."""
        # Mock connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Mock INSERT query result
        mock_cursor.description = None
        mock_cursor.rowcount = 1

        # Execute query
        url = "snowflake://user:pass@account/testdb/PUBLIC?warehouse=COMPUTE_WH"
        result = SnowflakeLoader.execute_sql_query("INSERT INTO users VALUES (1, 'test')", url)

        # Verify result
        assert len(result) == 1
        assert result[0]['operation'] == 'INSERT'
        assert result[0]['affected_rows'] == 1
        assert result[0]['status'] == 'success'

        # Verify the query was executed with correct SQL
        mock_cursor.execute.assert_called_once_with("INSERT INTO users VALUES (1, 'test')")

        # Verify transaction was committed and connection cleaned up
        mock_conn.commit.assert_called_once()
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()

    def test_execute_sample_query(self):
        """Test sample query execution for column values."""
        # Mock cursor (DictCursor returns dicts)
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {'test_column': 'value1'},
            {'test_column': 'value2'},
            {'test_column': 'value3'}
        ]

        # Execute sample query
        result = SnowflakeLoader._execute_sample_query(
            mock_cursor, 'test_table', 'test_column', 3
        )

        # Verify result
        assert len(result) == 3
        assert result == ['value1', 'value2', 'value3']

    def test_extract_sample_values_for_column(self):
        """Test extraction of sample values for a column."""
        # Mock cursor (DictCursor returns dicts)
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {'test_column': 1},
            {'test_column': 2},
            {'test_column': 3}
        ]

        # Extract sample values
        result = SnowflakeLoader.extract_sample_values_for_column(
            mock_cursor, 'test_table', 'test_column', 3
        )

        # Verify result
        assert len(result) == 3
        assert result == ['1', '2', '3']

    def test_validate_identifier_valid(self):
        """Test validation of valid identifiers."""
        # Valid identifiers should not raise
        SnowflakeLoader._validate_identifier("valid_table", "table")
        SnowflakeLoader._validate_identifier("TABLE123", "table")
        SnowflakeLoader._validate_identifier("column_name", "column")
        SnowflakeLoader._validate_identifier("DB_NAME", "database")
        SnowflakeLoader._validate_identifier("schema$name", "schema")

    def test_validate_identifier_invalid(self):
        """Test validation of invalid identifiers."""
        # Invalid characters
        with pytest.raises(ValueError, match="Invalid identifier"):
            SnowflakeLoader._validate_identifier("table'; DROP TABLE users--", "identifier")

        with pytest.raises(ValueError, match="Invalid identifier"):
            SnowflakeLoader._validate_identifier("table name", "identifier")

        with pytest.raises(ValueError, match="Invalid identifier"):
            SnowflakeLoader._validate_identifier("table-name", "identifier")

        with pytest.raises(ValueError, match="Invalid identifier"):
            SnowflakeLoader._validate_identifier("table.name", "identifier")

        # Too long
        with pytest.raises(ValueError, match="exceeds maximum length"):
            SnowflakeLoader._validate_identifier("a" * 256, "identifier")

    def test_quote_identifier(self):
        """Test identifier quoting."""
        # Simple identifier
        assert SnowflakeLoader._quote_identifier("table_name") == '"table_name"'

        # Identifier with double quotes
        assert SnowflakeLoader._quote_identifier('table"name') == '"table""name"'

        # Identifier with multiple double quotes
        assert SnowflakeLoader._quote_identifier('t"a"b"le') == '"t""a""b""le"'

    def test_execute_sample_query_with_invalid_identifiers(self):
        """Test sample query with invalid identifiers."""
        mock_cursor = MagicMock()

        # Invalid table name
        with pytest.raises(ValueError, match="Invalid table name"):
            SnowflakeLoader._execute_sample_query(
                mock_cursor, 'table; DROP TABLE users--', 'column', 3
            )

        # Invalid column name
        with pytest.raises(ValueError, match="Invalid column name"):
            SnowflakeLoader._execute_sample_query(
                mock_cursor, 'valid_table', 'col; DROP TABLE users--', 3
            )

        # Invalid sample size
        with pytest.raises(ValueError, match="sample_size must be a positive integer"):
            SnowflakeLoader._execute_sample_query(
                mock_cursor, 'valid_table', 'valid_column', -1
            )

        with pytest.raises(ValueError, match="sample_size must be a positive integer"):
            SnowflakeLoader._execute_sample_query(
                mock_cursor, 'valid_table', 'valid_column', "not an int"
            )
