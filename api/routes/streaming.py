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
    queue: asyncio.Queue = asyncio.Queue()
    finished = object()

    async def _pump():
        try:
            async for chunk in chunks:
                queue.put_nowait(chunk)
        except asyncio.CancelledError:
            raise
        except BaseException as exc:  # pylint: disable=broad-exception-caught
            # Hand the failure to the consumer so the route's error handling
            # still sees it, rather than losing it inside this task.
            queue.put_nowait(exc)
        else:
            queue.put_nowait(finished)

    pump = asyncio.ensure_future(_pump())
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=interval)
            except asyncio.TimeoutError:
                yield MESSAGE_DELIMITER
                continue
            if item is finished:
                return
            if isinstance(item, BaseException):
                raise item
            yield item
    finally:
        # Non-awaiting cleanup: safe even when cancellation is already pending.
        pump.cancel()
