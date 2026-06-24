"""Tests for always-on per-query usage tracking.

Usage tracking (``api/core/usage_tracking.py``) records every query onto the
``Organizations`` graph, independent of the optional ``use_memory`` feature and
the LLM provider. These tests assert the write content, the ungated design,
and that failures never propagate to the caller.
"""

import asyncio
import base64
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.core import usage_tracking
from api.core.usage_tracking import (
    _decode_email,
    record_query_usage_background,
)

pytestmark = [pytest.mark.unit]

EMAIL = "gal.shubeli@falkordb.com"
USER_ID = base64.b64encode(EMAIL.encode()).decode()


def _mock_db():
    """A FalkorDB-like mock whose ``select_graph(...).query`` is awaitable."""
    graph = MagicMock()
    graph.query = AsyncMock(return_value=MagicMock(result_set=[]))
    db = MagicMock()
    db.select_graph.return_value = graph
    return db, graph


async def _drain(sink):
    """Await every background task the recorder scheduled into ``sink``."""
    await asyncio.gather(*list(sink), return_exceptions=True)


class TestDecodeEmail:
    def test_decodes_valid_user_id(self):
        assert _decode_email(USER_ID) == EMAIL

    def test_returns_none_for_empty(self):
        assert _decode_email("") is None

    def test_returns_none_for_garbage(self):
        # Malformed base64 must yield None, not raise.
        assert _decode_email("!!!not-base64!!!") is None

    def test_returns_none_for_valid_base64_that_is_not_an_email(self):
        # Decodes cleanly but isn't email-shaped -> skip (no phantom write).
        not_email = base64.b64encode(b"notanemail").decode()
        assert _decode_email(not_email) is None


class TestRecordQueryUsage:
    @pytest.mark.asyncio
    async def test_records_successful_query_event(self):
        db, graph = _mock_db()
        sink: set = set()
        with patch.object(usage_tracking, "resolve_db", return_value=db), \
                patch.object(usage_tracking, "is_general_graph", return_value=False):
            record_query_usage_background(
                USER_ID, f"{USER_ID}_mydb", success=True, db=db, task_sink=sink
            )
            await _drain(sink)

        db.select_graph.assert_called_once_with("Organizations")
        graph.query.assert_awaited_once()
        cypher, params = graph.query.await_args.args
        assert "MATCH (u:User {email: $email})" in cypher
        assert ":UsageEvent" in cypher
        assert params == {
            "email": EMAIL,
            "graph_id": f"{USER_ID}_mydb",
            "is_demo": False,
            "success": True,
        }

    @pytest.mark.asyncio
    async def test_records_failed_query_event(self):
        db, graph = _mock_db()
        sink: set = set()
        with patch.object(usage_tracking, "resolve_db", return_value=db), \
                patch.object(usage_tracking, "is_general_graph", return_value=False):
            record_query_usage_background(
                USER_ID, f"{USER_ID}_mydb", success=False, db=db, task_sink=sink
            )
            await _drain(sink)

        _cypher, params = graph.query.await_args.args
        assert params["success"] is False

    @pytest.mark.asyncio
    async def test_demo_graph_is_flagged(self):
        db, graph = _mock_db()
        sink: set = set()
        with patch.object(usage_tracking, "resolve_db", return_value=db), \
                patch.object(usage_tracking, "is_general_graph", return_value=True):
            record_query_usage_background(
                USER_ID, "DEMO_CRM", success=True, db=db, task_sink=sink
            )
            await _drain(sink)

        _cypher, params = graph.query.await_args.args
        assert params["is_demo"] is True
        assert params["graph_id"] == "DEMO_CRM"

    @pytest.mark.asyncio
    async def test_invalid_user_id_skips_write(self):
        db, graph = _mock_db()
        sink: set = set()
        with patch.object(usage_tracking, "resolve_db", return_value=db):
            record_query_usage_background(
                "!!!bad!!!", "x_y", success=True, db=db, task_sink=sink
            )
            await _drain(sink)

        # No task scheduled, no graph touched.
        assert not sink
        graph.query.assert_not_awaited()
        db.select_graph.assert_not_called()

    @pytest.mark.asyncio
    async def test_write_failure_is_swallowed(self):
        db, graph = _mock_db()
        graph.query.side_effect = RuntimeError("falkordb down")
        sink: set = set()
        with patch.object(usage_tracking, "resolve_db", return_value=db), \
                patch.object(usage_tracking, "is_general_graph", return_value=False), \
                patch.object(usage_tracking.logging, "error") as mock_log_error:
            # The synchronous call must not raise despite the write failing.
            record_query_usage_background(
                USER_ID, f"{USER_ID}_mydb", success=True, db=db, task_sink=sink
            )
            await _drain(sink)

        # Failure was logged by the done-callback, not propagated.
        assert any(
            "Usage tracking save failed" in str(call.args[0])
            for call in mock_log_error.call_args_list
        )


class TestUngatedDesign:
    def test_recorder_has_no_memory_or_provider_parameter(self):
        """Tracking cannot be gated by ``use_memory`` or the LLM provider:
        the recorder simply has no such inputs."""
        params = set(inspect.signature(record_query_usage_background).parameters)
        assert params == {"user_id", "namespaced", "success", "db", "task_sink"}
        assert "use_memory" not in params
        assert "provider" not in params
