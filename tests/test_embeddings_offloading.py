"""Embedding calls must not run on the event loop.

``EmbeddingsModel.embed`` is a blocking network call. Called directly from an
async method it blocks the loop, and a blocked loop cannot write keepalives —
so a slow embedding kills open streams regardless of the keepalive wrapper.
The memory path (enabled by default in the browser) and the schema loaders both
embed, so both go through ``api.embeddings``.
"""

import asyncio
import inspect
import time

import pytest

from api.config import Config
from api.embeddings import embed_off_loop, embed_one_off_loop, vector_size_off_loop

STALL = 0.4
TICK = 0.02


@pytest.fixture(name="slow_embedding")
def _slow_embedding(monkeypatch):
    def slow_embed(text):
        time.sleep(STALL)
        count = len(text) if isinstance(text, list) else 1
        return [[0.1, 0.2] for _ in range(count)]

    def slow_vector_size():
        time.sleep(STALL)
        return 2

    monkeypatch.setattr(Config.EMBEDDING_MODEL, "embed", slow_embed)
    monkeypatch.setattr(Config.EMBEDDING_MODEL, "get_vector_size", slow_vector_size)


async def _ticks_during(coro):
    """Count event-loop ticks while *coro* runs."""
    stop = asyncio.Event()

    async def ticker():
        samples = []
        while not stop.is_set():
            samples.append(time.monotonic())
            await asyncio.sleep(TICK)
        return samples

    ticker_task = asyncio.ensure_future(ticker())
    result = await coro
    stop.set()
    return result, await ticker_task


@pytest.mark.unit
async def test_embed_off_loop_keeps_the_loop_responsive(slow_embedding):
    vectors, ticks = await _ticks_during(embed_off_loop(["a", "b"]))
    assert len(vectors) == 2
    assert len(ticks) > (STALL / TICK) * 0.4, f"event loop starved: {len(ticks)} ticks"


@pytest.mark.unit
async def test_embed_one_off_loop_returns_a_single_vector(slow_embedding):
    vector, ticks = await _ticks_during(embed_one_off_loop("a"))
    assert vector == [0.1, 0.2]
    assert len(ticks) > (STALL / TICK) * 0.4, f"event loop starved: {len(ticks)} ticks"


@pytest.mark.unit
async def test_vector_size_off_loop_keeps_the_loop_responsive(slow_embedding):
    size, ticks = await _ticks_during(vector_size_off_loop())
    assert size == 2
    assert len(ticks) > (STALL / TICK) * 0.4, f"event loop starved: {len(ticks)} ticks"


@pytest.mark.unit
def test_async_callers_do_not_embed_inline():
    """Guard the call sites: no bare ``EMBEDDING_MODEL.embed`` in async modules.

    These modules run inside streaming responses, so an inline embed there
    reintroduces the stall this suite exists to prevent.
    """
    import api.graph
    import api.loaders.graph_loader as graph_loader
    import api.memory.graphiti_tool as graphiti_tool

    offenders = []
    for module in (api.graph, graph_loader, graphiti_tool):
        source = inspect.getsource(module)
        for lineno, line in enumerate(source.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "EMBEDDING_MODEL.embed(" in stripped or (
                "EMBEDDING_MODEL.get_vector_size(" in stripped
            ):
                if "to_thread" not in stripped:
                    offenders.append(f"{module.__name__}:{lineno}: {stripped}")

    assert not offenders, "inline embedding call(s):\n" + "\n".join(offenders)


@pytest.mark.unit
def test_async_callers_do_not_call_llms_inline():
    """No bare provider call in modules whose coroutines back a stream.

    Every one of these has been a real incident-class bug: a synchronous
    provider call inside an ``async def`` blocks the event loop, and a blocked
    loop cannot write keepalives, so open streams are severed regardless of the
    keepalive wrapper.
    """
    import api.graph
    import api.loaders.graph_loader as graph_loader
    import api.memory.graphiti_tool as graphiti_tool
    import api.routes.settings as settings_route

    # Bare provider entry points that must never be invoked on the loop.
    calls = ("completion(", "batch_completion(", "embedding(")
    offenders = []
    for module in (api.graph, graph_loader, graphiti_tool, settings_route):
        source = inspect.getsource(module)
        for lineno, line in enumerate(source.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#") or "import" in stripped:
                continue
            if any(call in stripped for call in calls):
                if "to_thread" not in stripped and "off_loop" not in stripped:
                    offenders.append(f"{module.__name__}:{lineno}: {stripped}")

    assert not offenders, "inline provider call(s):\n" + "\n".join(offenders)


@pytest.mark.unit
def test_embedding_calls_are_time_bounded():
    """A hung provider must not pin a worker thread forever."""
    kwargs = Config.EMBEDDING_MODEL._embedding_kwargs()
    # LLM_TIMEOUT is the budget for the whole call, so the per-attempt value is
    # that budget divided across attempts; retries cannot push the real ceiling
    # past it.
    attempts = Config.LLM_MAX_RETRIES + 1
    assert kwargs == Config.llm_call_bounds()
    assert kwargs["timeout"] == Config.LLM_TIMEOUT / attempts
    assert kwargs["timeout"] * attempts <= Config.LLM_TIMEOUT
    assert kwargs["num_retries"] == 0
