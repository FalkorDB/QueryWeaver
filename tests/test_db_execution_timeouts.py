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

from api.config import Config
# Imported via api.core.pipeline: importing api.loaders.postgres_loader first
# hits a circular import (pipeline imports the loaders, the loaders import
# api.core). Going through pipeline initialises the package in the right order,
# which also makes the snowflake import below work.
from api.core.pipeline import MySQLLoader, PostgresLoader
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
def test_postgres_url_may_tighten_the_bounds():
    """A stricter URL value is honoured."""
    kwargs = PostgresLoader._execution_connect_kwargs(
        f"{PG_URL}?options=-c%20statement_timeout%3D1234"
    )
    assert kwargs["options"] == "-c statement_timeout=1234"

    kwargs = PostgresLoader._execution_connect_kwargs(f"{PG_URL}?connect_timeout=3")
    assert kwargs["connect_timeout"] == 3


@pytest.mark.unit
@pytest.mark.parametrize("statement_timeout", ["0", "999999999"])
def test_postgres_url_cannot_loosen_or_disable_statement_timeout(statement_timeout):
    """Configured values are maximums, not defaults.

    ``statement_timeout=0`` means "no limit" in libpq, so honouring it would
    let one query hold a shared worker thread indefinitely.
    """
    kwargs = PostgresLoader._execution_connect_kwargs(
        f"{PG_URL}?options=-c%20statement_timeout%3D{statement_timeout}"
    )
    # Exact equality: the URL directive is replaced, not appended alongside.
    assert kwargs["options"] == f"-c statement_timeout={Config.DB_STATEMENT_TIMEOUT * 1000}"


@pytest.mark.unit
@pytest.mark.parametrize("connect_timeout", ["0", "600"])
def test_postgres_url_cannot_loosen_or_disable_connect_timeout(connect_timeout):
    kwargs = PostgresLoader._execution_connect_kwargs(
        f"{PG_URL}?connect_timeout={connect_timeout}"
    )
    assert kwargs["connect_timeout"] == Config.DB_CONNECT_TIMEOUT


@pytest.mark.unit
def test_postgres_ignores_a_statement_timeout_lookalike():
    """Only a real ``-c statement_timeout=`` directive counts.

    A substring test would treat this option value as an existing timeout and
    silently skip the configured bound.
    """
    kwargs = PostgresLoader._execution_connect_kwargs(
        f"{PG_URL}?options=-c%20application_name%3Dstatement_timeout_probe"
    )
    assert "application_name=statement_timeout_probe" in kwargs["options"]
    assert f"-c statement_timeout={Config.DB_STATEMENT_TIMEOUT * 1000}" in kwargs["options"]


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


@pytest.mark.unit
@pytest.mark.parametrize("url_options,expected_ms,reason", [
    # libpq applies the last directive, so none may survive; the strictest
    # positive value wins and a disabling 0 is ignored entirely.
    ("-c%20statement_timeout%3D1000%20-c%20statement_timeout%3D0", 1000,
     "duplicate, last disables"),
    ("-c%20statement_timeout%3D0%20-c%20statement_timeout%3D1000", 1000,
     "duplicate, first disables"),
    ("-c%20STATEMENT_TIMEOUT%3D0%20-c%20statement_timeout%3D3000", 3000,
     "mixed case duplicate"),
    ("-c%20statement_timeout%3D2min", None, "looser unit value"),
    ("-c%20statement_timeout%3D0", None, "disabled"),
    ("-c%20statement_timeout%3D%20", None, "empty value"),
    ("-c%20statement_timeout%3D-5", None, "negative value"),
    ("-c%20statement_timeout%3D0s", None, "zero with a unit"),
])
def test_postgres_clamp_is_not_bypassable(url_options, expected_ms, reason):
    """Exactly one directive survives, never looser than the ceiling.

    ``expected_ms=None`` means the configured ceiling applies.
    """
    ceiling = Config.DB_STATEMENT_TIMEOUT * 1000
    kwargs = PostgresLoader._execution_connect_kwargs(f"{PG_URL}?options={url_options}")
    options = kwargs["options"]

    assert options.lower().count("statement_timeout") == 1, reason
    assert options == f"-c statement_timeout={expected_ms or ceiling}", reason


@pytest.mark.unit
@pytest.mark.parametrize("directive", [
    "-c%20statement_timeout",      # short form
    "-cstatement_timeout",         # short form, no space
    "--statement_timeout",         # long form
    "--statement-timeout",         # long form, hyphenated
    "--STATEMENT-TIMEOUT",         # long form, hyphenated, uppercase
])
def test_postgres_recognises_every_directive_form(directive):
    """PostgreSQL accepts ``-c name=value`` and ``--name=value``.

    A form we do not recognise stays in the options string, where it either
    overrides our bound or — since ours is appended last — silently loosens a
    stricter request.
    """
    ceiling = Config.DB_STATEMENT_TIMEOUT * 1000

    # A disabling value must never survive.
    disabled = PostgresLoader._execution_connect_kwargs(
        f"{PG_URL}?options={directive}%3D0"
    )["options"]
    assert disabled == f"-c statement_timeout={ceiling}", directive

    # A stricter value must be honoured, whichever form it arrives in.
    stricter = PostgresLoader._execution_connect_kwargs(
        f"{PG_URL}?options={directive}%3D5s"
    )["options"]
    assert stricter == "-c statement_timeout=5000", directive


@pytest.mark.unit
@pytest.mark.parametrize("value,expected_ms", [
    ("5s", 5_000),          # stricter than the 60s ceiling, so honoured
    ("5000", 5_000),        # bare numbers are milliseconds
    ("'5s'", 5_000),        # quoted
    ("500us", 1),           # sub-millisecond rounds up rather than truncating
    ("1min", 60_000),       # equal to the ceiling
    ("2min", None),         # looser, so clamped
])
def test_postgres_honours_stricter_units_and_case(value, expected_ms):
    """PostgreSQL accepts units, quotes and any case; all must be understood.

    Treating only lowercase bare digits as valid silently loosened a URL asking
    for ``5s`` to the configured 60s.
    """
    ceiling = Config.DB_STATEMENT_TIMEOUT * 1000
    quoted = value.replace("'", "%27").replace(" ", "%20")
    for name in ("statement_timeout", "STATEMENT_TIMEOUT", "Statement_Timeout"):
        kwargs = PostgresLoader._execution_connect_kwargs(
            f"{PG_URL}?options=-c%20{name}%3D{quoted}"
        )
        assert kwargs["options"] == f"-c statement_timeout={expected_ms or ceiling}", name


@pytest.mark.unit
def test_postgres_clamp_keeps_unrelated_options():
    """Stripping the timeout directives must not drop other settings."""
    kwargs = PostgresLoader._execution_connect_kwargs(
        f"{PG_URL}?options=-c%20search_path%3Dfoo%20-c%20statement_timeout%3D0"
    )
    assert "search_path=foo" in kwargs["options"]
    assert kwargs["options"].endswith(
        f"-c statement_timeout={Config.DB_STATEMENT_TIMEOUT * 1000}"
    )

