"""Timeout bounds applied when executing a user query.

Query execution runs in a worker thread so it cannot block the event loop, but
a thread blocked in a socket read cannot be cancelled from Python — so the only
thing bounding a slow query is a driver/server-side timeout. These tests pin
that the configured values actually reach the driver, which is easy to get
wrong: two of the three URL parsers discard or hardcode these keys, so a
``setdefault`` silently does nothing.
"""

from unittest.mock import MagicMock, patch

import pytest

import api.core  # noqa: F401  (import first: the loaders import via api.core)
from api.config import Config
from api.loaders.mysql_loader import MySQLLoader
from api.loaders.postgres_loader import PostgresLoader
from api.loaders.snowflake_loader import SnowflakeLoader

PG_URL = "postgresql://u:p@h:5432/db"


@pytest.mark.unit
def test_postgres_applies_statement_and_connect_timeouts():
    kwargs = PostgresLoader._execution_connect_kwargs(PG_URL)
    assert kwargs["connect_timeout"] == Config.DB_CONNECT_TIMEOUT
    assert f"statement_timeout={Config.DB_STATEMENT_TIMEOUT * 1000}" in kwargs["options"]


@pytest.mark.unit
def test_postgres_preserves_url_options():
    """A bare options= kwarg would drop a URL-supplied search_path."""
    kwargs = PostgresLoader._execution_connect_kwargs(
        f"{PG_URL}?options=-c%20search_path%3Dfoo"
    )
    assert "search_path=foo" in kwargs["options"]
    assert "statement_timeout" in kwargs["options"]


@pytest.mark.unit
def test_postgres_url_timeouts_win():
    """An explicit value in the URL is not overridden."""
    kwargs = PostgresLoader._execution_connect_kwargs(
        f"{PG_URL}?options=-c%20statement_timeout%3D1234"
    )
    assert kwargs["options"] == "-c statement_timeout=1234"

    kwargs = PostgresLoader._execution_connect_kwargs(f"{PG_URL}?connect_timeout=3")
    assert "connect_timeout" not in kwargs


@pytest.mark.unit
@patch("api.loaders.mysql_loader.pymysql.connect")
def test_mysql_applies_timeouts(mock_connect):
    cursor = MagicMock()
    cursor.description = None
    cursor.rowcount = 0
    mock_connect.return_value.cursor.return_value = cursor

    MySQLLoader.execute_sql_query("SELECT 1", "mysql://u:p@h:3306/db")

    params = mock_connect.call_args.kwargs
    assert params["connect_timeout"] == Config.DB_CONNECT_TIMEOUT
    assert params["read_timeout"] == Config.DB_STATEMENT_TIMEOUT
    assert params["write_timeout"] == Config.DB_STATEMENT_TIMEOUT


@pytest.mark.unit
@patch("api.loaders.snowflake_loader.snowflake.connector.connect")
def test_snowflake_overrides_parser_timeout_defaults(mock_connect):
    """The parser hardcodes login_timeout=30/network_timeout=60.

    A ``setdefault`` here would be a no-op, leaving the configured values
    unused — which is the bug this pins.
    """
    cursor = MagicMock()
    cursor.description = None
    cursor.rowcount = 0
    mock_connect.return_value.cursor.return_value = cursor

    SnowflakeLoader.execute_sql_query(
        "SELECT 1", "snowflake://u:p@acct/db/schema?warehouse=WH"
    )

    params = mock_connect.call_args.kwargs
    assert params["login_timeout"] == Config.DB_CONNECT_TIMEOUT
    assert params["network_timeout"] == Config.DB_STATEMENT_TIMEOUT
    assert (
        params["session_parameters"]["STATEMENT_TIMEOUT_IN_SECONDS"]
        == Config.DB_STATEMENT_TIMEOUT
    )
