"""End-to-end idle-timeout coverage for the three slow stages.

The 2026-07-29 demo failure was a stream that went silent long enough for an
intermediary to sever it. Silence can come from any stage that performs a slow
blocking call, and a keepalive cannot be written while the event loop is
blocked — so covering one stage is not enough. These tests drive the real
``run_query`` generator through the real route-layer serialization and assert
that the stream never goes idle longer than the keepalive interval, with the
stall injected into each stage in turn:

  * analysis            -> AnalysisAgent.get_analysis
  * table finding       -> api.graph.find
  * SQL execution       -> loader.execute_sql_query

Each stage is stalled with a genuinely blocking ``time.sleep`` so a regression
that puts the call back on the event loop shows up as a missing keepalive
rather than passing silently.
"""

import asyncio
import json
import time

import pytest

from api.core.pipeline import MESSAGE_DELIMITER
from api.routes.streaming import with_keepalive

STALL = 0.9
INTERVAL = 0.15
# Generous: the assertion is "keepalives kept flowing", not a latency budget.
MAX_IDLE = INTERVAL * 4

ANALYSIS = {
    "sql_query": "SELECT name FROM accounts LIMIT 5",
    "confidence": 0.9,
    "missing_information": "",
    "ambiguities": "",
    "explanation": "Lists customers.",
    "is_sql_translatable": True,
}
TABLES = [[
    "accounts", "Customer accounts.", {},
    [{"columnName": "name", "dataType": "text", "description": "Account name"}],
]]


class _Chat:
    """Minimal stand-in for ChatRequest."""

    def __init__(self, query="Show me five customers"):
        self.chat = [query]
        self.result = None
        self.instructions = None
        self.use_user_rules = False
        self.use_memory = False
        self.custom_api_key = None
        self.custom_model = None


class _Loader:
    stall = False

    @staticmethod
    def execute_sql_query(sql, db_url):
        if _Loader.stall:
            time.sleep(STALL)
        return [{"name": "Stark Industries"}]


@pytest.fixture(name="pipeline_stubs")
def _pipeline_stubs(monkeypatch):
    """Stub the external seams, leaving the pipeline's own structure real."""
    import api.core.text2sql as t2s

    _Loader.stall = False

    async def fake_db_description(namespaced, db=None):
        return ("CRM demo.", "postgresql://u:p@localhost:5432/demo")

    async def fake_find(namespaced, queries_history, db_description, db=None):
        return TABLES

    monkeypatch.setattr(t2s, "get_db_description", fake_db_description)
    monkeypatch.setattr(t2s, "find", fake_find)
    monkeypatch.setattr(t2s, "get_user_rules", lambda *a, **k: None)
    monkeypatch.setattr(
        t2s, "get_database_type_and_loader", lambda url: ("postgresql", _Loader)
    )
    monkeypatch.setattr(t2s, "check_schema_modification", lambda sql, loader: (False, None))
    monkeypatch.setattr(t2s, "detect_destructive_operation", lambda sql, db_type: (None, False))
    monkeypatch.setattr(t2s, "auto_quote_sql_identifiers", lambda sql, *a, **k: (sql, False))
    monkeypatch.setattr(t2s, "is_general_graph", lambda *a, **k: False)
    monkeypatch.setattr(t2s, "save_memory_background", lambda *a, **k: None)
    monkeypatch.setattr(t2s, "format_ai_response", lambda **k: "Here are five customers.")

    class _Relevancy:
        def __init__(self, *a, **k):
            pass

        async def get_answer(self, *a, **k):
            return {"status": "On-topic", "reason": "about accounts"}

    class _Analysis:
        stall = False

        def __init__(self, *a, **k):
            pass

        def get_analysis(self, *a, **k):
            if _Analysis.stall:
                time.sleep(STALL)
            return dict(ANALYSIS)

    monkeypatch.setattr(t2s, "RelevancyAgent", _Relevancy)
    monkeypatch.setattr(t2s, "AnalysisAgent", _Analysis)
    return {"analysis": _Analysis, "loader": _Loader, "text2sql": t2s}


async def _collect_gaps(t2s):
    """Run the pipeline through the real serializer + keepalive, timing arrivals."""
    from api.core.text2sql import _Final

    async def serialize(gen):
        async for event in gen:
            if isinstance(event, _Final):
                break
            yield json.dumps(event) + MESSAGE_DELIMITER

    gaps, payloads, keepalives = [], [], 0
    last = time.monotonic()
    stream = with_keepalive(
        serialize(t2s.run_query("u", "g", _Chat())), interval=INTERVAL
    )
    async for chunk in stream:
        now = time.monotonic()
        gaps.append(now - last)
        last = now
        if chunk == MESSAGE_DELIMITER:
            keepalives += 1
        else:
            payloads.append(chunk)
    return max(gaps), keepalives, payloads


@pytest.mark.unit
async def test_no_stall_completes_without_idle_gap(pipeline_stubs):
    max_gap, _, payloads = await _collect_gaps(pipeline_stubs["text2sql"])
    assert max_gap < MAX_IDLE, f"stream idle for {max_gap:.2f}s"
    assert any('"ai_response"' in p for p in payloads)


@pytest.mark.unit
async def test_slow_analysis_stage_keeps_stream_alive(pipeline_stubs):
    """Stage 1: the analysis LLM — the stall seen in the incident."""
    pipeline_stubs["analysis"].stall = True
    try:
        max_gap, keepalives, payloads = await _collect_gaps(pipeline_stubs["text2sql"])
    finally:
        pipeline_stubs["analysis"].stall = False

    assert keepalives >= 2, "no keepalive during the analysis stall"
    assert max_gap < MAX_IDLE, f"stream idle for {max_gap:.2f}s during analysis"
    assert any('"ai_response"' in p for p in payloads)


@pytest.mark.unit
async def test_slow_table_finding_keeps_stream_alive(pipeline_stubs, monkeypatch):
    """Stage 2: table finding — where the incident logs actually stop."""
    t2s = pipeline_stubs["text2sql"]

    async def slow_find(namespaced, queries_history, db_description, db=None):
        # api.graph.find offloads its blocking LLM/embedding work; mirror that.
        await asyncio.to_thread(time.sleep, STALL)
        return TABLES

    monkeypatch.setattr(t2s, "find", slow_find)
    max_gap, keepalives, payloads = await _collect_gaps(t2s)

    assert keepalives >= 2, "no keepalive during the table-finding stall"
    assert max_gap < MAX_IDLE, f"stream idle for {max_gap:.2f}s during table finding"
    assert any('"ai_response"' in p for p in payloads)


@pytest.mark.unit
async def test_slow_sql_execution_keeps_stream_alive(pipeline_stubs):
    """Stage 3: database execution."""
    pipeline_stubs["loader"].stall = True
    try:
        max_gap, keepalives, payloads = await _collect_gaps(pipeline_stubs["text2sql"])
    finally:
        pipeline_stubs["loader"].stall = False

    assert keepalives >= 2, "no keepalive during the SQL-execution stall"
    assert max_gap < MAX_IDLE, f"stream idle for {max_gap:.2f}s during SQL execution"
    assert any('"query_result"' in p for p in payloads)
