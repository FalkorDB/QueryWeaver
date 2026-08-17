"""Tests for QueryWeaver error analytics."""

from unittest.mock import AsyncMock, MagicMock, patch

import asyncio
import pytest
from fastapi import Request

from api import analytics

pytestmark = [pytest.mark.unit]


def _request() -> Request:
    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/graphs/query",
        "headers": [],
        "query_string": b"",
        "scheme": "https",
        "server": ("queryweaver.example", 443),
    })
    request.state.user_email = "user@example.com"
    return request


def test_safe_message_redacts_credentials():
    """Persisted messages must not contain common credential values."""
    error = RuntimeError(
        'password=hunter2 token: abc123 Authorization: ****** '
        '"api_key": "json-secret" ******db.example:5432/app '
        '******host/db '
        'redis://:redis-secret@cache.example:6379'
    )

    message = analytics._safe_message(error)  # pylint: disable=protected-access

    for secret in (
        "hunter2", "abc123", "bearer-secret", "json-secret",
        "pg-secret", "mysql-secret",
        "redis-secret",
    ):
        assert secret not in message


def test_safe_message_preserves_diagnostic_phrases():
    """Words such as password and token are not secrets without a separator."""
    message = analytics._safe_message(  # pylint: disable=protected-access
        RuntimeError('password authentication failed; token expired')
    )
    assert "password authentication failed" in message
    assert "token expired" in message


@pytest.mark.asyncio
async def test_report_error_writes_org_graph():
    """Unhandled errors should be written with QueryWeaver attribution."""
    graph = AsyncMock()
    client = MagicMock()
    client.select_graph.return_value = graph

    sink: set = set()
    with patch.object(analytics, "_DB_OVERRIDE", client):
        analytics.report_error(
            _request(), RuntimeError("sales demo failed"), task_sink=sink
        )
        await asyncio.gather(*list(sink))

    params = graph.query.await_args.args[1]
    assert params == {
        "type": "RuntimeError",
        "message": "sales demo failed",
        "endpoint": "/graphs/query",
        "method": "POST",
        "user_email": "user@example.com",
    }


@pytest.mark.asyncio
async def test_report_error_swallows_setup_failure():
    """Analytics connection failures must preserve best-effort behavior."""
    sink: set = set()
    broken_db = MagicMock()
    broken_db.select_graph.side_effect = ConnectionError("offline")
    with patch.object(analytics, "_DB_OVERRIDE", broken_db):
        analytics.report_error(_request(), RuntimeError("boom"), task_sink=sink)
        results = await asyncio.gather(*list(sink), return_exceptions=True)

    assert isinstance(results[0], ConnectionError)
