"""Schema loading must not block the event loop.

``load()`` backs the connect and refresh streaming responses. Its driver work —
connect, introspection — is synchronous, and a blocked loop cannot write
keepalives, so inline introspection means those two streams go silent for the
whole load and can be severed by an idle timeout.
"""

import asyncio
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from api.config import Config
from api.core.pipeline import MySQLLoader, PostgresLoader
from api.loaders.sqlserver_loader import SQLServerLoader

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
@patch("api.loaders.sqlserver_loader.load_to_graph")
@patch("api.loaders.sqlserver_loader.SQLServerLoader.extract_relationships", _slow)
@patch("api.loaders.sqlserver_loader.SQLServerLoader.extract_tables_info", _slow)
@patch("api.loaders.sqlserver_loader.pymssql.connect")
async def test_sqlserver_load_does_not_block_the_loop(mock_connect, mock_load_to_graph):
    def slow_connect(*_args, **_kwargs):
        time.sleep(STALL)
        return MagicMock()

    mock_connect.side_effect = slow_connect

    async def noop(*_args, **_kwargs):
        return None

    mock_load_to_graph.side_effect = noop

    _steps, ticks = await _ticks_while_consuming(
        SQLServerLoader.load("pfx", "sqlserver://u:p@h:1433/db")
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
            # Expected: we cancelled it. What matters is the cleanup that runs
            # afterwards, asserted below.
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



@pytest.mark.unit
@patch("api.loaders.postgres_loader.load_to_graph")
@patch("api.loaders.postgres_loader.PostgresLoader.extract_relationships", _slow)
@patch("api.loaders.postgres_loader.PostgresLoader.extract_tables_info", _slow)
@patch("api.loaders.postgres_loader.psycopg2.connect")
async def test_postgres_schema_introspection_is_time_bounded(
    mock_connect, mock_load_to_graph
):
    """Introspection carries its own, larger server-side deadline.

    A connect timeout alone is not enough: cancelling the awaiting task cannot
    stop the driver call, so a database that accepts the connection and then
    stalls would hold the session and the worker until it answered.
    """
    async def noop(*_args, **_kwargs):
        return None

    mock_load_to_graph.side_effect = noop
    mock_connect.return_value = MagicMock()

    async for _ in PostgresLoader.load("pfx", "postgresql://u:p@h:5432/db"):
        pass

    kwargs = mock_connect.call_args.kwargs
    assert kwargs["connect_timeout"] == Config.DB_CONNECT_TIMEOUT
    expected = f"-c statement_timeout={Config.DB_SCHEMA_TIMEOUT * 1000}"
    assert kwargs["options"] == expected
    # Deliberately larger than the user-query ceiling: metadata work over a
    # whole database legitimately outlasts a single query.
    assert Config.DB_SCHEMA_TIMEOUT > Config.DB_STATEMENT_TIMEOUT


@pytest.mark.unit
@patch("api.loaders.mysql_loader.pymysql.connect")
async def test_mysql_schema_introspection_is_time_bounded(mock_connect):
    cursor = MagicMock()
    cursor.description = None
    mock_connect.return_value.cursor.return_value = cursor

    with patch.object(MySQLLoader, "extract_tables_info", lambda *_a: {}), \
         patch.object(MySQLLoader, "extract_relationships", lambda *_a: {}), \
         patch("api.loaders.mysql_loader.load_to_graph") as load_to_graph:
        async def noop(*_args, **_kwargs):
            return None

        load_to_graph.side_effect = noop
        async for _ in MySQLLoader.load("pfx", "mysql://u:p@h:3306/db"):
            pass

    kwargs = mock_connect.call_args.kwargs
    assert kwargs["connect_timeout"] == Config.DB_CONNECT_TIMEOUT
    assert kwargs["read_timeout"] == Config.DB_SCHEMA_TIMEOUT
    assert kwargs["write_timeout"] == Config.DB_SCHEMA_TIMEOUT


@pytest.mark.unit
async def test_schema_introspection_concurrency_is_bounded(monkeypatch):
    """Only DB_SCHEMA_CONCURRENCY introspections may hold workers at once.

    The executor is shared with every other offloaded call, so unbounded schema
    work against a stalled database could starve LLM, embedding and user-SQL
    calls alike.
    """
    import api.loaders.introspection as introspection

    monkeypatch.setattr(introspection, "_EXECUTOR", None)
    monkeypatch.setattr(Config, "DB_SCHEMA_CONCURRENCY", 2, raising=False)

    live = 0
    peak = 0
    lock = threading.Lock()

    def blocking_work():
        nonlocal live, peak
        with lock:
            live += 1
            peak = max(peak, live)
        time.sleep(STALL)
        with lock:
            live -= 1
        return "done"

    results = await asyncio.gather(
        *(introspection.run_introspection(blocking_work) for _ in range(6))
    )

    assert results == ["done"] * 6
    assert peak <= 2, f"{peak} introspections ran concurrently, cap is 2"


@pytest.mark.unit
async def test_cancelled_introspection_keeps_its_slot(monkeypatch):
    """A cancelled introspection must not hand its slot to new work.

    Cancelling the awaiting task cannot stop the worker, so releasing the slot
    on cancellation lets the cap be exceeded by exactly the disconnect-driven
    load it exists to bound.
    """
    import api.loaders.introspection as introspection

    monkeypatch.setattr(introspection, "_EXECUTOR", None)
    monkeypatch.setattr(Config, "DB_SCHEMA_CONCURRENCY", 2, raising=False)

    live = 0
    peak = 0
    lock = threading.Lock()

    def blocking_work():
        nonlocal live, peak
        with lock:
            live += 1
            peak = max(peak, live)
        time.sleep(STALL * 2)
        with lock:
            live -= 1

    # Fill the cap, then cancel both awaiting tasks while the threads run on.
    first = [
        asyncio.ensure_future(introspection.run_introspection(blocking_work))
        for _ in range(2)
    ]
    await asyncio.sleep(STALL / 2)
    for task in first:
        task.cancel()
    await asyncio.gather(*first, return_exceptions=True)

    # Slots must still be held by the running threads.
    second = [
        asyncio.ensure_future(introspection.run_introspection(blocking_work))
        for _ in range(4)
    ]
    await asyncio.sleep(STALL)
    assert peak <= 2, f"{peak} workers ran concurrently while the cap was 2"

    await asyncio.gather(*second, return_exceptions=True)



@pytest.mark.unit
def test_introspection_pool_survives_a_new_event_loop(monkeypatch):
    """The cap must not be tied to whichever loop first contended on it.

    A module-level ``asyncio.Semaphore`` binds to the first loop that waits on
    it and then raises ``is bound to a different event loop`` for every later
    loop — which breaks any second `asyncio.run()`, including SDK callers.
    """
    import api.loaders.introspection as introspection

    monkeypatch.setattr(introspection, "_EXECUTOR", None)
    monkeypatch.setattr(Config, "DB_SCHEMA_CONCURRENCY", 2, raising=False)

    def work():
        time.sleep(0.05)
        return "done"

    async def batch():
        # More work than workers, so the pool is genuinely contended.
        return await asyncio.gather(
            *(introspection.run_introspection(work) for _ in range(3))
        )

    assert asyncio.run(batch()) == ["done"] * 3
    # A second, entirely separate loop must work just the same.
    assert asyncio.run(batch()) == ["done"] * 3


@pytest.mark.unit
@patch("api.loaders.postgres_loader.load_to_graph")
@patch("api.loaders.postgres_loader.psycopg2.connect")
async def test_introspection_connect_preserves_url_role(mock_connect, mock_load_to_graph):
    """Introspection must not silently gain privilege the URL restricted.

    ``options=`` replaces the entire URL-supplied options string. Building it
    without merging drops ``-c role=app_reader``, so introspection connects as
    the URL's owning role and can read tables the connection was scoped away
    from. This guards the connect call itself, not just the kwargs builder.
    """
    async def noop(*_args, **_kwargs):
        return None

    mock_load_to_graph.side_effect = noop
    mock_connect.return_value = MagicMock()

    url = "postgresql://u:p@h:5432/db?options=-c%20role%3Dapp_reader"
    with patch.object(PostgresLoader, "extract_tables_info", lambda *_a: {}), \
         patch.object(PostgresLoader, "extract_relationships", lambda *_a: {}):
        async for _ in PostgresLoader.load("pfx", url):
            pass

    options = mock_connect.call_args.kwargs["options"]
    assert "role=app_reader" in options, (
        "URL role was dropped — introspection would run with more privilege"
    )
    assert f"statement_timeout={Config.DB_SCHEMA_TIMEOUT * 1000}" in options
