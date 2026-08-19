"""``api.graph.find`` must not block the event loop.

``find`` performs a completion and an embedding call, both synchronous network
calls, and it is launched with ``asyncio.create_task`` alongside the relevancy
agent. Running them on the loop made that concurrency illusory and — more
importantly — stopped any stream from writing keepalives, since a blocked loop
cannot flush bytes. This is the call that logs "Calling LLM to find relevant
tables/columns", the last line before the stall in the 2026-07-29 logs.
"""

import asyncio
import json
import time
import types

import pytest

import api.graph as graph_module

STALL = 0.6
TICK = 0.02


class _FakeResult:
    result_set: list = []


class _FakeGraph:
    async def query(self, query, params=None, timeout=None):
        return _FakeResult()


class _FakeDB:
    def select_graph(self, graph_id):
        return _FakeGraph()


@pytest.fixture(name="slow_find_deps")
def _slow_find_deps(monkeypatch):
    """Make find()'s two network calls slow and synchronous."""
    descriptions = json.dumps({
        "tables_descriptions": [
            {"name": "accounts", "description": "customer accounts"}
        ],
        "columns_descriptions": [
            {"name": "name", "description": "account name"}
        ],
    })

    def slow_completion(*args, **kwargs):
        time.sleep(STALL)              # blocking, like the real provider call
        return descriptions

    def slow_embed(texts):
        time.sleep(STALL)              # blocking, like the real embedding call
        return [[0.0, 0.1, 0.2] for _ in texts]

    monkeypatch.setattr(graph_module, "run_completion", slow_completion)
    monkeypatch.setattr(graph_module, "resolve_db", lambda db: _FakeDB())
    monkeypatch.setattr(
        graph_module.Config, "EMBEDDING_MODEL",
        types.SimpleNamespace(embed=slow_embed), raising=False,
    )


@pytest.mark.unit
async def test_find_does_not_block_the_event_loop(slow_find_deps):
    """A ticker must keep running while find() is in its blocking calls."""
    ticks = []
    stop = asyncio.Event()

    async def ticker():
        while not stop.is_set():
            ticks.append(time.monotonic())
            await asyncio.sleep(TICK)

    ticker_task = asyncio.ensure_future(ticker())
    started = time.monotonic()
    tables = await graph_module.find("g", ["show me customers"], "CRM demo.")
    elapsed = time.monotonic() - started
    stop.set()
    await ticker_task

    # Both blocking calls ran, so this took at least 2 * STALL.
    assert elapsed >= STALL * 2 * 0.9, f"stalls did not run (elapsed {elapsed:.2f}s)"

    # The loop stayed responsive throughout: with both calls offloaded the
    # ticker keeps firing. If they ran on the loop it would be starved and
    # produce only a couple of ticks.
    expected = elapsed / TICK
    assert len(ticks) > expected * 0.4, (
        f"event loop was starved: {len(ticks)} ticks in {elapsed:.2f}s "
        f"(expected roughly {expected:.0f})"
    )

    # And the longest gap between ticks stays far below the stall duration.
    gaps = [b - a for a, b in zip(ticks, ticks[1:])]
    assert max(gaps) < STALL / 2, f"loop blocked for {max(gaps):.2f}s"

    # The fake graph returns no rows, so the call still completes normally.
    assert tables == []
