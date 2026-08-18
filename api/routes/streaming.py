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
    """
    iterator = aiter(chunks)
    try:
        while True:
            pending = asyncio.ensure_future(anext(iterator))
            try:
                while True:
                    done, _ = await asyncio.wait({pending}, timeout=interval)
                    if done:
                        break
                    yield MESSAGE_DELIMITER
                yield pending.result()
            except StopAsyncIteration:
                return
            finally:
                # A client disconnect arrives as GeneratorExit at one of the
                # yields above; without this the in-flight pull is orphaned
                # and keeps running after the response is gone. Waiting for
                # the cancellation to settle also releases the inner
                # generator, which cannot be closed while a pull is in flight.
                if not pending.done():
                    pending.cancel()
                    await asyncio.wait({pending})
    finally:
        aclose = getattr(iterator, "aclose", None)
        if aclose is not None:
            await aclose()
