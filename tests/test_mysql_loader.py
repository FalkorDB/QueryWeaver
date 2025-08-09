"""Tests for MySQL loader functionality."""

import pytest
from unittest.mock import patch, MagicMock
from api.loaders.mysql_loader import MySQLLoader


class TestMySQLLoader:
    """Test cases for MySQLLoader class."""

    def test_parse_mysql_url_valid(self):
        """Test parsing a valid MySQL URL."""
        url = "mysql://testuser:testpass@localhost:3306/testdb"
        result = MySQLLoader._parse_mysql_url(url)
        expected = {
            'host': 'localhost',
            'port': 3306,
            'user': 'testuser',
            'password': 'testpass',
            'database': 'testdb'
        }
        assert result == expected

    def test_parse_mysql_url_default_port(self):
        """Test parsing MySQL URL without port (should default to 3306)."""
        url = "mysql://testuser:testpass@localhost/testdb"
        result = MySQLLoader._parse_mysql_url(url)
        assert result['port'] == 3306
        assert result['host'] == 'localhost'

    def test_parse_mysql_url_no_password(self):
        """Test parsing MySQL URL without password."""
        url = "mysql://testuser@localhost:3306/testdb"
        result = MySQLLoader._parse_mysql_url(url)
        assert result['password'] == ""
        assert result['user'] == 'testuser'

    def test_parse_mysql_url_with_query_params(self):
        """Test parsing MySQL URL with query parameters."""
        url = "mysql://testuser:testpass@localhost:3306/testdb?charset=utf8"
        result = MySQLLoader._parse_mysql_url(url)
        assert result['database'] == 'testdb'  # Should strip query params

    def test_parse_mysql_url_invalid_format(self):
        """Test parsing invalid MySQL URL format."""
        with pytest.raises(ValueError, match="Invalid MySQL URL format"):
            MySQLLoader._parse_mysql_url("postgresql://user@host/db")

    def test_parse_mysql_url_missing_host(self):
        """Test parsing MySQL URL without host."""
        with pytest.raises(ValueError, match="MySQL URL must include username and host"):
            MySQLLoader._parse_mysql_url("mysql://")

    def test_parse_mysql_url_missing_database(self):
        """Test parsing MySQL URL without database."""
        with pytest.raises(ValueError, match="MySQL URL must include database name"):
            MySQLLoader._parse_mysql_url("mysql://user@host")

    def test_serialize_value(self):
        """Test value serialization for JSON compatibility."""
        from datetime import datetime, date, time
        from decimal import Decimal

        # Test datetime
        dt = datetime(2023, 1, 1, 12, 0, 0)
        assert MySQLLoader._serialize_value(dt) == "2023-01-01T12:00:00"

        # Test date
        d = date(2023, 1, 1)
        assert MySQLLoader._serialize_value(d) == "2023-01-01"

        # Test time
        t = time(12, 0, 0)
        assert MySQLLoader._serialize_value(t) == "12:00:00"

        # Test decimal
        dec = Decimal("123.45")
        assert MySQLLoader._serialize_value(dec) == 123.45

        # Test None
        assert MySQLLoader._serialize_value(None) is None

        # Test regular value
        assert MySQLLoader._serialize_value("test") == "test"

    def test_is_schema_modifying_query(self):
        """Test detection of schema-modifying queries."""
        # Schema-modifying queries
        assert MySQLLoader.is_schema_modifying_query("CREATE TABLE test (id INT)")[0] is True
        assert MySQLLoader.is_schema_modifying_query("DROP TABLE test")[0] is True
        assert MySQLLoader.is_schema_modifying_query("ALTER TABLE test ADD COLUMN name VARCHAR(50)")[0] is True
        assert MySQLLoader.is_schema_modifying_query("  CREATE INDEX idx_name ON test(name)")[0] is True

        # Non-schema-modifying queries
        assert MySQLLoader.is_schema_modifying_query("SELECT * FROM test")[0] is False
        assert MySQLLoader.is_schema_modifying_query("INSERT INTO test VALUES (1)")[0] is False
        assert MySQLLoader.is_schema_modifying_query("UPDATE test SET name = 'test'")[0] is False
        assert MySQLLoader.is_schema_modifying_query("DELETE FROM test WHERE id = 1")[0] is False

        # Edge cases
        assert MySQLLoader.is_schema_modifying_query("")[0] is False
        assert MySQLLoader.is_schema_modifying_query(None)[0] is False

    @patch('mysql.connector.connect')
    def test_connection_error(self, mock_connect):
        """Test handling of MySQL connection errors."""
        # Mock connection failure
        mock_connect.side_effect = Exception("Connection failed")
        
        success, message = MySQLLoader.load("test_prefix", "mysql://user:pass@host:3306/db")
        
        assert success is False
        assert "Error loading MySQL schema" in message

    @patch('mysql.connector.connect')
    @patch('api.loaders.mysql_loader.load_to_graph')
    def test_successful_load(self, mock_load_to_graph, mock_connect):
        """Test successful MySQL schema loading."""
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {'table_name': 'users', 'table_comment': 'User table'}
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        # Mock the extract methods to return minimal data
        with patch.object(MySQLLoader, 'extract_tables_info', return_value={'users': {'description': 'User table'}}):
            with patch.object(MySQLLoader, 'extract_relationships', return_value={}):
                success, message = MySQLLoader.load("test_prefix", "mysql://user:pass@localhost:3306/testdb")

        assert success is True
        assert "MySQL schema loaded successfully" in message
        mock_load_to_graph.assert_called_once()