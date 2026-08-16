"""Tests for QueryWeaver error analytics."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request

from api import analytics


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
