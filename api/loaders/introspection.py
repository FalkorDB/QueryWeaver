"""Bounded execution for schema introspection.

Introspection runs in a worker thread because the drivers are blocking, and
cancelling the awaiting task does not stop that thread: a stalled database
holds its session and its worker until it answers. Two bounds follow from
that — a deadline the server applies (see each loader's connect parameters),
and a cap on how many introspections may occupy the shared executor at once,
so a stalled database cannot starve every other offloaded call.
"""

import asyncio
import logging

from api.config import Config

_SLOTS: asyncio.Semaphore | None = None


def _semaphore() -> asyncio.Semaphore:
    """Create the semaphore lazily, on the loop that first needs it."""
    global _SLOTS  # pylint: disable=global-statement
    if _SLOTS is None:
        _SLOTS = asyncio.Semaphore(Config.DB_SCHEMA_CONCURRENCY)
    return _SLOTS


async def run_introspection(func, /, *args, **kwargs):
    """Run *func* in a worker thread, holding one introspection slot."""
    slots = _semaphore()
    if slots.locked():
        logging.info(
            "schema introspection queued: %d concurrent slots in use",
            Config.DB_SCHEMA_CONCURRENCY,
        )
    async with slots:
        return await asyncio.to_thread(func, *args, **kwargs)
