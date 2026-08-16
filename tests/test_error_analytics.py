"""Tests for QueryWeaver error analytics."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request

from api import analytics

pytestmark = [pytest.mark.unit]


def test_safe_message_redacts_credentials():
    """Persisted messages must not contain common credential values."""
    error = RuntimeError(
        "password=hunter2 token: abc123 redis://default:secret@db.example:6379"
    )

    message = analytics._safe_message(error)  # pylint: disable=protected-access

    assert "hunter2" not in message
    assert "abc123" not in message
    assert "secret@" not in message


@pytest.mark.asyncio
async def test_report_error_writes_org_graph(monkeypatch):
    """Unhandled errors should be written with QueryWeaver attribution."""
    monkeypatch.setenv("FALKORDB_URL", "redis://analytics.example:6379")
    graph = AsyncMock()
    client = MagicMock()
    client.select_graph.return_value = graph
    pool = AsyncMock()
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/graphs/query",
        "headers": [],
        "query_string": b"",
        "scheme": "https",
        "server": ("queryweaver.example", 443),
    }
    request = Request(scope)
    request.state.user_email = "user@example.com"

    with (
        patch.object(analytics.BlockingConnectionPool, "from_url", return_value=pool),
        patch.object(analytics, "FalkorDB", return_value=client),
    ):
        result = await analytics.report_error(request, RuntimeError("sales demo failed"))

    assert result is True
    graph.query.assert_awaited_once()
    params = graph.query.await_args.args[1]
    assert params == {
        "type": "RuntimeError",
        "message": "sales demo failed",
        "endpoint": "/graphs/query",
        "method": "POST",
        "user_email": "user@example.com",
    }
    pool.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_report_error_without_url_returns_false(monkeypatch):
    """Missing analytics configuration must not mask the original error."""
    monkeypatch.delenv("FALKORDB_URL", raising=False)
    request = Request({
        "type": "http", "method": "GET", "path": "/", "headers": [],
        "query_string": b"", "scheme": "http", "server": ("localhost", 80),
    })

    assert await analytics.report_error(request, RuntimeError("boom")) is False


@pytest.mark.asyncio
async def test_report_error_swallows_setup_failure(monkeypatch):
    """Invalid connection configuration must preserve best-effort behavior."""
    monkeypatch.setenv("FALKORDB_URL", "invalid")
    request = Request({
        "type": "http", "method": "GET", "path": "/", "headers": [],
        "query_string": b"", "scheme": "http", "server": ("localhost", 80),
    })

    with patch.object(
        analytics.BlockingConnectionPool,
        "from_url",
        side_effect=ValueError("invalid URL"),
    ):
        assert await analytics.report_error(request, RuntimeError("boom")) is False
