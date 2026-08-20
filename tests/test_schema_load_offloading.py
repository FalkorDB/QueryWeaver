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
