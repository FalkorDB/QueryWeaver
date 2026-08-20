"""Schema loading must not block the event loop.

``load()`` backs the connect and refresh streaming responses. Its driver work —
connect, introspection — is synchronous, and a blocked loop cannot write
keepalives, so inline introspection means those two streams go silent for the
whole load and can be severed by an idle timeout.
"""

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from api.core.pipeline import MySQLLoader, PostgresLoader

STALL = 0.3
TICK = 0.02


async def _ticks_while_consuming(agen):
    """Drain *agen*, counting event-loop ticks."""
    stop = asyncio.Event()

    async def ticker():
        samples = []
        while not stop.is_set():
            samples.append(time.monotonic())
            await asyncio.sleep(TICK)
        return samples

    ticker_task = asyncio.ensure_future(ticker())
    steps = [step async for step in agen]
    stop.set()
    return steps, await ticker_task


def _slow(*_args, **_kwargs):
    time.sleep(STALL)
    return {}


@pytest.mark.unit
@patch("api.loaders.postgres_loader.load_to_graph")
@patch("api.loaders.postgres_loader.PostgresLoader.extract_relationships", _slow)
@patch("api.loaders.postgres_loader.PostgresLoader.extract_tables_info", _slow)
@patch("api.loaders.postgres_loader.psycopg2.connect")
async def test_postgres_load_does_not_block_the_loop(mock_connect, mock_load_to_graph):
    def slow_connect(*_args, **_kwargs):
        time.sleep(STALL)
        return MagicMock()

    mock_connect.side_effect = slow_connect

    async def noop(*_args, **_kwargs):
        return None

    mock_load_to_graph.side_effect = noop

    _steps, ticks = await _ticks_while_consuming(
        PostgresLoader.load("pfx", "postgresql://u:p@h:5432/db")
    )

    # Three blocking stages at STALL each; the loop must stay responsive.
    assert len(ticks) > (STALL * 3 / TICK) * 0.3, (
        f"event loop starved during schema load: {len(ticks)} ticks"
    )
    gaps = [b - a for a, b in zip(ticks, ticks[1:])]
    assert max(gaps) < STALL, f"loop blocked for {max(gaps):.2f}s"


@pytest.mark.unit
@patch("api.loaders.mysql_loader.load_to_graph")
@patch("api.loaders.mysql_loader.MySQLLoader.extract_relationships", _slow)
@patch("api.loaders.mysql_loader.MySQLLoader.extract_tables_info", _slow)
@patch("api.loaders.mysql_loader.pymysql.connect")
async def test_mysql_load_does_not_block_the_loop(mock_connect, mock_load_to_graph):
    def slow_connect(*_args, **_kwargs):
        time.sleep(STALL)
        return MagicMock()

    mock_connect.side_effect = slow_connect

    async def noop(*_args, **_kwargs):
        return None

    mock_load_to_graph.side_effect = noop

    _steps, ticks = await _ticks_while_consuming(
        MySQLLoader.load("pfx", "mysql://u:p@h:3306/db")
    )

    assert len(ticks) > (STALL * 3 / TICK) * 0.3, (
        f"event loop starved during schema load: {len(ticks)} ticks"
    )
    gaps = [b - a for a, b in zip(ticks, ticks[1:])]
    assert max(gaps) < STALL, f"loop blocked for {max(gaps):.2f}s"


@pytest.mark.unit
@pytest.mark.parametrize("loader_module,loader,url", [
    ("api.loaders.postgres_loader", "PostgresLoader", "postgresql://u:p@h:5432/db"),
    ("api.loaders.mysql_loader", "MySQLLoader", "mysql://u:p@h:3306/db"),
])
async def test_cancelling_a_schema_load_still_closes_the_connection(
    loader_module, loader, url
):
    """A client disconnect must not leak the database session.

    The introspection runs in a worker thread that cancellation cannot stop,
    so cleanup has to live in that same thread. Closing from the generator's
    ``finally`` instead would either race the in-flight introspection or, where
    there was no ``finally`` at all, leak the connection outright.
    """
    conn = MagicMock()
    loader_cls = {"PostgresLoader": PostgresLoader, "MySQLLoader": MySQLLoader}[loader]
    connect_name = (
        "psycopg2.connect" if loader == "PostgresLoader" else "pymysql.connect"
    )

    def slow_extract(*_args, **_kwargs):
        time.sleep(STALL * 3)
        return {}

    with patch(f"{loader_module}.{connect_name}", return_value=conn), \
         patch.object(loader_cls, "extract_tables_info", slow_extract), \
         patch.object(loader_cls, "extract_relationships", slow_extract), \
         patch(f"{loader_module}.load_to_graph"):
        agen = loader_cls.load("pfx", url)
        assert await agen.__anext__() == (True, "Extracting table information...")

        consumer = asyncio.ensure_future(agen.__anext__())
        await asyncio.sleep(STALL)          # introspection is in flight
        consumer.cancel()
        try:
            await consumer
        except asyncio.CancelledError:
            pass
        await agen.aclose()

        # The worker owns cleanup, so it runs even though the awaiting task was
        # cancelled. Give the thread time to finish and close.
        for _ in range(50):
            if conn.close.called:
                break
            await asyncio.sleep(0.05)

    assert conn.close.called, "connection was not closed after cancellation"


@pytest.mark.unit
@pytest.mark.parametrize("loader_module,loader,url", [
    ("api.loaders.postgres_loader", "PostgresLoader", "postgresql://u:p@h:5432/db"),
    ("api.loaders.mysql_loader", "MySQLLoader", "mysql://u:p@h:3306/db"),
])
async def test_failed_introspection_still_closes_the_connection(
    loader_module, loader, url
):
    """An error mid-introspection must not leak the session.

    This is what the worker's ``finally`` buys: MySQL and Snowflake previously
    closed only on the success path, so any failure left the connection open,
    and repeated failures exhaust database sessions.
    """
    conn = MagicMock()
    loader_cls = {"PostgresLoader": PostgresLoader, "MySQLLoader": MySQLLoader}[loader]
    connect_name = (
        "psycopg2.connect" if loader == "PostgresLoader" else "pymysql.connect"
    )

    def boom(*_args, **_kwargs):
        raise RuntimeError("introspection blew up")

    with patch(f"{loader_module}.{connect_name}", return_value=conn), \
         patch.object(loader_cls, "extract_tables_info", boom), \
         patch(f"{loader_module}.load_to_graph"):
        steps = [step async for step in loader_cls.load("pfx", url)]

    # The loader reports failure to the stream rather than raising...
    assert steps[-1][0] is False
    # ...and the connection is closed regardless.
    assert conn.close.called, "connection leaked when introspection failed"

