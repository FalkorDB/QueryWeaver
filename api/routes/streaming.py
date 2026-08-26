"""Keepalive support for the delimited streaming responses.

The query pipeline emits no events for the whole SQL-generation phase. An HTTP
body that goes silent for that long invites proxy buffering and idle-timeout
disconnects, which is what broke a live demo on 2026-07-29: the stream was
severed mid-body and the browser surfaced it as ``Stream error: network
error``.

This lives in the route layer rather than ``api/core`` because it is a
transport concern, and so it ships with the hosted app rather than the SDK.
"""

import asyncio

from api.core.pipeline import MESSAGE_DELIMITER

# Interval between keepalive bytes on an otherwise silent stream. Comfortably
# under the ~60s idle timeout common to proxies and PaaS edges.
STREAM_KEEPALIVE_INTERVAL = 10.0

# Discourage intermediaries from buffering the streamed body.
# ``X-Accel-Buffering`` is honoured by nginx and several PaaS edges.
STREAM_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
}


async def with_keepalive(chunks, interval: float = STREAM_KEEPALIVE_INTERVAL):
    """Emit a bare delimiter while *chunks* produces nothing.

    Wrap the already-serialized stream, so one call covers a whole endpoint
    including silent gaps introduced later. A bare delimiter splits into an
    empty part on the client, which every consumer's parser already skips, so
    this needs no protocol change and no client change.

    The producer runs as a task feeding a queue rather than having this
    generator race ``anext`` against a timeout directly. That matters for
    teardown: a client disconnect cancels the ASGI task, and cleanup that has
    to ``await`` cannot complete once cancellation is pending. Here the only
    cleanup is ``cancel()``, which never awaits, and ``chunks`` is consumed by
    a plain ``async for`` so its closure follows ordinary task cancellation
    instead of an ``aclose()`` racing an in-flight pull.
    """
    # maxsize=1 keeps backpressure: without it a slow client would let the
    # whole source stream accumulate in memory.
    queue: asyncio.Queue = asyncio.Queue(maxsize=1)
    finished = object()

    async def _pump():
        try:
            async for chunk in chunks:
                await queue.put(chunk)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # Hand the failure to the consumer so the route's error handling
            # still sees it, rather than losing it inside this task.
            # CancelledError is a BaseException, so it is not caught here and
            # propagates as cancellation should.
            await queue.put(exc)
        else:
            await queue.put(finished)

    pump = asyncio.ensure_future(_pump())
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=interval)
            except asyncio.TimeoutError:
                if pump.done():
                    # The producer ended without a terminal item, so it was
                    # cancelled — every other exit enqueues one. Emitting
                    # keepalives from here would never terminate the response.
                    # Drain anything it managed to enqueue first: the terminal
                    # item can land between the timeout firing and this check.
                    while not queue.empty():
                        queued = queue.get_nowait()
                        if queued is finished:
                            return
                        if isinstance(queued, Exception):
                            # ``from None``: the timeout is how we noticed, not
                            # the cause. Chaining it would misreport the error.
                            raise queued from None
                        yield queued
                    # Re-raises the producer's CancelledError, so cancellation
                    # reaches the consumer instead of stalling it.
                    pump.result()
                    return
                yield MESSAGE_DELIMITER
                continue
            if item is finished:
                return
            if isinstance(item, Exception):
                raise item
            yield item
    finally:
        # Non-awaiting cleanup: safe even when cancellation is already pending.
        pump.cancel()
