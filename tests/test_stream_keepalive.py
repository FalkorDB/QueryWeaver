"""Tests for the streaming keepalive wrapper.

The 2026-07-29 demo failure was a stream that emitted nothing for the whole
SQL-generation phase and was severed mid-body. ``_with_keepalive`` keeps bytes
flowing through those silent gaps.
"""

import asyncio

import pytest

from api.core.pipeline import MESSAGE_DELIMITER
from api.routes.streaming import with_keepalive


async def _collect(agen):
    return [chunk async for chunk in agen]


@pytest.mark.unit
async def test_passes_chunks_through_unchanged():
    """A stream that never goes idle is forwarded verbatim."""
    async def source():
        yield "a"
        yield "b"

    assert await _collect(with_keepalive(source(), interval=5.0)) == ["a", "b"]


@pytest.mark.unit
async def test_empty_stream_yields_nothing():
    async def source():
        return
        yield  # pragma: no cover - never reached

    assert await _collect(with_keepalive(source(), interval=5.0)) == []


@pytest.mark.unit
async def test_emits_keepalive_during_a_silent_gap():
    """A slow producer gets bare delimiters until its next real chunk."""
    async def source():
        yield "first"
        await asyncio.sleep(0.25)
        yield "second"

    chunks = await _collect(with_keepalive(source(), interval=0.05))

    assert chunks[0] == "first"
    assert chunks[-1] == "second"
    keepalives = chunks[1:-1]
    assert keepalives, "expected at least one keepalive during the gap"
    assert set(keepalives) == {MESSAGE_DELIMITER}


@pytest.mark.unit
async def test_keepalive_is_an_empty_part_for_the_client():
    """A bare delimiter splits into empty parts, which the client skips.

    This is what makes the keepalive backward compatible: no new message type
    and no client change. Mirrors the parser in app/src/services/chat.ts.
    """
    payload = "".join([MESSAGE_DELIMITER, MESSAGE_DELIMITER])
    parts = [p for p in payload.split(MESSAGE_DELIMITER) if p.strip()]
    assert parts == []


@pytest.mark.unit
async def test_propagates_producer_exception():
    """Pipeline failures must still reach the route's error handler."""
    async def source():
        yield "a"
        raise RuntimeError("pipeline exploded")

    with pytest.raises(RuntimeError, match="pipeline exploded"):
        await _collect(with_keepalive(source(), interval=5.0))


@pytest.mark.unit
async def test_close_mid_gap_tears_down_the_inner_stream():
    """A client disconnect during a silent gap must not orphan the pull.

    The inner generator's ``finally`` running is the observable proof that the
    wrapper closed it rather than leaving it pending on the loop.
    """
    closed = asyncio.Event()

    async def source():
        try:
            yield "first"
            await asyncio.sleep(60)  # the silent gap; never completes
            yield "unreachable"  # pragma: no cover
        finally:
            closed.set()

    agen = with_keepalive(source(), interval=0.05)
    assert await agen.__anext__() == "first"
    # The next pull enters the gap, so this returns a keepalive, not a chunk.
    assert await agen.__anext__() == MESSAGE_DELIMITER

    await agen.aclose()

    await asyncio.wait_for(closed.wait(), timeout=1)
