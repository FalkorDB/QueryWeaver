"""Bounded execution for schema introspection.

Introspection runs off the event loop because the drivers are blocking, and
cancelling the awaiting task cannot stop the worker: a stalled database holds
its session and its worker until it answers. Two bounds follow — a deadline the
server applies (see each loader's connect parameters), and a cap on how many
introspections may run at once, so a stalled database cannot starve the shared
default executor that every other offloaded call uses.

The cap is a dedicated ``ThreadPoolExecutor`` rather than an
``asyncio.Semaphore``: a module-level semaphore binds itself to the first loop
that contends on it and then raises ``is bound to a different event loop`` for
any later loop, and an executor bounds the *threads* themselves, so a cancelled
introspection cannot free its slot while its worker is still running.
"""

import asyncio
import functools
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from api.config import Config

_EXECUTOR: ThreadPoolExecutor | None = None
_EXECUTOR_LOCK = threading.Lock()


def _executor() -> ThreadPoolExecutor:
    """Create the process-wide introspection pool once, lazily."""
    global _EXECUTOR  # pylint: disable=global-statement
    with _EXECUTOR_LOCK:
        if _EXECUTOR is None:
            _EXECUTOR = ThreadPoolExecutor(
                max_workers=Config.DB_SCHEMA_CONCURRENCY,
                thread_name_prefix="schema-introspect",
            )
        return _EXECUTOR


async def run_introspection(func, /, *args, **kwargs):
    """Run *func* on the bounded introspection pool.

    Cancellation reaches the caller while the worker keeps running: the future
    is shielded, so an abandoned introspection continues to occupy its worker
    until the driver returns. That is the point — releasing the slot early
    would let the cap be exceeded by exactly the disconnect-driven load it
    exists to bound.
    """
    pool = _executor()
    queued = getattr(pool, "_work_queue", None)
    if queued is not None and queued.qsize():
        logging.info(
            "schema introspection queued: all %d workers busy",
            Config.DB_SCHEMA_CONCURRENCY,
        )

    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(pool, functools.partial(func, *args, **kwargs))
    return await asyncio.shield(future)
