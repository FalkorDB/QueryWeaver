"""Unit tests for SQL identifier quoting utilities."""

import pytest

from api.sql_utils import SQLIdentifierQuoter, DatabaseSpecificQuoter

pytestmark = pytest.mark.unit


class TestSQLIdentifierQuoter:
    """Test cases for SQLIdentifierQuoter."""

    def test_needs_quoting_with_dash(self):
        """Test that identifiers with dashes need quoting."""
        assert SQLIdentifierQuoter.needs_quoting("table-name") is True
        assert SQLIdentifierQuoter.needs_quoting("my-table") is True
        assert SQLIdentifierQuoter.needs_quoting("order-items") is True

    def test_needs_quoting_without_special_chars(self):
        """Test that normal identifiers don't need quoting."""
        assert SQLIdentifierQuoter.needs_quoting("table_name") is False
        assert SQLIdentifierQuoter.needs_quoting("users") is False
        assert SQLIdentifierQuoter.needs_quoting("OrderItems") is False

    def test_needs_quoting_already_quoted(self):
        """Test that already quoted identifiers don't need quoting again.

        "Already quoted" is dialect-scoped: only the active dialect's delimiter
        counts, so a backtick pair is pre-quoted for MySQL but is ordinary data
        for PostgreSQL.
        """
        assert SQLIdentifierQuoter.needs_quoting('"table-name"') is False
        assert SQLIdentifierQuoter.needs_quoting('`table-name`', '`') is False
        assert SQLIdentifierQuoter.needs_quoting('`table-name`', '"') is True

    def test_needs_quoting_with_spaces(self):
        """Test that identifiers with spaces need quoting."""
        assert SQLIdentifierQuoter.needs_quoting("table name") is True

    def test_needs_quoting_sql_keywords(self):
        """Test that SQL keywords are not marked as needing quoting."""
        assert SQLIdentifierQuoter.needs_quoting("SELECT") is False
        assert SQLIdentifierQuoter.needs_quoting("FROM") is False
        assert SQLIdentifierQuoter.needs_quoting("WHERE") is False

    def test_quote_identifier(self):
        """Test quoting an identifier."""
        assert SQLIdentifierQuoter.quote_identifier("table-name") == '"table-name"'
        assert SQLIdentifierQuoter.quote_identifier("my-table", "`") == "`my-table`"

    def test_quote_identifier_no_double_quote(self):
        """Test that already quoted identifiers aren't double-quoted."""
        assert SQLIdentifierQuoter.quote_identifier('"table-name"') == '"table-name"'
        assert SQLIdentifierQuoter.quote_identifier('`table-name`', '`') == '`table-name`'

    def test_extract_table_names_from_query(self):
        """Test extracting table names from SQL queries."""
        query = "SELECT * FROM table-name WHERE id = 1"
        tables = SQLIdentifierQuoter.extract_table_names_from_query(query)
        assert "table-name" in tables

        query = "SELECT * FROM users JOIN order-items ON users.id = order-items.user_id"
        tables = SQLIdentifierQuoter.extract_table_names_from_query(query)
        assert "users" in tables
        assert "order-items" in tables

    def test_auto_quote_identifiers_simple(self):
        """Test auto-quoting a simple SELECT query."""
        query = "SELECT * FROM table-name"
        known_tables = {"table-name"}

        result, modified = SQLIdentifierQuoter.auto_quote_identifiers(
            query, known_tables, '"'
        )

        assert modified is True
        assert '"table-name"' in result
        assert "table-name" not in result.replace('"table-name"', "")

    def test_auto_quote_identifiers_with_join(self):
        """Test auto-quoting a query with JOINs."""
        query = "SELECT * FROM users JOIN order-items ON users.id = order-items.user_id"
        known_tables = {"users", "order-items"}

        result, modified = SQLIdentifierQuoter.auto_quote_identifiers(
            query, known_tables, '"'
        )

        assert modified is True
        assert '"order-items"' in result
        assert 'order-items.user_id' not in result  # Should be quoted

    def test_auto_quote_identifiers_no_modification_needed(self):
        """Test that queries without special chars aren't modified."""
        query = "SELECT * FROM users WHERE id = 1"
        known_tables = {"users"}

        result, modified = SQLIdentifierQuoter.auto_quote_identifiers(
            query, known_tables, '"'
        )

        assert modified is False
        assert result == query

    def test_auto_quote_identifiers_unknown_table(self):
        """Test that unknown tables aren't quoted."""
        query = "SELECT * FROM unknown-table"
        known_tables = {"users"}  # unknown-table is not in schema

        _result, modified = SQLIdentifierQuoter.auto_quote_identifiers(
            query, known_tables, '"'
        )

        # Should not modify since table is not in known_tables
        assert modified is False

    def test_auto_quote_identifiers_with_qualified_columns(self):
        """Test auto-quoting with qualified column names (table.column)."""
        query = "SELECT table-name.id FROM table-name"
        known_tables = {"table-name"}

        result, modified = SQLIdentifierQuoter.auto_quote_identifiers(
            query, known_tables, '"'
        )

        assert modified is True
        assert '"table-name".id' in result or '"table-name"."id"' in result

    def test_auto_quote_identifiers_mysql_backticks(self):
        """Test auto-quoting with MySQL backticks."""
        query = "SELECT * FROM order-items"
        known_tables = {"order-items"}

        result, modified = SQLIdentifierQuoter.auto_quote_identifiers(
            query, known_tables, '`'
        )

        assert modified is True
        assert '`order-items`' in result

    def test_auto_quote_identifiers_insert_query(self):
        """Test auto-quoting INSERT queries."""
        query = "INSERT INTO table-name (id, name) VALUES (1, 'test')"
        known_tables = {"table-name"}

        result, modified = SQLIdentifierQuoter.auto_quote_identifiers(
            query, known_tables, '"'
        )

        assert modified is True
        assert '"table-name"' in result

    def test_auto_quote_identifiers_update_query(self):
        """Test auto-quoting UPDATE queries."""
        query = "UPDATE table-name SET status = 'active' WHERE id = 1"
        known_tables = {"table-name"}

        result, modified = SQLIdentifierQuoter.auto_quote_identifiers(
            query, known_tables, '"'
        )

        assert modified is True
        assert '"table-name"' in result

    def test_auto_quote_identifiers_multiple_tables(self):
        """Test auto-quoting with multiple tables needing quotes."""
        query = """
        SELECT * FROM user-accounts 
        JOIN order-history ON user-accounts.id = order-history.user_id
        """
        known_tables = {"user-accounts", "order-history"}

        result, modified = SQLIdentifierQuoter.auto_quote_identifiers(
            query, known_tables, '"'
        )

        assert modified is True
        assert '"user-accounts"' in result
        assert '"order-history"' in result


class TestDatabaseSpecificQuoter:
    """Test cases for DatabaseSpecificQuoter."""

    def test_get_quote_char_mysql(self):
        """Test getting quote character for MySQL."""
        assert DatabaseSpecificQuoter.get_quote_char('mysql') == '`'
        assert DatabaseSpecificQuoter.get_quote_char('MySQL') == '`'
        assert DatabaseSpecificQuoter.get_quote_char('MYSQL') == '`'
        assert DatabaseSpecificQuoter.get_quote_char('mariadb') == '`'

    def test_get_quote_char_postgresql(self):
        """Test getting quote character for PostgreSQL."""
        assert DatabaseSpecificQuoter.get_quote_char('postgresql') == '"'
        assert DatabaseSpecificQuoter.get_quote_char('postgres') == '"'
        assert DatabaseSpecificQuoter.get_quote_char('PostgreSQL') == '"'

    def test_get_quote_char_default(self):
        """Test getting quote character for unknown database types."""
        assert DatabaseSpecificQuoter.get_quote_char('unknown') == '"'
        assert DatabaseSpecificQuoter.get_quote_char('') == '"'


class TestIntegrationScenarios:
    """Integration test scenarios for real-world use cases."""

    def test_complex_query_with_multiple_special_chars(self):
        """Test a complex query with multiple special character scenarios."""
        query = """
        SELECT 
            ua.user_id,
            ua.email,
            oh.order_date
        FROM user-accounts ua
        LEFT JOIN order-history oh ON ua.user_id = oh.user_id
        WHERE ua.status = 'active'
        ORDER BY oh.order_date DESC
        """
        known_tables = {"user-accounts", "order-history"}

        result, modified = SQLIdentifierQuoter.auto_quote_identifiers(
            query, known_tables, '"'
        )

        assert modified is True
        assert '"user-accounts"' in result
        assert '"order-history"' in result
        # Ensure aliases (ua, oh) are not quoted
        assert '"ua"' not in result
        assert '"oh"' not in result

    def test_real_world_user_comment_scenario(self):
        """Test the exact scenario from the user comment."""
        # User's scenario: table with dash needs quotes
        query = "select * from table-name"
        known_tables = {"table-name"}

        result, modified = SQLIdentifierQuoter.auto_quote_identifiers(
            query, known_tables, '"'
        )

        assert modified is True
        assert 'select * from "table-name"' in result.lower()


class TestSQLServerQuoting:
    """SQL Server bracket-quoting behaviour."""

    def test_get_quote_char_sqlserver(self):
        """SQL Server uses the opening bracket as its quote character."""
        assert DatabaseSpecificQuoter.get_quote_char('sqlserver') == '['
        assert DatabaseSpecificQuoter.get_quote_char('SQLServer') == '['
        assert DatabaseSpecificQuoter.get_quote_char('mssql') == '['

    def test_quote_identifier_brackets(self):
        """Identifiers are wrapped in a bracket pair."""
        assert SQLIdentifierQuoter.quote_identifier('my-table', '[') == '[my-table]'

    def test_quote_identifier_escapes_closing_bracket(self):
        """A literal ``]`` is doubled so it cannot terminate the delimiter."""
        assert SQLIdentifierQuoter.quote_identifier('my]table', '[') == '[my]]table]'

    def test_quote_identifier_no_double_quoting(self):
        """An already-bracketed identifier is left alone."""
        assert SQLIdentifierQuoter.quote_identifier('[my-table]', '[') == '[my-table]'

    def test_auto_quote_identifiers_sqlserver(self):
        """Table names with special characters get bracket-quoted."""
        result, modified = SQLIdentifierQuoter.auto_quote_identifiers(
            'SELECT * FROM user-accounts', {'user-accounts'}, '['
        )
        assert modified is True
        assert '[user-accounts]' in result

    def test_bracketed_name_still_quoted_for_postgres(self):
        """``[weird]`` is data on PostgreSQL, so it must still be quoted.

        Regression test: a dialect-agnostic bracket pair made this identifier
        look pre-quoted and it was emitted unquoted.
        """
        assert SQLIdentifierQuoter.needs_quoting('[weird]', '"') is True
        assert SQLIdentifierQuoter.quote_identifier('[weird]', '"') == '"[weird]"'

    def test_bracketed_name_treated_as_quoted_for_sqlserver(self):
        """The same identifier is already delimited on SQL Server."""
        assert SQLIdentifierQuoter.needs_quoting('[weird]', '[') is False
