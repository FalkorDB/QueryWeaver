"""Tests for Oracle loader functionality."""
# pylint: disable=protected-access

import asyncio
import datetime
import decimal
from unittest.mock import patch, MagicMock

import pytest

# Initialises the api package in the order that avoids the loader <-> api.core
# circular import, so this file also runs on its own.
import api.core.pipeline  # noqa: F401  pylint: disable=unused-import
from api.loaders.oracle_loader import OracleLoader


async def _consume_loader(loader_gen):
    """Consume an async generator loader and return the final result."""
    last_success, last_message = False, ""
    async for success, message in loader_gen:
        last_success, last_message = success, message
    return last_success, last_message


class TestOracleLoader:
    """Test cases for OracleLoader class."""

    def test_parse_oracle_url_valid(self):
        """Test parsing a valid Oracle URL."""
        url = "oracle://scott:tiger@dbhost:1521/ORCLPDB1"
        result = OracleLoader._parse_oracle_url(url)
        expected = {
            'user': 'scott',
            'password': 'tiger',
            'dsn': 'dbhost:1521/ORCLPDB1',
            'schema': 'SCOTT',
        }
        assert result == expected

    def test_parse_oracle_url_default_port(self):
        """Test parsing Oracle URL without port (should default to 1521)."""
        url = "oracle://scott:tiger@dbhost/ORCLPDB1"
        result = OracleLoader._parse_oracle_url(url)
        assert result['dsn'] == 'dbhost:1521/ORCLPDB1'

    def test_parse_oracle_url_no_password(self):
        """Test parsing Oracle URL without password."""
        url = "oracle://scott@dbhost:1521/ORCLPDB1"
        result = OracleLoader._parse_oracle_url(url)
        assert result['password'] == ""
        assert result['user'] == 'scott'

    def test_parse_oracle_url_explicit_schema(self):
        """An explicit ?schema= overrides the connecting user's own schema."""
        url = "oracle://scott:tiger@dbhost:1521/ORCLPDB1?schema=hr"
        result = OracleLoader._parse_oracle_url(url)
        # Unquoted Oracle identifiers are upper-case.
        assert result['schema'] == 'HR'

    def test_parse_oracle_url_schema_defaults_to_username_uppercased(self):
        """With no ?schema=, the schema defaults to the (upper-cased) username."""
        url = "oracle://scott:tiger@dbhost:1521/ORCLPDB1"
        result = OracleLoader._parse_oracle_url(url)
        assert result['schema'] == 'SCOTT'

    def test_parse_oracle_url_ssl_builds_tcps_dsn(self):
        """?ssl=true switches to an Easy Connect Plus tcps:// DSN (e.g. Autonomous Database)."""
        url = "oracle://admin:pw@adb.example.oraclecloud.com:1522/svc_high?ssl=true"
        result = OracleLoader._parse_oracle_url(url)
        assert result['dsn'] == (
            "tcps://adb.example.oraclecloud.com:1522/svc_high?ssl_server_dn_match=true"
        )

    def test_parse_oracle_url_ssl_false_keeps_plain_dsn(self):
        """Anything but a truthy ?ssl= keeps the plain host:port/service DSN."""
        url = "oracle://scott:tiger@dbhost:1521/ORCLPDB1?ssl=false"
        result = OracleLoader._parse_oracle_url(url)
        assert result['dsn'] == 'dbhost:1521/ORCLPDB1'

    def test_parse_oracle_url_ssl_and_schema_together(self):
        """?ssl= and ?schema= are independent and can be combined."""
        url = "oracle://admin:pw@dbhost:1522/svc?ssl=true&schema=sales"
        result = OracleLoader._parse_oracle_url(url)
        assert result['schema'] == 'SALES'
        assert result['dsn'].startswith('tcps://')

    def test_parse_oracle_url_password_with_colon(self):
        """Only the first ':' separates user from password."""
        url = "oracle://admin:pa:ss@dbhost:1521/svc"
        result = OracleLoader._parse_oracle_url(url)
        assert result['user'] == 'admin'
        assert result['password'] == 'pa:ss'

    def test_parse_oracle_url_decodes_percent_encoded_password(self):
        """Browsers' URL builder percent-encodes credentials; they must be decoded."""
        url = "oracle://scott:p%40ss%3Aword%2F1@dbhost:1521/svc"
        result = OracleLoader._parse_oracle_url(url)
        assert result['user'] == 'scott'
        assert result['password'] == 'p@ss:word/1'

    def test_extract_tables_info_excludes_recycle_bin(self):
        """Dropped tables (BIN$...) are not valid identifiers and must not be listed."""
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        OracleLoader.extract_tables_info(cursor, "ADMIN")
        executed_sql = cursor.execute.call_args[0][0]
        assert "NOT LIKE 'BIN$%'" in executed_sql

    def test_extract_columns_info_skips_sampling_lob_columns(self):
        """DISTINCT/ORDER BY on a LOB raises ORA-00932, so LOB columns are not sampled."""
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            ("BODY", "CLOB", "Y", None, None),
            ("ID", "NUMBER", "N", None, None),
        ]
        with patch.object(OracleLoader, '_primary_key_columns', return_value={"ID"}), \
                patch.object(OracleLoader, 'extract_foreign_keys', return_value=[]), \
                patch.object(OracleLoader, 'extract_sample_values_for_column',
                             return_value=["1"]) as sampler:
            columns = OracleLoader.extract_columns_info(cursor, "ADMIN", "NOTES")

        sampled = [call.args[2] for call in sampler.call_args_list]
        assert sampled == ["ID"]
        assert columns["BODY"]["sample_values"] == []
        assert columns["ID"]["key"] == "PRIMARY KEY"
        assert columns["ID"]["null"] == "NO"

    def test_parse_oracle_url_invalid_format(self):
        """Test parsing invalid Oracle URL format."""
        with pytest.raises(ValueError, match="Invalid Oracle URL format"):
            OracleLoader._parse_oracle_url("postgresql://user@host/db")

    def test_parse_oracle_url_missing_username(self):
        """Test parsing Oracle URL without a username."""
        with pytest.raises(ValueError, match="Oracle URL must include username"):
            OracleLoader._parse_oracle_url("oracle://dbhost:1521/ORCLPDB1")

    def test_parse_oracle_url_missing_service_name(self):
        """Test parsing Oracle URL without a service name."""
        with pytest.raises(ValueError, match="Oracle URL must include a service name"):
            OracleLoader._parse_oracle_url("oracle://scott:tiger@dbhost:1521")

    def test_serialize_value(self):
        """Test value serialization for JSON compatibility."""
        dt = datetime.datetime(2023, 1, 1, 12, 0, 0)
        assert OracleLoader._serialize_value(dt) == "2023-01-01T12:00:00"

        d = datetime.date(2023, 1, 1)
        assert OracleLoader._serialize_value(d) == "2023-01-01"

        t = datetime.time(12, 0, 0)
        assert OracleLoader._serialize_value(t) == "12:00:00"

        dec = decimal.Decimal("123.45")
        assert OracleLoader._serialize_value(dec) == 123.45

        assert OracleLoader._serialize_value(None) is None
        assert OracleLoader._serialize_value("test") == "test"

    def test_validate_identifier_rejects_injection_attempt(self):
        """Identifiers used in string-built SQL must reject non-Oracle charset."""
        with pytest.raises(ValueError, match="Invalid table name"):
            OracleLoader._validate_identifier('t" OR 1=1 --', "table name")

    def test_quote_identifier_escapes_embedded_quotes(self):
        """Embedded double quotes must be doubled, not stripped."""
        assert OracleLoader._quote_identifier('WEIRD"NAME') == '"WEIRD""NAME"'

    def test_is_schema_modifying_query(self):
        """Test detection of schema-modifying queries."""
        assert OracleLoader.is_schema_modifying_query("CREATE TABLE test (id NUMBER)")[0] is True
        assert OracleLoader.is_schema_modifying_query("DROP TABLE test")[0] is True
        assert OracleLoader.is_schema_modifying_query(
            "ALTER TABLE test ADD name VARCHAR2(50)")[0] is True
        assert OracleLoader.is_schema_modifying_query(
            "  CREATE INDEX idx_name ON test(name)")[0] is True

        assert OracleLoader.is_schema_modifying_query("SELECT * FROM test")[0] is False
        assert OracleLoader.is_schema_modifying_query("INSERT INTO test VALUES (1)")[0] is False
        assert OracleLoader.is_schema_modifying_query("UPDATE test SET name = 'test'")[0] is False
        assert OracleLoader.is_schema_modifying_query("DELETE FROM test WHERE id = 1")[0] is False

        assert OracleLoader.is_schema_modifying_query("")[0] is False

    @patch('oracledb.connect')
    def test_connection_error(self, mock_connect):
        """Test handling of Oracle connection errors."""
        mock_connect.side_effect = Exception("Connection failed")

        success, message = asyncio.run(
            _consume_loader(OracleLoader.load(
                "test_prefix", "oracle://scott:tiger@dbhost:1521/ORCLPDB1"
            ))
        )

        assert success is False
        assert "Failed to load Oracle database schema" in message

    @patch('oracledb.connect')
    @patch('api.loaders.oracle_loader.load_to_graph')
    def test_successful_load(self, mock_load_to_graph, mock_connect):
        """Test successful Oracle schema loading."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        with patch.object(OracleLoader, 'extract_tables_info',
                          return_value={'USERS': {'description': 'User table'}}):
            with patch.object(OracleLoader, 'extract_relationships', return_value={}):
                success, message = asyncio.run(_consume_loader(OracleLoader.load(
                    "test_prefix", "oracle://scott:tiger@dbhost:1521/ORCLPDB1"
                )))

        assert success is True
        assert "Oracle schema loaded successfully" in message
        mock_load_to_graph.assert_called_once()
